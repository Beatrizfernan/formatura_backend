from flask import Blueprint, request, jsonify
from bson import ObjectId
from mongoengine.errors import DoesNotExist, ValidationError
from datetime import datetime

from app.models.formatura import Formatura
from app.models.local import Local
from app.models.curso import Curso
from app.models.alocacao import Alocacao
from app.services.planilha_service import PlanilhaService

planilha_bp = Blueprint('planilha', __name__, url_prefix='/api/planilha')


def _calcular_assentos_vazios(local, alocacao):
    """
    Calcula quais assentos ficaram vazios em cada fila
    
    Retorna:
    [
        {
            "fila": "1A",
            "assentos_vazios": [15, 16],
            "total_vazios": 2
        }
    ]
    """
    assentos_vazios = []
    
    for fila in local.filas_ordenadas:
        # Pega todos os assentos alocados nesta fila
        assentos_ocupados = set()
        
        for alocacao_fila in alocacao.alocacoes:
            if alocacao_fila.fila_nome == fila.nome:
                assentos_ocupados.update(alocacao_fila.assentos)
        
        # Calcula os vazios
        todos_assentos = set(range(1, fila.quantidade_assentos + 1))
        vazios = sorted(todos_assentos - assentos_ocupados)
        
        if vazios:
            assentos_vazios.append({
                'fila': fila.nome,
                'assentos_vazios': vazios,
                'total_vazios': len(vazios)
            })
    
    return assentos_vazios


def _gerar_alocacao_sequencial(formatura):
    """
    Aloca sequencialmente pela ORDEM das filas
    """
    alocacao = Alocacao(
        formatura=formatura,
        local=formatura.local,
        observacoes='Alocação gerada automaticamente - Sequencial por ordem de filas'
    )
    
    filas = formatura.local.filas_ordenadas
    assento_atual = 1
    fila_index = 0
    
    for curso_formatura in formatura.cursos:
        assentos_necessarios = curso_formatura.qtd_assentos
        
        while assentos_necessarios > 0 and fila_index < len(filas):
            fila = filas[fila_index]
            assentos_disponiveis_na_fila = fila.quantidade_assentos - assento_atual + 1
            quantidade_a_alocar = min(assentos_necessarios, assentos_disponiveis_na_fila)
            assentos_alocados = list(range(assento_atual, assento_atual + quantidade_a_alocar))
            
            alocacao.adicionar_alocacao_fila(
                curso_id=curso_formatura.curso_id,
                fila_nome=fila.nome,
                assentos=assentos_alocados
            )
            
            assentos_necessarios -= quantidade_a_alocar
            assento_atual += quantidade_a_alocar
            
            if assento_atual > fila.quantidade_assentos:
                fila_index += 1
                assento_atual = 1
    
    return alocacao


@planilha_bp.route('/processar', methods=['POST'])
def processar_planilha():
    """
    Processa planilha CSV e cria formatura + alocação sequencial
    
    POST /api/planilha/processar
    Body:
    {
        "planilha_url": "https://docs.google.com/spreadsheets/d/{ID}/export?format=csv",
        "local_id": "68d9878ab55edbcd99f79214",
        "sobrescrever": false  // opcional - se true, deleta formatura existente
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'planilha_url' not in data:
            return jsonify({'error': 'URL da planilha é obrigatória'}), 400
        
        if 'local_id' not in data:
            return jsonify({'error': 'ID do local é obrigatório'}), 400
        
        planilha_url = data['planilha_url']
        local_id = data['local_id']
        sobrescrever = data.get('sobrescrever', False)
        
        if not ObjectId.is_valid(local_id):
            return jsonify({'error': 'ID de local inválido'}), 400
        
        # Busca local
        local = Local.objects.get(id=local_id, ativo=True)
        
        # Lê planilha
        dados_planilha = PlanilhaService.ler_planilha_csv(planilha_url)
        
        if not dados_planilha['data']:
            return jsonify({'error': 'Data inválida na planilha'}), 400
        
        if not dados_planilha['cursos']:
            return jsonify({'error': 'Nenhum curso encontrado na planilha'}), 400
        
        # Converte data
        data_formatura = datetime.strptime(dados_planilha['data'], '%Y-%m-%d').date()
        
        # VERIFICAÇÃO DE DUPLICATA
        formatura_existente = Formatura.objects(
            nome=dados_planilha['nome_formatura'],
            data=data_formatura,
            local=local,
            ativo=True
        ).first()
        
        if formatura_existente:
            if not sobrescrever:
                # Busca alocação existente
                alocacao_existente = Alocacao.objects(formatura=formatura_existente).first()
                
                # Monta resumo detalhado
                resumo_detalhado = []
                if alocacao_existente:
                    for curso_id in alocacao_existente.get_cursos_alocados():
                        curso = Curso.get_by_id(curso_id)
                        if curso:
                            info_curso = alocacao_existente.get_resumo_por_curso()[curso_id]
                            resumo_detalhado.append({
                                'curso': curso.nome,
                                'total_assentos': info_curso['total_assentos'],
                                'filas': info_curso['detalhes_filas']
                            })
                
                # Calcula assentos vazios
                assentos_vazios = _calcular_assentos_vazios(local, alocacao_existente) if alocacao_existente else []
                
                return jsonify({
                    'success': True,
                    'message': 'Formatura já existe - retornando dados existentes',
                    'ja_existia': True,
                    'formatura': {
                        'id': str(formatura_existente.id),
                        'nome': formatura_existente.nome,
                        'data': formatura_existente.data.isoformat(),
                        'local': local.nome,
                        'total_formandos': formatura_existente.total_formandos,
                        'total_assentos': formatura_existente.total_assentos_necessarios
                    },
                    'alocacao': {
                        'id': str(alocacao_existente.id) if alocacao_existente else None,
                        'total_alocado': alocacao_existente.total_assentos_alocados if alocacao_existente else 0,
                        'taxa_ocupacao': f"{round(alocacao_existente.taxa_ocupacao, 2)}%" if alocacao_existente else "0%",
                        'detalhes': resumo_detalhado,
                        'assentos_vazios': assentos_vazios
                    } if alocacao_existente else None
                }), 200
            else:
                # Deleta formatura e alocação antigas
                alocacao_antiga = Alocacao.objects(formatura=formatura_existente).first()
                if alocacao_antiga:
                    alocacao_antiga.delete(hard_delete=True)
                
                formatura_existente.delete(hard_delete=True)
        
        # Processa cursos (busca ou cria)
        cursos_criados = []
        cursos_existentes = []
        
        for curso_data in dados_planilha['cursos']:
            nome_curso = curso_data['nome']
            curso = Curso.buscar_por_nome(nome_curso)
            
            if not curso:
                curso = Curso(nome=nome_curso)
                curso.save()
                cursos_criados.append(nome_curso)
            else:
                cursos_existentes.append(nome_curso)
            
            curso_data['curso_id'] = str(curso.id)
        
        # Cria formatura
        formatura = Formatura(
            nome=dados_planilha['nome_formatura'],
            data=data_formatura,
            local=local,
            status='planejamento'
        )
        
        for curso_data in dados_planilha['cursos']:
            formatura.adicionar_curso(
                curso_id=curso_data['curso_id'],
                qtd_formandos=curso_data['qtd_formandos']
            )
        
        formatura.save()
        
        # Verifica capacidade
        if not formatura.capacidade_suficiente:
            formatura.delete(hard_delete=True)
            return jsonify({
                'error': 'Local não tem capacidade suficiente',
                'assentos_necessarios': formatura.total_assentos_necessarios,
                'assentos_disponiveis': local.total_assentos
            }), 400
        
        # Gera alocação
        alocacao = _gerar_alocacao_sequencial(formatura)
        alocacao.save()
        
        formatura.marcar_alocacao_gerada()
        formatura.save()
        
        # Monta resumo detalhado
        resumo_detalhado = []
        for curso_id in alocacao.get_cursos_alocados():
            curso = Curso.get_by_id(curso_id)
            if curso:
                info_curso = alocacao.get_resumo_por_curso()[curso_id]
                resumo_detalhado.append({
                    'curso': curso.nome,
                    'total_assentos': info_curso['total_assentos'],
                    'filas': info_curso['detalhes_filas']
                })
        
        # Calcula assentos vazios por fila
        assentos_vazios = _calcular_assentos_vazios(formatura.local, alocacao)
        
        return jsonify({
            'success': True,
            'message': 'Formatura e alocação criadas com sucesso' + (' (substituindo anterior)' if sobrescrever else ''),
            'ja_existia': False,
            'processamento': {
                'cursos_criados': cursos_criados,
                'cursos_existentes': cursos_existentes,
                'total_cursos': len(dados_planilha['cursos'])
            },
            'formatura': {
                'id': str(formatura.id),
                'nome': formatura.nome,
                'data': formatura.data.isoformat(),
                'local': local.nome,
                'total_formandos': formatura.total_formandos,
                'total_assentos': formatura.total_assentos_necessarios
            },
            'alocacao': {
                'id': str(alocacao.id),
                'total_alocado': alocacao.total_assentos_alocados,
                'taxa_ocupacao': f"{round(alocacao.taxa_ocupacao, 2)}%",
                'detalhes': resumo_detalhado,
                'assentos_vazios': assentos_vazios
            }
        }), 201
        
    except DoesNotExist:
        return jsonify({'error': 'Local não encontrado'}), 404
    except ValidationError as e:
        return jsonify({'error': 'Erro de validação', 'detalhes': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500