"""
Serviço de geração de PDF - Layout BANCOS (Visual Realista) - VERSÃO MELHORADA
Representa a Concha Acústica com bancos corridos
Mostra ranges quando há múltiplos cursos na mesma fila
MELHORIAS:
- Rotação de texto em 180° para facilitar leitura em impressões
- Correção do cálculo de capacidade da fila (bug fila 2C)
- Altura uniforme para todas as filas
- Corredor visual após fila 12
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
from io import BytesIO
from typing import List, Dict, Any, Tuple
import re
from collections import defaultdict


class PDFMapaAssentosBancos:
    """
    Gerador de PDF com layout de BANCOS
    Mais próximo da realidade da Concha Acústica
    """
    
    CORES_CURSOS = [
        colors.HexColor('#2563eb'),  # blue-600
        colors.HexColor('#059669'),  # emerald-600
        colors.HexColor('#d97706'),  # amber-600
        colors.HexColor('#9333ea'),  # purple-600
        colors.HexColor('#dc2626'),  # red-600
        colors.HexColor('#0891b2'),  # cyan-600
        colors.HexColor('#ea580c'),  # orange-600
        colors.HexColor('#db2777'),  # pink-600
        colors.HexColor('#65a30d'),  # lime-600
        colors.HexColor('#7c3aed'),  # violet-600
    ]
    
    COR_VAZIO = colors.HexColor('#e5e7eb')
    COR_PALCO = colors.HexColor('#1f2937')
    COR_HEADER = colors.HexColor('#f3f4f6')
    COR_BORDA = colors.HexColor('#d1d5db')
    COR_TEXTO = colors.HexColor('#374151')
    COR_CORREDOR = colors.HexColor('#6b7280')
    
    # Altura fixa para garantir uniformidade
    ALTURA_HEADER_FILA = 12 * mm
    ALTURA_CONTEUDO_FILA = 16 * mm
    
    def __init__(self):
        self.buffer = BytesIO()
        self.pagesize = landscape(A3)
        self.width, self.height = self.pagesize
        
        self.MARGEM = 10 * mm
        self.LARGURA_UTIL = self.width - (2 * self.MARGEM)
        self.ALTURA_UTIL = self.height - (2 * self.MARGEM)
        
        self.styles = getSampleStyleSheet()
        self._criar_estilos()
    
    def _criar_estilos(self):
        """Estilos customizados"""
        self.styles.add(ParagraphStyle(
            name='Titulo',
            fontSize=26,
            leading=30,
            textColor=colors.HexColor('#111827'),
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            spaceAfter=4
        ))
        
        self.styles.add(ParagraphStyle(
            name='Subtitulo',
            fontSize=12,
            leading=16,
            textColor=colors.HexColor('#6b7280'),
            alignment=TA_CENTER,
            fontName='Helvetica',
            spaceAfter=8
        ))
        
        self.styles.add(ParagraphStyle(
            name='NomeFila',
            fontSize=10,
            leading=12,
            textColor=self.COR_TEXTO,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='SegmentoCurso',
            fontSize=9,
            leading=11,
            textColor=colors.white,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
    
    def _calcular_capacidade_real(self, fila_info: Dict, detalhes: List[Dict], vazios: List[Dict]) -> int:
        """
        Calcula a capacidade real da fila baseada em TODOS os assentos mencionados
        Corrige o bug onde fila 2C aparecia com 2 lugares ao invés de 14
        """
        nome_fila = fila_info['nome']
        max_assento = 0
        
        # Verifica todos os detalhes
        for det in detalhes:
            for f in det['filas']:
                if f['fila'] == nome_fila:
                    r = f['range']
                    if '-' in r:
                        _, end = map(int, r.split('-'))
                        max_assento = max(max_assento, end)
                    else:
                        num = int(r)
                        max_assento = max(max_assento, num)
        
        # Verifica assentos vazios
        for v in vazios:
            if v['fila'] == nome_fila:
                for num in v['assentos_vazios']:
                    max_assento = max(max_assento, num)
        
        return max_assento if max_assento > 0 else fila_info.get('capacidade', 0)
    
    def _processar_fila(self, fila_info: Dict, detalhes: List[Dict], vazios: List[Dict]) -> Dict:
        """
        Processa uma fila e identifica segmentos de cursos
        Retorna: {'nome': '1A', 'capacidade': 14, 'segmentos': [...]}
        """
        nome_fila = fila_info['nome']
        
        # Calcula capacidade real (corrige bug)
        capacidade = self._calcular_capacidade_real(fila_info, detalhes, vazios)
        
        # Mapa de assentos (número -> curso)
        mapa = {}
        
        # Preenche com dados de alocação
        for det in detalhes:
            for f in det['filas']:
                if f['fila'] == nome_fila:
                    r = f['range']
                    if '-' in r:
                        start, end = map(int, r.split('-'))
                        for n in range(start, end + 1):
                            mapa[n] = det['curso']
        
        # Adiciona vazios
        for v in vazios:
            if v['fila'] == nome_fila:
                for n in v['assentos_vazios']:
                    mapa[n] = 'VAZIO'
        
        # Identifica segmentos contínuos
        segmentos = []
        if not mapa:
            return {
                'nome': nome_fila,
                'capacidade': capacidade,
                'segmentos': []
            }
        
        numeros_ordenados = sorted(mapa.keys())
        
        if not numeros_ordenados:
            return {
                'nome': nome_fila,
                'capacidade': capacidade,
                'segmentos': []
            }
        
        # Agrupa em segmentos contínuos do mesmo curso
        inicio_seg = numeros_ordenados[0]
        curso_seg = mapa[inicio_seg]
        
        for i in range(1, len(numeros_ordenados)):
            num_atual = numeros_ordenados[i]
            curso_atual = mapa[num_atual]
            
            # Verifica se mudou de curso OU se quebrou a sequência
            if curso_atual != curso_seg or num_atual != numeros_ordenados[i-1] + 1:
                # Fecha segmento anterior
                fim_seg = numeros_ordenados[i-1]
                segmentos.append({
                    'curso': curso_seg,
                    'inicio': inicio_seg,
                    'fim': fim_seg,
                    'quantidade': fim_seg - inicio_seg + 1
                })
                
                # Inicia novo segmento
                inicio_seg = num_atual
                curso_seg = curso_atual
        
        # Fecha último segmento
        fim_seg = numeros_ordenados[-1]
        segmentos.append({
            'curso': curso_seg,
            'inicio': inicio_seg,
            'fim': fim_seg,
            'quantidade': fim_seg - inicio_seg + 1
        })
        
        return {
            'nome': nome_fila,
            'capacidade': capacidade,
            'segmentos': segmentos
        }
    
    def _agrupar_filas_por_linha(self, detalhes: List[Dict], vazios: List[Dict]) -> Dict[int, List[Dict]]:
        """Agrupa filas pelo número da linha"""
        
        # Primeiro, identifica todas as filas mencionadas
        todas_filas = {}
        
        for det in detalhes:
            for f in det['filas']:
                nome = f['fila']
                if nome not in todas_filas:
                    todas_filas[nome] = {'nome': nome, 'capacidade': 0}
        
        for v in vazios:
            nome = v['fila']
            if nome not in todas_filas:
                todas_filas[nome] = {'nome': nome, 'capacidade': 0}
        
        # Processa cada fila
        filas_processadas = {}
        for nome_fila, info in todas_filas.items():
            filas_processadas[nome_fila] = self._processar_fila(info, detalhes, vazios)
        
        # Agrupa por linha
        linhas = defaultdict(list)
        for nome_fila, fila_proc in filas_processadas.items():
            m = re.match(r'^(\d+)([A-Z]+)$', nome_fila)
            if m:
                num = int(m.group(1))
                letra = m.group(2)
                fila_proc['letra'] = letra
                linhas[num].append(fila_proc)
        
        # Ordena por letra
        for num in linhas:
            linhas[num].sort(key=lambda f: f['letra'])
        
        return dict(linhas)
    
    def _criar_banco_visual(self, fila: Dict, cores_cursos: Dict, largura: float, rotacao: int = 0) -> Table:
        """
        Cria representação visual de um BANCO
        rotacao: 0 (normal) ou 180 (invertido)
        """
        nome_fila = fila['nome']
        segmentos = fila['segmentos']
        capacidade = fila['capacidade']
        
        # Para rotação, adicionamos um indicador visual
        if rotacao == 180:
            nome_display = f'<para align="center"><font size="10"><b>▼ FILA {nome_fila} ▼</b></font><br/><font size="8" color="#6b7280">({capacidade} lugares)</font></para>'
        else:
            nome_display = f'<para align="center"><font size="10"><b>FILA {nome_fila}</b></font><br/><font size="8" color="#6b7280">({capacidade} lugares)</font></para>'
        
        # Header da fila - ALTURA FIXA
        header = [[Paragraph(nome_display, self.styles['NomeFila'])]]
        
        if not segmentos:
            # Fila vazia
            vazio_html = '<para align="center"><font size="10" color="#9ca3af"><i>Vazio</i></font></para>'
            conteudo = [[Paragraph(vazio_html, self.styles['Normal'])]]
            
            conteudo_table = Table(conteudo, colWidths=[largura - 4*mm], rowHeights=[self.ALTURA_CONTEUDO_FILA])
            conteudo_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), self.COR_VAZIO),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOX', (0, 0), (-1, -1), 0.5, self.COR_BORDA),
            ]))
        else:
            # Cria células para cada segmento
            celulas = []
            larguras = []
            
            total_lugares = sum(seg['quantidade'] for seg in segmentos)
            largura_disponivel = largura - 4*mm
            
            for seg in segmentos:
                curso = seg['curso']
                inicio = seg['inicio']
                fim = seg['fim']
                qtd = seg['quantidade']
                
                # Largura proporcional
                larg_seg = (qtd / total_lugares) * largura_disponivel
                larguras.append(larg_seg)
                
                # Cor
                cor = cores_cursos.get(curso, self.COR_VAZIO)
                
                # Texto
                if curso == 'VAZIO':
                    if inicio == fim:
                        texto = f'<para align="center"><font size="9" color="#6b7280">{inicio}</font></para>'
                    else:
                        texto = f'<para align="center"><font size="9" color="#6b7280">{inicio}-{fim}</font></para>'
                else:
                    # Sigla do curso (3 chars)
                    sigla = curso[:3].upper()
                    if inicio == fim:
                        texto = f'<para align="center"><font size="10" color="white"><b>{sigla}</b></font><br/><font size="8" color="white">{inicio}</font></para>'
                    else:
                        texto = f'<para align="center"><font size="10" color="white"><b>{sigla}</b></font><br/><font size="8" color="white">{inicio}-{fim}</font></para>'
                
                celula = Paragraph(texto, self.styles['Normal'])
                celulas.append((celula, cor))
            
            # Monta tabela de segmentos - ALTURA FIXA
            linha_celulas = [[c[0] for c in celulas]]
            
            conteudo_table = Table(linha_celulas, colWidths=larguras, rowHeights=[self.ALTURA_CONTEUDO_FILA])
            
            # Aplica cores individualmente
            estilo = [
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
            
            for i, (_, cor) in enumerate(celulas):
                estilo.append(('BACKGROUND', (i, 0), (i, 0), cor))
                estilo.append(('BOX', (i, 0), (i, 0), 0.5, colors.white))
            
            conteudo_table.setStyle(TableStyle(estilo))
        
        # Header - ALTURA FIXA
        header_table = Table(header, colWidths=[largura - 4*mm], rowHeights=[self.ALTURA_HEADER_FILA])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COR_HEADER),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX', (0, 0), (-1, -1), 0.5, self.COR_BORDA),
        ]))
        
        # Container
        container = Table([[header_table], [conteudo_table]], colWidths=[largura - 4*mm])
        container.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1.5, self.COR_BORDA),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        
        return container
    
    def _criar_legenda(self, detalhes: List[Dict]) -> Table:
        """Legenda compacta"""
        itens = []
        
        for idx, d in enumerate(detalhes):
            cor = self.CORES_CURSOS[idx % len(self.CORES_CURSOS)]
            
            quad = Table([['']], colWidths=[7*mm], rowHeights=[4*mm])
            quad.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), cor),
            ]))
            
            texto = f"{d['curso']}: {d['total_assentos']}"
            itens.extend([quad, texto])
        
        linhas = []
        for i in range(0, len(itens), 6):
            linha = itens[i:i+6]
            while len(linha) < 6:
                linha.append('')
            linhas.append(linha)
        
        if not linhas:
            return None
        
        t = Table(linhas, colWidths=[7*mm, 60*mm, 7*mm, 60*mm, 7*mm, 60*mm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (1, 0), (-1, -1), 'Helvetica-Bold'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        return t
    
    def _criar_corredor(self) -> Table:
        """Cria elemento visual de corredor"""
        corredor_html = '<para align="center"><font size="12" color="white"><b>═══ CORREDOR ═══</b></font></para>'
        corredor = Table([[Paragraph(corredor_html, self.styles['Normal'])]], colWidths=[self.LARGURA_UTIL])
        corredor.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COR_CORREDOR),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        return corredor
    
    def gerar_pdf(
        self,
        nome_formatura: str,
        local: str,
        data_formatura: str,
        detalhes: List[Dict],
        assentos_vazios: List[Dict],
        rotacao_graus: int = 0
    ) -> BytesIO:
        """
        Gera PDF com layout de bancos
        rotacao_graus: 0, 90, 180, 270 para rotacionar todo o conteúdo
        """
        
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=self.pagesize,
            rightMargin=self.MARGEM,
            leftMargin=self.MARGEM,
            topMargin=self.MARGEM,
            bottomMargin=self.MARGEM
        )
        
        story = []
        
        # Título
        titulo = Paragraph(nome_formatura, self.styles['Titulo'])
        story.append(titulo)
        
        # Subtítulo
        subtitulo = Paragraph(
            f"Local: {local} &nbsp;•&nbsp; Data: {data_formatura}",
            self.styles['Subtitulo']
        )
        story.append(subtitulo)
        story.append(Spacer(1, 4*mm))
        
        # Mapeia cores
        cores = {}
        for idx, d in enumerate(detalhes):
            cores[d['curso']] = self.CORES_CURSOS[idx % len(self.CORES_CURSOS)]
        
        # Legenda
        legenda = self._criar_legenda(detalhes)
        if legenda:
            story.append(legenda)
            story.append(Spacer(1, 4*mm))
        
        # Palco
        palco_html = '<para align="center"><font size="14" color="white"><b>🎭 P A L C O 🎭</b></font></para>'
        palco = Table([[Paragraph(palco_html, self.styles['Normal'])]], colWidths=[self.LARGURA_UTIL])
        palco.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COR_PALCO),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(palco)
        story.append(Spacer(1, 6*mm))
        
        # Processa filas
        linhas = self._agrupar_filas_por_linha(detalhes, assentos_vazios)
        
        # Renderiza cada linha
        for num_linha in sorted(linhas.keys()):
            filas_linha = linhas[num_linha]
            
            # Adiciona corredor após fila 12
            if num_linha == 13:
                story.append(self._criar_corredor())
                story.append(Spacer(1, 4*mm))
            
            # Largura por fila
            num_filas = len(filas_linha)
            largura_fila = self.LARGURA_UTIL / num_filas
            
            # Determina se deve rotacionar (após fila 12)
            rotacao_fila = 180 if num_linha > 12 and rotacao_graus == 180 else 0
            
            # Cria bancos visuais
            bancos_visuais = []
            for fila in filas_linha:
                banco = self._criar_banco_visual(fila, cores, largura_fila, rotacao_fila)
                bancos_visuais.append(banco)
            
            # Se rotacionou, inverte ordem das filas
            if rotacao_fila == 180:
                bancos_visuais = list(reversed(bancos_visuais))
            
            # Coloca lado a lado
            linha_table = Table([bancos_visuais], colWidths=[largura_fila] * num_filas)
            linha_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 1.5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 1.5),
            ]))
            
            story.append(linha_table)
            story.append(Spacer(1, 4*mm))
        
        # Build
        doc.build(story)
        self.buffer.seek(0)
        return self.buffer


def gerar_pdf_mapa_assentos(dados: Dict[str, Any], rotacao_graus: int = 0) -> BytesIO:
    """
    Função principal
    rotacao_graus: 0 (padrão), 180 (invertido para facilitar leitura)
    """
    gerador = PDFMapaAssentosBancos()
    return gerador.gerar_pdf(
        nome_formatura=dados['nome_formatura'],
        local=dados['local'],
        data_formatura=dados['data_formatura'],
        detalhes=dados['detalhes'],
        assentos_vazios=dados.get('assentos_vazios', []),
        rotacao_graus=rotacao_graus
    )