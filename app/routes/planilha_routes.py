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
    """Calcula quais assentos ficaram vazios em cada fila"""
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


def _deletar_formatura_permanentemente(formatura):
    """Deleta uma formatura permanentemente do banco"""
    try:
        Formatura.objects(id=formatura.id).delete()
    except Exception as e:
        print(f"Erro ao deletar formatura: {e}")


def _gerar_alocacao_vertical_compartilhada(formatura):
    """
    Aloca TODOS OS CURSOS de forma VERTICAL e COMPARTILHADA
    
    NOVA LÓGICA:
    1. Preenche VERTICALMENTE (mesma letra) 
    2. Preenche PRIMEIRO todas as filas de 1-12 (antes do corredor)
    3. Após o corredor:
       - Cursos que começam ANTES do corredor continuam na MESMA COLUNA
       - Novos cursos preenchem da DIREITA para ESQUERDA (D → C → B → A)
    """
    
    alocacao = Alocacao(
        formatura=formatura,
        local=formatura.local,
        observacoes='Alocação vertical compartilhada - Cursos atravessam corredor na mesma coluna'
    )
    
    # Organiza filas por letra, depois por número
    import re
    filas_por_letra = {}
    
    for fila in formatura.local.filas_ordenadas:
        match = re.match(r'^(\d+)([A-Z]+)$', fila.nome)
        if match:
            numero = int(match.group(1))
            letra = match.group(2)
            
            if letra not in filas_por_letra:
                filas_por_letra[letra] = []
            
            filas_por_letra[letra].append({
                'nome': fila.nome,
                'numero': numero,
                'capacidade': fila.quantidade_assentos,
                'assento_atual': 1
            })
    
    # Ordena cada coluna por número
    for letra in filas_por_letra:
        filas_por_letra[letra].sort(key=lambda f: f['numero'])
    
    # Separa filas ANTES e DEPOIS do corredor
    LINHA_CORREDOR = 12
    
    filas_antes_corredor = {}
    filas_depois_corredor = {}
    
    for letra, filas_lista in filas_por_letra.items():
        filas_antes_corredor[letra] = [f for f in filas_lista if f['numero'] <= LINHA_CORREDOR]
        filas_depois_corredor[letra] = [f for f in filas_lista if f['numero'] > LINHA_CORREDOR]
    
    # Remove letras vazias
    filas_antes_corredor = {k: v for k, v in filas_antes_corredor.items() if v}
    filas_depois_corredor = {k: v for k, v in filas_depois_corredor.items() if v}
    
    # Cria lista ordenada de letras
    letras_antes = sorted(filas_antes_corredor.keys())
    letras_depois = sorted(filas_depois_corredor.keys(), reverse=True)  # INVERTIDO: D → C → B → A
    
    # Estado global
    regiao_atual = 'antes'
    letra_atual_index = 0
    fila_atual_index = 0
    
    # Rastreia qual letra cada curso está usando
    curso_letra_map = {}
    
    # Processa cada curso sequencialmente
    for curso_formatura in formatura.cursos:
        assentos_necessarios = curso_formatura.qtd_assentos
        curso_id = curso_formatura.curso_id
        
        # Validação: deve ser par
        if assentos_necessarios % 2 != 0:
            raise ValidationError(
                f'Curso {curso_id} com {assentos_necessarios} assentos (ímpar). '
                f'Cada curso deve ter número PAR de assentos.'
            )
        
        # Aloca este curso
        while assentos_necessarios > 0:
            # Escolhe a região atual
            if regiao_atual == 'antes':
                letras_disponiveis = letras_antes
                filas_regiao = filas_antes_corredor
            else:
                # DEPOIS DO CORREDOR
                # Verifica se o curso já tinha começado antes
                if curso_id in curso_letra_map:
                    # Continua na MESMA COLUNA
                    letra_continua = curso_letra_map[curso_id]
                    if letra_continua in filas_depois_corredor:
                        letras_disponiveis = [letra_continua]
                        letra_atual_index = 0
                    else:
                        # Letra não existe após corredor, usar comportamento normal
                        letras_disponiveis = letras_depois
                else:
                    # Novo curso após corredor: preenche da DIREITA para ESQUERDA
                    letras_disponiveis = letras_depois
                
                filas_regiao = filas_depois_corredor
            
            # Verifica se acabaram as letras nesta região
            if letra_atual_index >= len(letras_disponiveis):
                if regiao_atual == 'antes':
                    # Muda para região DEPOIS do corredor
                    regiao_atual = 'depois'
                    letra_atual_index = 0
                    fila_atual_index = 0
                    
                    # Se não há filas depois do corredor, erro
                    if not letras_depois:
                        raise ValidationError(
                            f'Não há espaço suficiente no local. Faltam {assentos_necessarios} assentos.'
                        )
                    continue
                else:
                    # Acabou tudo
                    raise ValidationError(
                        f'Não há espaço suficiente no local. Faltam {assentos_necessarios} assentos.'
                    )
            
            letra_atual = letras_disponiveis[letra_atual_index]
            filas_letra = filas_regiao[letra_atual]
            
            # Registra que este curso está usando esta letra (se estamos antes do corredor)
            if regiao_atual == 'antes':
                curso_letra_map[curso_id] = letra_atual
            
            # Verifica se acabaram as filas desta letra
            if fila_atual_index >= len(filas_letra):
                # Vai para próxima letra na mesma região
                letra_atual_index += 1
                fila_atual_index = 0
                continue
            
            fila = filas_letra[fila_atual_index]
            assento_inicial = fila['assento_atual']
            
            # Calcula espaço disponível nesta fila
            assentos_disponiveis = fila['capacidade'] - assento_inicial + 1
            
            # Sempre em pares
            pares_disponiveis = assentos_disponiveis // 2
            assentos_disponiveis_pares = pares_disponiveis * 2
            
            if assentos_disponiveis_pares == 0:
                # Fila cheia, vai para próxima
                fila_atual_index += 1
                continue
            
            # Quanto alocar nesta fila
            pares_necessarios = assentos_necessarios // 2
            pares_a_alocar = min(pares_disponiveis, pares_necessarios)
            assentos_a_alocar = pares_a_alocar * 2
            
            # Cria lista de assentos
            assentos_alocados = list(range(
                assento_inicial,
                assento_inicial + assentos_a_alocar
            ))
            
            # Adiciona alocação
            alocacao.adicionar_alocacao_fila(
                curso_id=curso_formatura.curso_id,
                fila_nome=fila['nome'],
                assentos=assentos_alocados
            )
            
            # Atualiza estado
            assentos_necessarios -= assentos_a_alocar
            fila['assento_atual'] += assentos_a_alocar
            
            # Se encheu a fila, vai para próxima
            if fila['assento_atual'] > fila['capacidade']:
                fila_atual_index += 1
    
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
    formatura = None
    
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
            _deletar_formatura_permanentemente(formatura)
            return jsonify({
                'error': 'Local não tem capacidade suficiente',
                'assentos_necessarios': formatura.total_assentos_necessarios,
                'assentos_disponiveis': local.total_assentos
            }), 400
        
        # Gera alocação VERTICAL COMPARTILHADA (cursos atravessam corredor na mesma coluna)
        try:
            alocacao = _gerar_alocacao_vertical_compartilhada(formatura)
            alocacao.save()
        except ValidationError as e:
            _deletar_formatura_permanentemente(formatura)
            return jsonify({
                'error': 'Erro na alocação',
                'detalhes': str(e)
            }), 400
        
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
            'message': 'Formatura e alocação criadas com sucesso (cursos atravessam corredor na mesma coluna)',
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