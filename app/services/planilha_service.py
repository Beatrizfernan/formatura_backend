import csv
import requests
from io import StringIO
from typing import Dict, List, Tuple
from datetime import datetime

class PlanilhaService:
    
    @staticmethod
    def ler_planilha_csv(url: str) -> Dict:
        """Lê planilha CSV do Google Sheets"""
        try:
            response = requests.get(url)
            response.encoding = "utf-8"
            csv_text = StringIO(response.text)
            reader = csv.reader(csv_text)
            
            dados = [row for row in reader]
            return PlanilhaService._processar_dados_csv(dados)
            
        except Exception as e:
            raise Exception(f'Erro ao ler planilha: {str(e)}')
    
    @staticmethod
    def _processar_dados_csv(dados: List[List[str]]) -> Dict:
        """
        Formato:
        Linha 0: "26/08/2025 - FAMED; FFOE; ICA"
        Linha 1: Headers (Unidade | Curso | QTD | EFETIVO)
        Linha 2+: Dados
        """
        if not dados or len(dados) < 3:
            raise ValueError('Planilha não contém dados suficientes')
        
        primeira_linha = dados[0][0] if dados[0] and len(dados[0]) > 0 else ""
        nome_formatura, data_formatura = PlanilhaService._extrair_nome_data(primeira_linha)
        
        cursos = PlanilhaService._processar_cursos(dados[2:])
        
        return {
            'nome_formatura': nome_formatura,
            'data': data_formatura,
            'cursos': cursos
        }
    
    @staticmethod
    def _extrair_nome_data(texto: str) -> Tuple[str, str]:
        """Extrai nome e data: "26/08/2025 - FAMED; FFOE; ICA" """
        partes = texto.split(' - ')
        data_str = partes[0].strip() if len(partes) > 0 else ""
        unidades = partes[1].strip() if len(partes) > 1 else "Formatura"
        
        data_formatura = None
        if data_str:
            try:
                data_obj = datetime.strptime(data_str, '%d/%m/%Y')
                data_formatura = data_obj.strftime('%Y-%m-%d')
            except:
                pass
        
        return f"Formatura {unidades}", data_formatura
    
    @staticmethod
    def _processar_cursos(linhas: List[List[str]]) -> List[Dict]:
        """
        Processa: [Unidade, Curso, QTD, EFETIVO]
        """
        cursos = []
        
        for row in linhas:
            if not row or len(row) < 3:
                continue
            
            curso_nome = row[1].strip() if len(row) > 1 and row[1] else ""
            qtd_str = row[2].strip() if len(row) > 2 and row[2] else "0"
            
            if not curso_nome or curso_nome.upper().startswith('TOTAL'):
                continue
            
            try:
                qtd_formandos = int(qtd_str)
            except (ValueError, TypeError):
                continue
            
            if qtd_formandos > 0:
                cursos.append({
                    'nome': curso_nome.upper().strip(),
                    'qtd_formandos': qtd_formandos
                })
        
        return cursos