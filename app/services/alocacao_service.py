"""
Algoritmo de alocação vertical - VERSÃO CORRIGIDA

REGRA CORRETA:
- Preenche coluna por coluna (letra A, B, C...) de cima para baixo (linha 1 → 12)
- Quando um curso NÃO cabe inteiro antes do corredor na coluna atual:
    → O EXCESSO continua na mesma coluna DEPOIS do corredor
    → O PRÓXIMO CURSO começa na PRÓXIMA coluna, linha 1 (antes do corredor)
- Quando um curso CABE inteiro antes do corredor:
    → O próximo curso continua na mesma coluna, no próximo assento disponível
    → Só avança de coluna quando a coluna atual (antes do corredor) esgota
- Espaço depois do corredor de uma coluna que já foi "atravessada" por um curso
  NÃO é reaproveitado por outros cursos — fica vazio (igual ao comportamento do PDF)

RESULTADO: cursos ficam compactos e juntos, sem desperdiçar espaço antes do corredor.
"""

import re
from mongoengine.errors import ValidationError
from app.models.alocacao import Alocacao, AlocacaoFila

LINHA_CORREDOR = 12


def _organizar_filas(local):
    """
    Retorna dict ordenado por letra:
    {
      'A': {
        'antes': [{'nome': '1A', 'numero': 1, 'capacidade': 24, 'assento_atual': 1}, ...],
        'depois': [{'nome': '13A', ...}, ...]
      },
      'B': { ... },
      ...
    }
    """
    filas_por_letra = {}

    for fila in local.filas_ordenadas:
        m = re.match(r'^(\d+)([A-Z]+)$', fila.nome)
        if not m:
            continue
        numero = int(m.group(1))
        letra = m.group(2)

        if letra not in filas_por_letra:
            filas_por_letra[letra] = {'antes': [], 'depois': []}

        info = {
            'nome': fila.nome,
            'numero': numero,
            'capacidade': fila.quantidade_assentos,
            'assento_atual': 1,
        }

        if numero <= LINHA_CORREDOR:
            filas_por_letra[letra]['antes'].append(info)
        else:
            filas_por_letra[letra]['depois'].append(info)

    for letra in filas_por_letra:
        filas_por_letra[letra]['antes'].sort(key=lambda f: f['numero'])
        filas_por_letra[letra]['depois'].sort(key=lambda f: f['numero'])

    return filas_por_letra


def _espaco_disponivel_antes(filas_antes):
    """Calcula total de assentos disponíveis (em pares) antes do corredor nessa coluna."""
    total = 0
    for f in filas_antes:
        disp = f['capacidade'] - f['assento_atual'] + 1
        total += (disp // 2) * 2
    return total


def _alocar_em_filas(filas_lista, quantidade, curso_id, alocacao):
    """
    Aloca `quantidade` assentos sequencialmente nas filas da lista.
    Retorna quantos ainda faltam (0 se alocou tudo).
    Modifica assento_atual das filas in-place.
    """
    restantes = quantidade

    for fila in filas_lista:
        if restantes <= 0:
            break

        inicio = fila['assento_atual']
        disp = fila['capacidade'] - inicio + 1
        if disp <= 0:
            continue

        # Garante pares
        pares = min(disp // 2, restantes // 2)
        if pares == 0:
            continue

        a_alocar = pares * 2
        assentos = list(range(inicio, inicio + a_alocar))

        alocacao.adicionar_alocacao_fila(
            curso_id=curso_id,
            fila_nome=fila['nome'],
            assentos=assentos,
        )

        fila['assento_atual'] += a_alocar
        restantes -= a_alocar

    return restantes


def gerar_alocacao_vertical_corrigida(formatura):
    """
    Algoritmo principal.

    Estado mantido entre cursos:
      - letra_idx: qual coluna estamos usando antes do corredor
      - dentro de cada coluna, assento_atual de cada fila persiste entre cursos
        (para cursos consecutivos que compartilham a mesma coluna)
      - quando um curso transborda para depois do corredor, a coluna depois
        fica "bloqueada" para aquele curso, e o próximo começa em letra_idx+1
    """
    alocacao = Alocacao(
        formatura=formatura,
        local=formatura.local,
        observacoes='Alocação vertical - cursos compactos, excesso passa ao corredor na mesma coluna',
    )

    filas_por_letra = _organizar_filas(formatura.local)
    letras = sorted(filas_por_letra.keys())

    if not letras:
        raise ValidationError('Nenhuma fila válida encontrada no local.')

    letra_idx = 0  # coluna atual (antes do corredor)

    for curso_formatura in formatura.cursos:
        curso_id = curso_formatura.curso_id
        necessarios = curso_formatura.qtd_assentos

        if necessarios % 2 != 0:
            raise ValidationError(
                f'Curso {curso_id} tem {necessarios} assentos (número ímpar). '
                f'Cada formando ocupa 2 assentos (formando + acompanhante).'
            )

        restantes = necessarios

        while restantes > 0:
            # Avança colunas que não têm mais espaço antes do corredor
            while letra_idx < len(letras):
                letra = letras[letra_idx]
                if _espaco_disponivel_antes(filas_por_letra[letra]['antes']) > 0:
                    break
                letra_idx += 1

            if letra_idx >= len(letras):
                raise ValidationError(
                    f'Não há espaço suficiente no local. '
                    f'Faltam {restantes} assentos para alocar todos os cursos.'
                )

            letra = letras[letra_idx]
            filas_antes = filas_por_letra[letra]['antes']
            filas_depois = filas_por_letra[letra]['depois']

            # Tenta alocar antes do corredor
            restantes = _alocar_em_filas(filas_antes, restantes, curso_id, alocacao)

            if restantes > 0:
                # Curso não coube — excesso vai para DEPOIS do corredor na MESMA coluna
                restantes = _alocar_em_filas(filas_depois, restantes, curso_id, alocacao)

                # Independente de ter cabido ou não depois,
                # marca a coluna como "usada" para este curso atravessado
                # → próximo curso começa na próxima coluna antes do corredor
                letra_idx += 1

            # Se restantes ainda > 0 depois de esgotar antes+depois desta coluna,
            # o while externo vai tentar a próxima coluna

        # Se o curso coube inteiro antes do corredor (restantes == 0 sem transbordar),
        # NÃO avança letra_idx — o próximo curso continua na mesma coluna

    return alocacao