"""
Rota para geração e download de PDF do mapa de assentos

✨ ATUALIZADO: Agora passa as abreviações dos cursos para o PDF
"""

from flask import Blueprint, jsonify, send_file, request
from mongoengine.errors import DoesNotExist
from datetime import datetime
from io import BytesIO

from app.models.alocacao import Alocacao
from app.models.formatura import Formatura
from app.models.local import Local
from app.models.curso import Curso
from app.services.pdf_service import gerar_pdf_mapa_assentos

pdf_bp = Blueprint('pdf', __name__, url_prefix='/api/pdf')


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


@pdf_bp.route('/mapa-assentos/<formatura_id>', methods=['GET'])
def download_pdf_mapa(formatura_id):
    """
    Gera e retorna PDF do mapa de assentos para download
    
    GET /api/pdf/mapa-assentos/<formatura_id>
    
    Returns:
        PDF file (application/pdf)
    """
    try:
        # Busca formatura
        formatura = Formatura.objects.get(id=formatura_id, ativo=True)
        
        # Busca alocação
        alocacao = Alocacao.objects(formatura=formatura).first()
        
        if not alocacao:
            return jsonify({'error': 'Alocação não encontrada para esta formatura'}), 404
        
        # Prepara dados para o PDF
        local = formatura.local
        
        # ✨ NOVO: Monta resumo detalhado por curso COM ABREVIAÇÃO
        resumo_detalhado = []
        for curso_id in alocacao.get_cursos_alocados():
            curso = Curso.get_by_id(curso_id)
            if curso:
                info_curso = alocacao.get_resumo_por_curso()[curso_id]
                resumo_detalhado.append({
                    'curso': curso.nome,
                    'abreviacao': curso.abreviacao if curso.abreviacao else curso.nome[:3].upper(),  # ✨ NOVO
                    'total_assentos': info_curso['total_assentos'],
                    'filas': info_curso['detalhes_filas']
                })
        
        # Calcula assentos vazios
        assentos_vazios = _calcular_assentos_vazios(local, alocacao)
        
        # Prepara dados
        dados_pdf = {
            'nome_formatura': formatura.nome,
            'local': local.nome,
            'data_formatura': formatura.data.strftime('%d/%m/%Y'),
            'detalhes': resumo_detalhado,
            'assentos_vazios': assentos_vazios
        }
        
        # Gera PDF
        pdf_buffer = gerar_pdf_mapa_assentos(dados_pdf)
        
        # Nome do arquivo
        nome_arquivo = f"mapa-assentos-{formatura.nome.replace(' ', '-')}.pdf"
        
        # Retorna PDF
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=nome_arquivo
        )
        
    except DoesNotExist:
        return jsonify({'error': 'Formatura não encontrada'}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()  # Debug
        return jsonify({'error': f'Erro ao gerar PDF: {str(e)}'}), 500


@pdf_bp.route('/mapa-assentos/preview/<formatura_id>', methods=['GET'])
def preview_pdf_mapa(formatura_id):
    """
    Gera e retorna PDF para visualização inline (sem download)
    
    GET /api/pdf/mapa-assentos/preview/<formatura_id>
    """
    try:
        formatura = Formatura.objects.get(id=formatura_id, ativo=True)
        alocacao = Alocacao.objects(formatura=formatura).first()
        
        if not alocacao:
            return jsonify({'error': 'Alocação não encontrada'}), 404
        
        local = formatura.local
        
        # ✨ NOVO: Monta resumo detalhado por curso COM ABREVIAÇÃO
        resumo_detalhado = []
        for curso_id in alocacao.get_cursos_alocados():
            curso = Curso.get_by_id(curso_id)
            if curso:
                info_curso = alocacao.get_resumo_por_curso()[curso_id]
                resumo_detalhado.append({
                    'curso': curso.nome,
                    'abreviacao': curso.abreviacao if curso.abreviacao else curso.nome[:3].upper(),  # ✨ NOVO
                    'total_assentos': info_curso['total_assentos'],
                    'filas': info_curso['detalhes_filas']
                })
        
        assentos_vazios = _calcular_assentos_vazios(local, alocacao)
        
        dados_pdf = {
            'nome_formatura': formatura.nome,
            'local': local.nome,
            'data_formatura': formatura.data.strftime('%d/%m/%Y'),
            'detalhes': resumo_detalhado,
            'assentos_vazios': assentos_vazios
        }
        
        pdf_buffer = gerar_pdf_mapa_assentos(dados_pdf)
        
        # Retorna inline (para visualização no navegador)
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=False
        )
        
    except DoesNotExist:
        return jsonify({'error': 'Formatura não encontrada'}), 404
    except Exception as e:
        import traceback
        traceback.print_exc()  # Debug
        return jsonify({'error': f'Erro ao gerar PDF: {str(e)}'}), 500