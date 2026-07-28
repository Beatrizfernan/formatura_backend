"""
Rotas de alocação:
  GET  /api/alocacao/<formatura_id>                → carrega alocação atual
  PUT  /api/alocacao/<formatura_id>/reordenar      → recebe nova ordem dos cursos, realoca do zero
  PUT  /api/alocacao/<formatura_id>/mover-curso    → move curso manualmente (assento a assento)
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

def _mover_e_empurrar(alocacao, formatura, curso_id_alvo, fila_destino, assento_destino):
    local = formatura.local
    capacidades = {f.nome: f.quantidade_assentos for f in local.filas_ordenadas}
    filas_ordenadas = _ordenar_filas(capacidades)

    if fila_destino not in capacidades:
        raise ValidationError(f"Fila '{fila_destino}' não existe neste local.")
    if assento_destino < 1 or assento_destino > capacidades[fila_destino]:
        raise ValidationError(f"Assento {assento_destino} inválido para fila '{fila_destino}'.")

    total_curso_alvo = sum(
        len(af.assentos) for af in alocacao.alocacoes if af.curso_id == curso_id_alvo
    )
    if total_curso_alvo == 0:
        raise ValidationError(f"Curso '{curso_id_alvo}' não encontrado nesta alocação.")

    mapa = {f: {} for f in filas_ordenadas}
    for af in alocacao.alocacoes:
        if af.fila_nome in mapa:
            for num in af.assentos:
                mapa[af.fila_nome][num] = af.curso_id

    for fila, cap in capacidades.items():
        for i in range(1, cap + 1):
            if i not in mapa[fila]:
                mapa[fila][i] = "VAZIO"

    for fila in filas_ordenadas:
        for num in list(mapa[fila].keys()):
            if mapa[fila][num] == curso_id_alvo:
                mapa[fila][num] = "VAZIO"

    idx_dest = filas_ordenadas.index(fila_destino)

    cursos_para_empurrar = []
    for fi, fila in enumerate(filas_ordenadas):
        if fi < idx_dest:
            continue
        cap = capacidades[fila]
        inicio = assento_destino if fi == idx_dest else 1
        for num in range(inicio, cap + 1):
            c = mapa[fila][num]
            if c != "VAZIO":
                cursos_para_empurrar.append(c)

    for fi, fila in enumerate(filas_ordenadas):
        if fi < idx_dest:
            continue
        cap = capacidades[fila]
        inicio = assento_destino if fi == idx_dest else 1
        for num in range(inicio, cap + 1):
            mapa[fila][num] = "VAZIO"

    restantes = total_curso_alvo
    fi = idx_dest
    num = assento_destino
    while restantes > 0:
        if fi >= len(filas_ordenadas):
            raise ValidationError("Não há espaço suficiente para alocar o curso no destino.")
        fila = filas_ordenadas[fi]
        cap = capacidades[fila]
        while num <= cap and restantes > 0:
            mapa[fila][num] = curso_id_alvo
            restantes -= 1
            num += 1
        fi += 1
        num = 1

    for c in cursos_para_empurrar:
        placed = False
        while not placed:
            if fi >= len(filas_ordenadas):
                raise ValidationError("Não há espaço suficiente para realocar todos os cursos.")
            fila = filas_ordenadas[fi]
            cap = capacidades[fila]
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
    fila_destino = data.get("fila_destino")
    assento_dest = data.get("assento_destino")

    if not curso_id:
        return jsonify({"error": "'curso_id' é obrigatório"}), 400
    if not fila_destino:
        return jsonify({"error": "'fila_destino' é obrigatório"}), 400
    if assento_dest is None:
        return jsonify({"error": "'assento_destino' é obrigatório"}), 400

    try:
        assento_dest = int(assento_dest)
    except (ValueError, TypeError):
        return jsonify({"error": "'assento_destino' deve ser inteiro"}), 400

    try:
        alocacao = _mover_e_empurrar(alocacao, formatura, curso_id, fila_destino, assento_dest)
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