from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from bson import ObjectId
from mongoengine.errors import DoesNotExist, ValidationError
from datetime import datetime
import os
import pandas as pd
from io import BytesIO

from app.models.formatura import Formatura
from app.models.local import Local
from app.models.curso import Curso
from app.models.alocacao import Alocacao
from app.services.planilha_service import PlanilhaService

planilha_bp = Blueprint('planilha', __name__, url_prefix='/api/planilha')

# Configuração
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def allowed_file(filename):
    """Verifica se a extensão do arquivo é permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _calcular_assentos_vazios(local, alocacao):
    """
    Calcula quais assentos ficaram vazios em cada fila
    """
    assentos_vazios = []
    
    for fila in local.filas_ordenadas:
        assentos_ocupados = set()
        
        for alocacao_fila in alocacao.alocacoes:
            if alocacao_fila.fila_nome == fila.nome:
                assentos_ocupados.update(alocacao_fila.assentos)
        
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
    Processa arquivo CSV/Excel enviado como upload
    
    POST /api/planilha/processar
    FormData:
    - arquivo: File (CSV ou Excel)
    - local_id: string (ID do local)
    """
    try:
        # Validação: arquivo obrigatório
        if 'arquivo' not in request.files:
            return jsonify({'error': 'Arquivo não fornecido'}), 400
        
        arquivo = request.files['arquivo']
        
        # Validação: nome do arquivo
        if arquivo.filename == '':
            return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
        
        # Validação: extensão
        if not allowed_file(arquivo.filename):
            return jsonify({'error': 'Tipo de arquivo não permitido. Use CSV ou Excel'}), 400
        
        # Validação: tamanho
        arquivo.seek(0, os.SEEK_END)
        tamanho = arquivo.tell()
        arquivo.seek(0)
        
        if tamanho > MAX_FILE_SIZE:
            return jsonify({'error': 'Arquivo muito grande (máximo 5MB)'}), 400
        
        # Validação: local_id obrigatório
        local_id = request.form.get('local_id')
        if not local_id:
            return jsonify({'error': 'ID do local é obrigatório'}), 400
        
        if not ObjectId.is_valid(local_id):
            return jsonify({'error': 'ID de local inválido'}), 400
        
        # Busca local
        local = Local.objects.get(id=local_id, ativo=True)
        
        # Lê o arquivo
        arquivo_bytes = arquivo.read()
        
        # Processa baseado na extensão
        extensao = arquivo.filename.rsplit('.', 1)[1].lower()
        
        if extensao == 'csv':
            dados_planilha = PlanilhaService.ler_planilha_csv_bytes(arquivo_bytes)
        else:
            # Excel (.xlsx ou .xls)
            dados_planilha = PlanilhaService.ler_planilha_excel_bytes(arquivo_bytes)
        
        # Validações
        if not dados_planilha['data']:
            return jsonify({'error': 'Data inválida na planilha'}), 400
        
        if not dados_planilha['cursos']:
            return jsonify({'error': 'Nenhum curso encontrado na planilha'}), 400
        
        # Converte data
        if isinstance(dados_planilha['data'], str):
            data_formatura = datetime.strptime(dados_planilha['data'], '%Y-%m-%d').date()
        else:
            data_formatura = dados_planilha['data']
        
        # VERIFICAÇÃO DE DUPLICATA
        # formatura_existente = Formatura.objects(
        #     nome=dados_planilha['nome_formatura'],
        #     data=data_formatura,
        #     local=local,
        #     ativo=True
        # ).first()
        
        # if formatura_existente:
        #     alocacao_existente = Alocacao.objects(formatura=formatura_existente).first()
            
        #     resumo_detalhado = []
        #     if alocacao_existente:
        #         for curso_id in alocacao_existente.get_cursos_alocados():
        #             curso = Curso.get_by_id(curso_id)
        #             if curso:
        #                 info_curso = alocacao_existente.get_resumo_por_curso()[curso_id]
        #                 resumo_detalhado.append({
        #                     'curso': curso.nome,
        #                     'total_assentos': info_curso['total_assentos'],
        #                     'filas': info_curso['detalhes_filas']
        #                 })
            
        #     assentos_vazios = _calcular_assentos_vazios(local, alocacao_existente) if alocacao_existente else []
            
        #     return jsonify({
        #         'success': True,
        #         'message': 'Formatura já existe - retornando dados existentes',
        #         'ja_existia': True,
        #         'formatura': {
        #             'id': str(formatura_existente.id),
        #             'nome': formatura_existente.nome,
        #             'data': formatura_existente.data.isoformat(),
        #             'local': local.nome,
        #             'total_formandos': formatura_existente.total_formandos,
        #             'total_assentos': formatura_existente.total_assentos_necessarios
        #         },
        #         'alocacao': {
        #             'id': str(alocacao_existente.id) if alocacao_existente else None,
        #             'total_alocado': alocacao_existente.total_assentos_alocados if alocacao_existente else 0,
        #             'taxa_ocupacao': f"{round(alocacao_existente.taxa_ocupacao, 2)}%" if alocacao_existente else "0%",
        #             'detalhes': resumo_detalhado,
        #             'assentos_vazios': assentos_vazios
        #         } if alocacao_existente else None
        #     }), 200
        
        # Processa cursos
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
        
        assentos_vazios = _calcular_assentos_vazios(formatura.local, alocacao)
        
        return jsonify({
            'success': True,
            'message': 'Formatura e alocação criadas com sucesso',
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
        return jsonify({'error': f'Erro ao processar: {str(e)}'}), 500