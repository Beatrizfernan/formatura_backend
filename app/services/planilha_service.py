import csv
import pandas as pd
from io import StringIO, BytesIO
from typing import Dict, List, Tuple
from datetime import datetime

class PlanilhaService:
    
    @staticmethod
    def ler_planilha_csv(url: str) -> Dict:
        """Lê planilha CSV do Google Sheets (antigo - via URL)"""
        try:
            import requests
            response = requests.get(url)
            response.encoding = "utf-8"
            csv_text = StringIO(response.text)
            reader = csv.reader(csv_text)
            
            dados = [row for row in reader]
            return PlanilhaService._processar_dados_csv(dados)
            
        except Exception as e:
            raise Exception(f'Erro ao ler planilha: {str(e)}')
    
    @staticmethod
    def ler_planilha_csv_bytes(arquivo_bytes: bytes) -> Dict:
        """Lê planilha CSV a partir de bytes"""
        try:
            # Decodifica bytes para string
            texto_csv = arquivo_bytes.decode('utf-8')
            csv_text = StringIO(texto_csv)
            reader = csv.reader(csv_text)
            
            dados = [row for row in reader]
            return PlanilhaService._processar_dados_csv(dados)
            
        except Exception as e:
            raise Exception(f'Erro ao ler arquivo CSV: {str(e)}')
    
    @staticmethod
    def ler_planilha_excel_bytes(arquivo_bytes: bytes) -> Dict:
        """Lê planilha Excel (.xlsx ou .xls) a partir de bytes"""
        try:
            # Lê com pandas, sem interpretar a primeira linha como header
            df = pd.read_excel(BytesIO(arquivo_bytes), sheet_name=0, header=None)
            
            # Converte DataFrame para lista de listas (como CSV)
            dados = []
            
            for _, row in df.iterrows():
                dados.append([str(val) if pd.notna(val) else "" for val in row.values])
            
            return PlanilhaService._processar_dados_csv(dados)
            
        except Exception as e:
            raise Exception(f'Erro ao ler arquivo Excel: {str(e)}')
    
    @staticmethod
    def _processar_dados_csv(dados: List[List[str]]) -> Dict:
        """
        Formato esperado:
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
        if not texto or not isinstance(texto, str):
            return "Formatura", None
        
        texto = str(texto).strip()
        
        # Tenta encontrar a data (formato DD/MM/YYYY)
        data_formatura = None
        nome_unidades = "Formatura"
        
        # Procura por padrão de data DD/MM/YYYY
        import re
        match_data = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', texto)
        
        if match_data:
            data_str = match_data.group(0)
            try:
                data_obj = datetime.strptime(data_str, '%d/%m/%Y')
                data_formatura = data_obj.strftime('%Y-%m-%d')
            except:
                pass
            
            # Extrai unidades após a data
            partes = texto.split('-', 1)
            if len(partes) > 1:
                nome_unidades = partes[1].strip()
        else:
            # Se não encontrar data, tenta dividir por "-"
            partes = texto.split('-', 1)
            if len(partes) > 1:
                nome_unidades = partes[1].strip()
        
        return f"Formatura {nome_unidades}", data_formatura
    
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
                qtd_formandos = int(float(qtd_str))  # Converte para float depois int (caso seja "10.0")
            except (ValueError, TypeError):
                continue
            
            if qtd_formandos > 0:
                cursos.append({
                    'nome': curso_nome.upper().strip(),
                    'qtd_formandos': qtd_formandos
                })
        
        return cursos