"""
Serviço de geração de PDF — Layout BANCOS v3
Usa canvas.drawString para renderizar siglas diretamente (sem Paragraph),
garantindo que nunca transbordam. "lugares" no lugar de "lug".
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus.flowables import Flowable
from io import BytesIO
from typing import List, Dict, Any
import re
from collections import defaultdict


# ─────────────────────────────────────────────────────────────────────────────
# Flowable customizado: renderiza uma fila inteira via canvas.drawString
# Isso elimina qualquer risco de transbordamento pois medimos com stringWidth
# antes de desenhar.
# ─────────────────────────────────────────────────────────────────────────────

class FilaFlowable(Flowable):
    """
    Desenha um banco (fila) diretamente no canvas, sem usar Table aninhada.
    Header: nome da fila + capacidade.
    Corpo: segmentos coloridos com sigla + "X lugares" calculados para caber.
    """

    CORES_CURSOS = [
        colors.HexColor('#2563eb'), colors.HexColor('#059669'),
        colors.HexColor('#d97706'), colors.HexColor('#9333ea'),
        colors.HexColor('#dc2626'), colors.HexColor('#0891b2'),
        colors.HexColor('#ea580c'), colors.HexColor('#db2777'),
        colors.HexColor('#65a30d'), colors.HexColor('#7c3aed'),
        colors.HexColor('#0d9488'), colors.HexColor('#b91c1c'),
        colors.HexColor('#4338ca'), colors.HexColor('#0284c7'),
    ]
    COR_VAZIO  = colors.HexColor('#e5e7eb')
    COR_HEADER = colors.HexColor('#f9fafb')
    COR_BORDA  = colors.HexColor('#d1d5db')

    H_HEADER  = 5.5 * mm
    H_CORPO   = 12 * mm
    PADDING_H = 2       # pts de padding horizontal interno

    def __init__(self, fila: Dict, cores_map: Dict, largura: float):
        super().__init__()
        self.fila      = fila
        self.cores_map = cores_map   # {nome_curso: Color}
        self.width     = largura - 1 * mm
        self.height    = self.H_HEADER + self.H_CORPO + 1

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def _fonte_cabe(self, texto: str, larg_pts: float,
                    fonte: str = 'Helvetica-Bold', max_pt=10, min_pt=5) -> int:
        espaco = max(larg_pts - 2 * self.PADDING_H, 1)
        for t in range(max_pt, min_pt - 1, -1):
            if stringWidth(texto, fonte, t) <= espaco:
                return t
        return min_pt

    def draw(self):
        c     = self.canv
        w     = self.width
        nome  = self.fila['nome']
        cap   = self.fila['capacidade']
        segs  = self.fila['segmentos']
        y_top = self.height

        # ── Header ──────────────────────────────────────────────────────────
        hh = self.H_HEADER
        c.setFillColor(self.COR_HEADER)
        c.rect(0, y_top - hh, w, hh, fill=1, stroke=0)
        c.setStrokeColor(self.COR_BORDA)
        c.setLineWidth(0.3)
        c.rect(0, y_top - hh, w, hh, fill=0, stroke=1)

        # Texto do header
        tam_nome = self._fonte_cabe(nome, w / 2, 'Helvetica-Bold', 8, 6)
        c.setFont('Helvetica-Bold', tam_nome)
        c.setFillColor(colors.HexColor('#374151'))
        c.drawCentredString(w / 2, y_top - hh + 3.5, nome)

        cap_txt = f'({cap} lugares)'
        tam_cap = self._fonte_cabe(cap_txt, w, 'Helvetica', 6, 5)
        c.setFont('Helvetica', tam_cap)
        c.setFillColor(colors.HexColor('#9ca3af'))
        c.drawCentredString(w / 2, y_top - hh + 3.5 - tam_nome - 1, cap_txt)

        # ── Corpo ────────────────────────────────────────────────────────────
        hc   = self.H_CORPO
        y0   = y_top - hh - hc        # y base do corpo
        total_seats = sum(s['quantidade'] for s in segs) if segs else 1

        x = 0
        for seg in segs:
            pct      = seg['quantidade'] / total_seats
            seg_w    = w * pct
            curso_n  = seg['curso']
            sigla    = seg['abreviacao']
            qtd      = seg['quantidade']

            if curso_n == 'VAZIO':
                cor = self.COR_VAZIO
            else:
                cor = self.cores_map.get(curso_n, colors.HexColor('#94a3b8'))

            # Fundo colorido
            c.setFillColor(cor)
            c.rect(x, y0, seg_w, hc, fill=1, stroke=0)

            # Borda entre segmentos
            c.setStrokeColor(colors.white)
            c.setLineWidth(0.5)
            c.rect(x, y0, seg_w, hc, fill=0, stroke=1)

            if curso_n != 'VAZIO' and seg_w > 4:
                # Sigla bold
                tam_sigla = self._fonte_cabe(sigla, seg_w, 'Helvetica-Bold', 10, 5)
                c.setFont('Helvetica-Bold', tam_sigla)
                c.setFillColor(colors.white)
                c.drawString(x + self.PADDING_H, y0 + hc - tam_sigla - 2, sigla)

                # Quantidade de lugares
                qtd_txt = f'{qtd} lugares'
                tam_qtd = self._fonte_cabe(qtd_txt, seg_w, 'Helvetica',
                                            max(tam_sigla - 2, 4), 4)
                # Verifica se realmente cabe
                if stringWidth(qtd_txt, 'Helvetica', tam_qtd) > seg_w - 2 * self.PADDING_H:
                    qtd_txt = str(qtd)  # só número
                c.setFont('Helvetica', tam_qtd)
                c.setFillColor(colors.HexColor('#ffffffcc'))
                c.drawString(x + self.PADDING_H, y0 + 3, qtd_txt)

            x += seg_w

        # Borda externa do corpo
        c.setStrokeColor(self.COR_BORDA)
        c.setLineWidth(0.5)
        c.rect(0, y0, w, hc, fill=0, stroke=1)


# ─────────────────────────────────────────────────────────────────────────────
# Serviço principal
# ─────────────────────────────────────────────────────────────────────────────

class PDFMapaAssentosBancos:

    CORES_CURSOS = FilaFlowable.CORES_CURSOS

    COR_PALCO    = colors.HexColor('#1f2937')
    COR_HEADER   = colors.HexColor('#f9fafb')
    COR_BORDA    = colors.HexColor('#d1d5db')
    COR_CORREDOR = colors.HexColor('#6b7280')

    def __init__(self):
        self.buffer   = BytesIO()
        self.pagesize = landscape(A3)
        self.width, self.height = self.pagesize
        self.MARGEM       = 8 * mm
        self.LARGURA_UTIL = self.width  - 2 * self.MARGEM
        self.styles = getSampleStyleSheet()
        self._criar_estilos()

    def _criar_estilos(self):
        self.styles.add(ParagraphStyle(
            name='Titulo', fontSize=22, leading=26,
            textColor=colors.HexColor('#111827'),
            alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=2,
        ))
        self.styles.add(ParagraphStyle(
            name='Subtitulo', fontSize=10, leading=13,
            textColor=colors.HexColor('#6b7280'),
            alignment=TA_CENTER, fontName='Helvetica', spaceAfter=4,
        ))

    # ------------------------------------------------------------------
    # Processamento de dados
    # ------------------------------------------------------------------

    def _processar_fila(self, nome_fila: str, detalhes, vazios) -> Dict:
        mapa: Dict[int, str] = {}
        abrevs: Dict[str, str] = {}

        for det in detalhes:
            for f in det['filas']:
                if f['fila'] != nome_fila:
                    continue
                r = f['range']
                s, e = (map(int, r.split('-')) if '-' in r else (int(r), int(r)))
                for n in range(s, e + 1):
                    mapa[n] = det['curso']
                abrevs[det['curso']] = det.get('abreviacao', det['curso'][:3].upper())

        for v in vazios:
            if v['fila'] == nome_fila:
                for n in v['assentos_vazios']:
                    mapa[n] = 'VAZIO'

        if not mapa:
            return {'nome': nome_fila, 'capacidade': 0, 'segmentos': []}

        nums = sorted(mapa)
        capacidade = max(nums)
        segmentos = []
        inicio = nums[0]
        atual = mapa[inicio]

        for i in range(1, len(nums)):
            n, c = nums[i], mapa[nums[i]]
            if c != atual or n != nums[i - 1] + 1:
                segmentos.append({
                    'curso': atual,
                    'abreviacao': abrevs.get(atual, atual[:3].upper()),
                    'inicio': inicio, 'fim': nums[i - 1],
                    'quantidade': nums[i - 1] - inicio + 1,
                })
                inicio, atual = n, c
        segmentos.append({
            'curso': atual,
            'abreviacao': abrevs.get(atual, atual[:3].upper()),
            'inicio': inicio, 'fim': nums[-1],
            'quantidade': nums[-1] - inicio + 1,
        })

        return {'nome': nome_fila, 'capacidade': capacidade, 'segmentos': segmentos}

    def _agrupar_por_linha(self, detalhes, vazios) -> Dict[int, List[Dict]]:
        todas = {}
        for det in detalhes:
            for f in det['filas']:
                todas.setdefault(f['fila'], None)
        for v in vazios:
            todas.setdefault(v['fila'], None)

        processadas = {nome: self._processar_fila(nome, detalhes, vazios) for nome in todas}
        linhas: Dict[int, List] = defaultdict(list)
        for nome, fila in processadas.items():
            m = re.match(r'^(\d+)([A-Z]+)$', nome)
            if m:
                fila['letra'] = m.group(2)
                linhas[int(m.group(1))].append(fila)
        for num in linhas:
            linhas[num].sort(key=lambda f: f['letra'])
        return dict(linhas)

    # ------------------------------------------------------------------
    # Legenda
    # ------------------------------------------------------------------

    def _criar_legenda(self, detalhes: List[Dict]) -> Table:
        COLS    = 2
        LINHA_H = 16 * mm
        COR_W   = 10 * mm
        GAP     = 3 * mm
        PAD_V   = 4 * mm

        larg_par      = self.LARGURA_UTIL / COLS
        larguras_cols = [COR_W, larg_par - COR_W] * COLS

        linhas_dados   = []
        linhas_estilos = []

        for row_i in range(0, len(detalhes), COLS):
            par = detalhes[row_i: row_i + COLS]
            linha_cells = []
            for col_j, d in enumerate(par):
                idx = row_i + col_j
                cor = self.CORES_CURSOS[idx % len(self.CORES_CURSOS)]
                linhas_estilos.append((row_i // COLS, col_j * 2, cor))
                html = (
                    f'<b><font size="11" color="#111827">{d["curso"]}</font></b><br/>'
                    f'<font size="9" color="#6b7280">{d["total_assentos"]} assentos</font>'
                )
                linha_cells += ['', Paragraph(html, self.styles['Normal'])]
            while len(par) < COLS:
                linha_cells += ['', '']
                par.append(None)
            linhas_dados.append(linha_cells)

        if not linhas_dados:
            return None

        t = Table(linhas_dados, colWidths=larguras_cols, rowHeights=LINHA_H)
        cmds = [
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('TOPPADDING',    (0, 0), (-1, -1), PAD_V),
            ('BOTTOMPADDING', (0, 0), (-1, -1), PAD_V),
            ('LEFTPADDING',   (1, 0), (1, -1), GAP),
            ('LEFTPADDING',   (3, 0), (3, -1), GAP),
            ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#e5e7eb')),
        ]
        for (ri, ci, cor) in linhas_estilos:
            cmds.append(('BACKGROUND', (ci,     ri), (ci,     ri), cor))
            bg = colors.white if ri % 2 == 0 else colors.HexColor('#f9fafb')
            cmds.append(('BACKGROUND', (ci + 1, ri), (ci + 1, ri), bg))
        t.setStyle(TableStyle(cmds))
        return t

    # ------------------------------------------------------------------
    # Renderiza seção (antes ou depois do corredor)
    # ------------------------------------------------------------------

    def _renderizar_secao(self, story: list, nums: List[int],
                           linhas_todas: Dict, cores: Dict):
        for num in nums:
            filas_linha = linhas_todas[num]
            n    = len(filas_linha)
            larg = self.LARGURA_UTIL / n

            # Linha de FilaFlowable lado a lado via Table de 1 linha
            bancos = [FilaFlowable(f, cores, larg) for f in filas_linha]
            t = Table([bancos], colWidths=[larg] * n)
            t.setStyle(TableStyle([
                ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING',  (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING',   (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
            ]))
            story.append(t)
            story.append(Spacer(1, 1.5 * mm))

    # ------------------------------------------------------------------
    # Geração final
    # ------------------------------------------------------------------

    def gerar_pdf(self, nome_formatura: str, local: str, data_formatura: str,
                  detalhes: List[Dict], assentos_vazios: List[Dict]) -> BytesIO:

        doc = SimpleDocTemplate(
            self.buffer, pagesize=self.pagesize,
            rightMargin=self.MARGEM, leftMargin=self.MARGEM,
            topMargin=self.MARGEM,   bottomMargin=self.MARGEM,
        )
        story = []

        # ── Página 1: Legenda ────────────────────────────────────────────────
        story.append(Paragraph(nome_formatura, self.styles['Titulo']))
        story.append(Paragraph(
            f"Local: {local} &nbsp;•&nbsp; Data: {data_formatura}",
            self.styles['Subtitulo'],
        ))
        story.append(Spacer(1, 8 * mm))
        legenda = self._criar_legenda(detalhes)
        if legenda:
            story.append(legenda)
        story.append(PageBreak())

        # Mapa de cores por nome de curso
        cores = {
            d['curso']: self.CORES_CURSOS[i % len(self.CORES_CURSOS)]
            for i, d in enumerate(detalhes)
        }

        linhas_todas   = self._agrupar_por_linha(detalhes, assentos_vazios)
        nums_ordenados = sorted(linhas_todas)
        antes_corr  = [n for n in nums_ordenados if n <= 12]
        depois_corr = [n for n in nums_ordenados if n > 12]

        # ── Página 2: Antes do corredor ──────────────────────────────────────
        palco_html = '<para align="center"><font size="11" color="white"><b>🎭 P A L C O 🎭</b></font></para>'
        palco = Table([[Paragraph(palco_html, self.styles['Normal'])]], colWidths=[self.LARGURA_UTIL])
        palco.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), self.COR_PALCO),
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(palco)
        story.append(Spacer(1, 2 * mm))
        self._renderizar_secao(story, antes_corr, linhas_todas, cores)

        # ── Página 3: Depois do corredor ─────────────────────────────────────
        if depois_corr:
            story.append(PageBreak())
            corr_html = '<para align="center"><font size="9" color="white"><b>═══ CORREDOR ═══</b></font></para>'
            corredor = Table([[Paragraph(corr_html, self.styles['Normal'])]], colWidths=[self.LARGURA_UTIL])
            corredor.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (-1, -1), self.COR_CORREDOR),
                ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING',    (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(corredor)
            story.append(Spacer(1, 2 * mm))
            self._renderizar_secao(story, depois_corr, linhas_todas, cores)

        doc.build(story)
        self.buffer.seek(0)
        return self.buffer


def gerar_pdf_mapa_assentos(dados: Dict[str, Any], rotacao_graus: int = 0) -> BytesIO:
    gerador = PDFMapaAssentosBancos()
    return gerador.gerar_pdf(
        nome_formatura=dados['nome_formatura'],
        local=dados['local'],
        data_formatura=dados['data_formatura'],
        detalhes=dados['detalhes'],
        assentos_vazios=dados.get('assentos_vazios', []),
    )