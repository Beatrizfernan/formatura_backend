from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from bson import ObjectId
from mongoengine.errors import DoesNotExist, ValidationError, NotUniqueError
from datetime import datetime
import os

from app.models.formatura import Formatura
from app.models.local import Local
from app.models.curso import Curso
from app.models.alocacao import Alocacao
from app.services.planilha_service import PlanilhaService
from app.services.alocacao_service import gerar_alocacao_vertical_corrigida

planilha_bp = Blueprint('planilha', __name__, url_prefix='/api/planilha')

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
                'fila': fila.nome,
                'assentos_vazios': vazios,
                'total_vazios': len(vazios)
            })
    return assentos_vazios


def _deletar_formatura_permanentemente(formatura):
    try:
        Formatura.objects(id=formatura.id).delete()
    except Exception as e:
        print(f"Erro ao deletar formatura: {e}")


@planilha_bp.route('/processar', methods=['POST'])
def processar_planilha():
    formatura = None

    try:
        if 'arquivo' not in request.files:
            return jsonify({'error': 'Arquivo não fornecido'}), 400

        arquivo = request.files['arquivo']

        if arquivo.filename == '':
            return jsonify({'error': 'Nenhum arquivo selecionado'}), 400

        if not allowed_file(arquivo.filename):
            return jsonify({'error': 'Tipo de arquivo não permitido. Use CSV ou Excel'}), 400

        arquivo.seek(0, os.SEEK_END)
        tamanho = arquivo.tell()
        arquivo.seek(0)

        if tamanho > MAX_FILE_SIZE:
            return jsonify({'error': 'Arquivo muito grande (máximo 5MB)'}), 400

        local_id = request.form.get('local_id')
        if not local_id:
            return jsonify({'error': 'ID do local é obrigatório'}), 400

        if not ObjectId.is_valid(local_id):
            return jsonify({'error': 'ID de local inválido'}), 400

        local = Local.objects.get(id=local_id, ativo=True)

        arquivo_bytes = arquivo.read()
        extensao = arquivo.filename.rsplit('.', 1)[1].lower()

        if extensao == 'csv':
            dados_planilha = PlanilhaService.ler_planilha_csv_bytes(arquivo_bytes)
        else:
            dados_planilha = PlanilhaService.ler_planilha_excel_bytes(arquivo_bytes)

        if not dados_planilha['data']:
            return jsonify({'error': 'Data inválida na planilha'}), 400

        if not dados_planilha['cursos']:
            return jsonify({'error': 'Nenhum curso encontrado na planilha'}), 400

        if isinstance(dados_planilha['data'], str):
            data_formatura = datetime.strptime(dados_planilha['data'], '%Y-%m-%d').date()
        else:
            data_formatura = dados_planilha['data']

        cursos_criados = []
        cursos_existentes = []

        for curso_data in dados_planilha['cursos']:
            nome_curso = curso_data['nome']
            sigla = curso_data.get('sigla')
            curso = Curso.buscar_por_nome(nome_curso)

            if not curso:
                curso = Curso(nome=nome_curso)
                if sigla:
                    curso.abreviacao = sigla
                try:
                    curso.save()
                except (ValidationError, NotUniqueError):
                    # Sigla inválida ou já usada por outro curso: cria sem abreviação
                    curso.abreviacao = None
                    curso.save()
                cursos_criados.append(nome_curso)
            else:
                if sigla and curso.abreviacao != sigla:
                    try:
                        curso.abreviacao = sigla
                        curso.save()
                    except (ValidationError, NotUniqueError):
                        pass
                cursos_existentes.append(nome_curso)

            curso_data['curso_id'] = str(curso.id)

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

        if not formatura.capacidade_suficiente:
            _deletar_formatura_permanentemente(formatura)
            return jsonify({
                'error': 'Local não tem capacidade suficiente',
                'assentos_necessarios': formatura.total_assentos_necessarios,
                'assentos_disponiveis': local.total_assentos
            }), 400

        # Usa o novo algoritmo corrigido
        try:
            alocacao = gerar_alocacao_vertical_corrigida(formatura)
            alocacao.save()
        except ValidationError as e:
            _deletar_formatura_permanentemente(formatura)
            return jsonify({'error': 'Erro na alocação', 'detalhes': str(e)}), 400

        formatura.marcar_alocacao_gerada()
        formatura.save()

        # Monta resumo detalhado com curso_id incluído
        resumo_detalhado = []
        for curso_id in alocacao.get_cursos_alocados():
            curso = Curso.get_by_id(curso_id)
            if curso:
                info_curso = alocacao.get_resumo_por_curso()[curso_id]
                resumo_detalhado.append({
                    'curso': curso.nome,
                    'curso_id': curso_id,
                    'abreviacao': curso.abreviacao if curso.abreviacao else curso.nome[:3].upper(),
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
        if formatura:
            _deletar_formatura_permanentemente(formatura)
        return jsonify({'error': 'Erro de validação', 'detalhes': str(e)}), 400
    except Exception as e:
        if formatura:
            _deletar_formatura_permanentemente(formatura)
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Erro ao processar: {str(e)}'}), 500