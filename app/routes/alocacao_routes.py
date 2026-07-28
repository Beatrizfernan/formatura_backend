"""
Rotas de alocação:
  GET  /api/alocacao/<formatura_id>                → carrega alocação atual
  PUT  /api/alocacao/<formatura_id>/reordenar      → recebe nova ordem dos cursos, realoca do zero
  PUT  /api/alocacao/<formatura_id>/mover-curso    → move um bloco contíguo de um curso (um ou mais trechos) pra um destino, empurrando em cascata só a partir dali
"""

import re
from flask import Blueprint, jsonify, request
from mongoengine.errors import DoesNotExist, ValidationError

from app.models.alocacao import Alocacao, AlocacaoFila
from app.models.formatura import Formatura
from app.models.curso import Curso
from app.services.alocacao_service import gerar_alocacao_vertical_corrigida

alocacao_bp = Blueprint("alocacao", __name__, url_prefix="/api/alocacao")


# ---------------------------------------------------------------------------
# Helpers compartilhados
# ---------------------------------------------------------------------------

def _calcular_assentos_vazios(local, alocacao):
    assentos_vazios = []
    for fila in local.filas_ordenadas:
        ocupados = set()
        for af in alocacao.alocacoes:
            if af.fila_nome == fila.nome:
                ocupados.update(af.assentos)
        todos = set(range(1, fila.quantidade_assentos + 1))
        vazios = sorted(todos - ocupados)
        if vazios:
            assentos_vazios.append({
                "fila": fila.nome,
                "assentos_vazios": vazios,
                "total_vazios": len(vazios),
            })
    return assentos_vazios


def _resumo_detalhado(alocacao, formatura):
    """
    Retorna os detalhes dos cursos NA MESMA ORDEM em que aparecem
    em formatura.cursos (= ordem da planilha / última reordenação).
    Isso garante que legenda e mapa sempre coincidem.
    """
    resumo_por_curso = alocacao.get_resumo_por_curso()
    resultado = []

    for curso_formatura in formatura.cursos:
        curso_id = curso_formatura.curso_id
        if curso_id not in resumo_por_curso:
            continue
        curso = Curso.get_by_id(curso_id)
        if not curso:
            continue
        info = resumo_por_curso[curso_id]
        resultado.append({
            "curso": curso.nome,
            "curso_id": curso_id,
            "abreviacao": curso.abreviacao if curso.abreviacao else curso.nome[:3].upper(),
            "total_assentos": info["total_assentos"],
            "filas": info["detalhes_filas"],
        })

    return resultado


def _ordenar_filas(filas_dict):
    def chave(nome):
        m = re.match(r"^(\d+)([A-Z]+)$", nome)
        return (int(m.group(1)), m.group(2)) if m else (9999, nome)
    return sorted(filas_dict.keys(), key=chave)


def _payload_alocacao(alocacao, local, formatura):
    return {
        "id": str(alocacao.id),
        "total_alocado": alocacao.total_assentos_alocados,
        "taxa_ocupacao": f"{round(alocacao.taxa_ocupacao, 2)}%",
        "detalhes": _resumo_detalhado(alocacao, formatura),
        "assentos_vazios": _calcular_assentos_vazios(local, alocacao),
    }


# ---------------------------------------------------------------------------
# GET /api/alocacao/<formatura_id>
# ---------------------------------------------------------------------------

@alocacao_bp.route("/<formatura_id>", methods=["GET"])
def get_alocacao(formatura_id):
    try:
        formatura = Formatura.objects.get(id=formatura_id, ativo=True)
    except DoesNotExist:
        return jsonify({"error": "Formatura não encontrada"}), 404

    alocacao = Alocacao.objects(formatura=formatura).first()
    if not alocacao:
        return jsonify({"error": "Alocação não encontrada"}), 404

    return jsonify({
        "formatura": {
            "id": str(formatura.id),
            "nome": formatura.nome,
            "data": formatura.data.isoformat(),
            "local": formatura.local.nome,
        },
        "alocacao": _payload_alocacao(alocacao, formatura.local, formatura),
    }), 200


# ---------------------------------------------------------------------------
# PUT /api/alocacao/<formatura_id>/reordenar
# ---------------------------------------------------------------------------

@alocacao_bp.route("/<formatura_id>/reordenar", methods=["PUT"])
def reordenar(formatura_id):
    """
    Body JSON:
    {
        "ordem": ["curso_id_1", "curso_id_2", ...]   // nova ordem desejada
    }
    A nova ordem é salva em formatura.cursos para que futuras chamadas
    ao GET também retornem os detalhes nessa ordem.
    """
    try:
        formatura = Formatura.objects.get(id=formatura_id, ativo=True)
    except DoesNotExist:
        return jsonify({"error": "Formatura não encontrada"}), 404

    data = request.get_json()
    if not data or "ordem" not in data:
        return jsonify({"error": "'ordem' é obrigatório"}), 400

    nova_ordem = data["ordem"]
    if not isinstance(nova_ordem, list) or not nova_ordem:
        return jsonify({"error": "'ordem' deve ser uma lista não vazia"}), 400

    ids_formatura = {c.curso_id for c in formatura.cursos}
    if set(nova_ordem) != ids_formatura:
        return jsonify({"error": "A lista de IDs não corresponde aos cursos desta formatura"}), 400

    # Reordena os cursos e SALVA na formatura para persistir a ordem
    cursos_map = {c.curso_id: c for c in formatura.cursos}
    formatura.cursos = [cursos_map[cid] for cid in nova_ordem]
    formatura.save()  # persiste a nova ordem

    # Deleta alocação existente e gera nova com a nova ordem
    Alocacao.objects(formatura=formatura).delete()

    try:
        nova_alocacao = gerar_alocacao_vertical_corrigida(formatura)
        nova_alocacao.save()
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"Erro ao gerar alocação: {str(e)}"}), 500

    return jsonify({
        "success": True,
        "alocacao": _payload_alocacao(nova_alocacao, formatura.local, formatura),
    }), 200


# ---------------------------------------------------------------------------
# PUT /api/alocacao/<formatura_id>/mover-curso
# ---------------------------------------------------------------------------

def _mover_e_empurrar(alocacao, formatura, curso_id_alvo, origem_segmentos, fila_destino, assento_destino):
    """
    Move um ou mais trechos de origem (normalmente o "bloco contíguo" de um curso que se
    espalhou por várias filas seguidas) para (fila_destino, assento_destino), empurrando em
    cascata — só a partir do destino em diante — o que estiver no caminho.

    origem_segmentos: lista de dicts {"fila": str, "inicio": int, "fim": int}.

    Filas antes do destino, e qualquer trecho do mesmo curso que NÃO esteja em
    origem_segmentos, não são tocados.
    """
    local = formatura.local
    capacidades = {f.nome: f.quantidade_assentos for f in local.filas_ordenadas}
    filas_ordenadas = _ordenar_filas(capacidades)

    if not origem_segmentos:
        raise ValidationError("Nenhum trecho de origem informado.")
    if fila_destino not in capacidades:
        raise ValidationError(f"Fila '{fila_destino}' não existe neste local.")
    if assento_destino < 1 or assento_destino > capacidades[fila_destino]:
        raise ValidationError(f"Assento {assento_destino} inválido para fila '{fila_destino}'.")

    mapa = {f: {} for f in filas_ordenadas}
    for af in alocacao.alocacoes:
        if af.fila_nome in mapa:
            for num in af.assentos:
                mapa[af.fila_nome][num] = af.curso_id

    for fila, cap in capacidades.items():
        for i in range(1, cap + 1):
            if i not in mapa[fila]:
                mapa[fila][i] = "VAZIO"

    # Valida todos os trechos de origem antes de mexer em qualquer coisa
    for seg in origem_segmentos:
        fila_o, ini_o, fim_o = seg["fila"], seg["inicio"], seg["fim"]
        if fila_o not in capacidades:
            raise ValidationError(f"Fila '{fila_o}' não existe neste local.")
        if ini_o < 1 or fim_o < ini_o or fim_o > capacidades[fila_o]:
            raise ValidationError(f"Intervalo de assentos inválido na fila '{fila_o}'.")
        for num in range(ini_o, fim_o + 1):
            if mapa[fila_o][num] != curso_id_alvo:
                raise ValidationError(
                    f"O assento {num} da fila '{fila_o}' não pertence ao curso informado."
                )

    total_curso_alvo = sum(seg["fim"] - seg["inicio"] + 1 for seg in origem_segmentos)

    # Libera todos os trechos de origem (e só eles)
    for seg in origem_segmentos:
        for num in range(seg["inicio"], seg["fim"] + 1):
            mapa[seg["fila"]][num] = "VAZIO"

    idx_dest = filas_ordenadas.index(fila_destino)

    # Empurra só OUTROS cursos. Qualquer outra ocorrência do próprio curso_id_alvo que
    # esteja fora de origem_segmentos (ex: um pedaço solto em outra fila) fica congelada
    # no lugar — nunca entra na fila de empurrar nem é limpa.
    cursos_para_empurrar = []
    for fi, fila in enumerate(filas_ordenadas):
        if fi < idx_dest:
            continue
        cap = capacidades[fila]
        inicio = assento_destino if fi == idx_dest else 1
        for num in range(inicio, cap + 1):
            c = mapa[fila][num]
            if c != "VAZIO" and c != curso_id_alvo:
                cursos_para_empurrar.append(c)

    for fi, fila in enumerate(filas_ordenadas):
        if fi < idx_dest:
            continue
        cap = capacidades[fila]
        inicio = assento_destino if fi == idx_dest else 1
        for num in range(inicio, cap + 1):
            if mapa[fila][num] != curso_id_alvo:
                mapa[fila][num] = "VAZIO"

    # Coloca o bloco movido, pulando (sem contar) qualquer célula já congelada com o
    # próprio curso_id_alvo — ela permanece exatamente como estava. Ao terminar, fi/num
    # ficam exatamente onde pararam (não pulam pra próxima fileira à toa), pra fase
    # seguinte (empurrar outros cursos) aproveitar o que sobrou da fileira atual.
    restantes = total_curso_alvo
    fi = idx_dest
    num = assento_destino
    while restantes > 0:
        if fi >= len(filas_ordenadas):
            raise ValidationError("Não há espaço suficiente para alocar o curso no destino.")
        fila = filas_ordenadas[fi]
        cap = capacidades[fila]
        if num > cap:
            fi += 1
            num = 1
            continue
        if mapa[fila][num] != curso_id_alvo:
            mapa[fila][num] = curso_id_alvo
            restantes -= 1
        num += 1

    for c in cursos_para_empurrar:
        placed = False
        while not placed:
            if fi >= len(filas_ordenadas):
                raise ValidationError("Não há espaço suficiente para realocar todos os cursos.")
            fila = filas_ordenadas[fi]
            cap = capacidades[fila]
            if num <= cap and mapa[fila][num] == curso_id_alvo:
                num += 1
                continue
            if num <= cap:
                mapa[fila][num] = c
                num += 1
                placed = True
            else:
                fi += 1
                num = 1

    alocacao.alocacoes = []
    for fila in filas_ordenadas:
        cap = capacidades[fila]
        curso_atual = None
        bloco = []
        for num in range(1, cap + 1):
            c = mapa[fila].get(num, "VAZIO")
            if c == curso_atual and c != "VAZIO":
                bloco.append(num)
            else:
                if bloco and curso_atual and curso_atual != "VAZIO":
                    alocacao.alocacoes.append(
                        AlocacaoFila(curso_id=curso_atual, fila_nome=fila, assentos=list(bloco))
                    )
                curso_atual = c
                bloco = [num] if c != "VAZIO" else []
        if bloco and curso_atual and curso_atual != "VAZIO":
            alocacao.alocacoes.append(
                AlocacaoFila(curso_id=curso_atual, fila_nome=fila, assentos=list(bloco))
            )

    return alocacao


@alocacao_bp.route("/<formatura_id>/mover-curso", methods=["PUT"])
def mover_curso(formatura_id):
    try:
        formatura = Formatura.objects.get(id=formatura_id, ativo=True)
    except DoesNotExist:
        return jsonify({"error": "Formatura não encontrada"}), 404

    alocacao = Alocacao.objects(formatura=formatura).first()
    if not alocacao:
        return jsonify({"error": "Alocação não encontrada"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "Body JSON obrigatório"}), 400

    curso_id     = data.get("curso_id")
    origem       = data.get("origem")
    fila_destino = data.get("fila_destino")
    assento_dest = data.get("assento_destino")

    if not curso_id:
        return jsonify({"error": "'curso_id' é obrigatório"}), 400
    if not origem or not isinstance(origem, list):
        return jsonify({"error": "'origem' (lista de trechos) é obrigatório"}), 400
    if not fila_destino:
        return jsonify({"error": "'fila_destino' é obrigatório"}), 400
    if assento_dest is None:
        return jsonify({"error": "'assento_destino' é obrigatório"}), 400

    try:
        assento_dest = int(assento_dest)
        origem_segmentos = [
            {"fila": seg["fila"], "inicio": int(seg["inicio"]), "fim": int(seg["fim"])}
            for seg in origem
        ]
    except (ValueError, TypeError, KeyError):
        return jsonify({"error": "'origem' ou 'assento_destino' em formato inválido"}), 400

    try:
        alocacao = _mover_e_empurrar(
            alocacao, formatura, curso_id, origem_segmentos, fila_destino, assento_dest,
        )
        alocacao.save()
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500

    return jsonify({
        "success": True,
        "alocacao": _payload_alocacao(alocacao, formatura.local, formatura),
    }), 200