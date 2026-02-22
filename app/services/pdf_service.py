"""
Serviço de geração de PDF — Layout BANCOS
Legendas maiores, sem transbordar, texto proporcional ao espaço disponível.
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
from io import BytesIO
from typing import List, Dict, Any
import re
from collections import defaultdict


class PDFMapaAssentosBancos:

    CORES_CURSOS = [
        colors.HexColor('#2563eb'),
        colors.HexColor('#059669'),
        colors.HexColor('#d97706'),
        colors.HexColor('#9333ea'),
        colors.HexColor('#dc2626'),
        colors.HexColor('#0891b2'),
        colors.HexColor('#ea580c'),
        colors.HexColor('#db2777'),
        colors.HexColor('#65a30d'),
        colors.HexColor('#7c3aed'),
        colors.HexColor('#0d9488'),
        colors.HexColor('#b91c1c'),
        colors.HexColor('#4338ca'),
        colors.HexColor('#0284c7'),
    ]

    COR_VAZIO    = colors.HexColor('#f3f4f6')
    COR_PALCO    = colors.HexColor('#1f2937')
    COR_HEADER   = colors.HexColor('#f9fafb')
    COR_BORDA    = colors.HexColor('#d1d5db')
    COR_TEXTO    = colors.HexColor('#374151')
    COR_CORREDOR = colors.HexColor('#6b7280')

    # Alturas das filas no mapa
    ALTURA_HEADER  = 5 * mm
    ALTURA_CONTEUDO = 9 * mm

    def __init__(self):
        self.buffer   = BytesIO()
        self.pagesize = landscape(A3)
        self.width, self.height = self.pagesize
        self.MARGEM       = 8 * mm
        self.LARGURA_UTIL = self.width  - 2 * self.MARGEM
        self.ALTURA_UTIL  = self.height - 2 * self.MARGEM
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
        self.styles.add(ParagraphStyle(
            name='NomeFila', fontSize=7, leading=8,
            textColor=self.COR_TEXTO, alignment=TA_CENTER, fontName='Helvetica-Bold',
        ))

    # ------------------------------------------------------------------ #
    # Helpers de processamento
    # ------------------------------------------------------------------ #

    def _processar_fila(self, nome_fila: str, detalhes, vazios) -> Dict:
        """Monta segmentos de curso para uma fila."""
        mapa: Dict[int, str]  = {}
        abrevs: Dict[str, str] = {}

        for det in detalhes:
            for f in det['filas']:
                if f['fila'] != nome_fila:
                    continue
                r = f['range']
                if '-' in r:
                    s, e = map(int, r.split('-'))
                else:
                    s = e = int(r)
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
        segmentos  = []
        inicio = nums[0]
        atual  = mapa[inicio]

        for i in range(1, len(nums)):
            n = nums[i]
            c = mapa[n]
            if c != atual or n != nums[i - 1] + 1:
                segmentos.append({
                    'curso': atual,
                    'abreviacao': abrevs.get(atual, atual[:3].upper()),
                    'inicio': inicio, 'fim': nums[i - 1],
                    'quantidade': nums[i - 1] - inicio + 1,
                })
                inicio = n
                atual  = c
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
                if f['fila'] not in todas:
                    todas[f['fila']] = None
        for v in vazios:
            if v['fila'] not in todas:
                todas[v['fila']] = None

        processadas = {nome: self._processar_fila(nome, detalhes, vazios) for nome in todas}

        linhas: Dict[int, List] = defaultdict(list)
        for nome, fila in processadas.items():
            m = re.match(r'^(\d+)([A-Z]+)$', nome)
            if m:
                num    = int(m.group(1))
                letra  = m.group(2)
                fila['letra'] = letra
                linhas[num].append(fila)

        for num in linhas:
            linhas[num].sort(key=lambda f: f['letra'])

        return dict(linhas)

    # ------------------------------------------------------------------ #
    # Banco visual (uma fila)
    # ------------------------------------------------------------------ #

    def _texto_segmento(self, seg: Dict, larg_mm: float) -> str:
        """
        Gera HTML do segmento com tamanho de fonte proporcional ao espaço,
        garantindo que não transborde.
        """
        if seg['curso'] == 'VAZIO':
            qtd = seg['quantidade']
            label = str(qtd) if qtd == 1 else f"{qtd}"
            return f'<para align="center"><font size="6" color="#9ca3af">{label}</font></para>'

        sigla = seg['abreviacao']
        qtd   = seg['quantidade']

        # Tamanho da fonte da sigla: proporcional à largura, máx 9, mín 5
        # ~0.55pt por caractere por pt de fonte
        tamanho_sigla = min(9, max(5, int(larg_mm * 0.9 / max(len(sigla), 1))))

        # Range: sempre mostra quantidade de lugares (não número do assento)
        if qtd <= 1:
            range_str = ""
        elif qtd <= 6:
            range_str = str(qtd)
        else:
            range_str = f"{qtd}lug"

        tamanho_range = max(4, tamanho_sigla - 2)
        leading = tamanho_sigla + tamanho_range + 2

        if range_str:
            return (
                f'<para align="center" leading="{leading}">'
                f'<font size="{tamanho_sigla}" color="white"><b>{sigla}</b></font>'
                f'<br/>'
                f'<font size="{tamanho_range}" color="white">{range_str}</font>'
                f'</para>'
            )
        else:
            return (
                f'<para align="center">'
                f'<font size="{tamanho_sigla}" color="white"><b>{sigla}</b></font>'
                f'</para>'
            )

    def _criar_banco(self, fila: Dict, cores: Dict, largura: float) -> Table:
        nome_fila  = fila['nome']
        segmentos  = fila['segmentos']
        capacidade = fila['capacidade']

        # Header
        header_html = (
            f'<para align="center">'
            f'<font size="7"><b>{nome_fila}</b></font>'
            f'<br/>'
            f'<font size="6" color="#9ca3af">({capacidade} lug.)</font>'
            f'</para>'
        )
        header_t = Table(
            [[Paragraph(header_html, self.styles['NomeFila'])]],
            colWidths=[largura - 1 * mm], rowHeights=[self.ALTURA_HEADER],
        )
        header_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COR_HEADER),
            ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
            ('BOX',        (0, 0), (-1, -1), 0.3, self.COR_BORDA),
            ('TOPPADDING',    (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))

        # Conteúdo
        if not segmentos:
            conteudo_t = Table(
                [[Paragraph('<para align="center"><font size="6" color="#9ca3af">—</font></para>', self.styles['Normal'])]],
                colWidths=[largura - 1 * mm], rowHeights=[self.ALTURA_CONTEUDO],
            )
            conteudo_t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), self.COR_VAZIO),
                ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
                ('BOX',        (0, 0), (-1, -1), 0.5, self.COR_BORDA),
            ]))
        else:
            total = sum(s['quantidade'] for s in segmentos)
            larg_util = largura - 1 * mm
            celulas = []
            larguras = []

            for seg in segmentos:
                larg_seg = (seg['quantidade'] / total) * larg_util
                larguras.append(larg_seg)
                larg_mm  = larg_seg / mm
                html = self._texto_segmento(seg, larg_mm)
                cor  = (cores.get(seg['curso'], self.COR_VAZIO)
                        if seg['curso'] != 'VAZIO' else self.COR_VAZIO)
                celulas.append((Paragraph(html, self.styles['Normal']), cor))

            conteudo_t = Table(
                [[c[0] for c in celulas]],
                colWidths=larguras, rowHeights=[self.ALTURA_CONTEUDO],
            )
            estilo = [
                ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING',   (0, 0), (-1, -1), 1),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 1),
                ('TOPPADDING',    (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ]
            for i, (_, cor) in enumerate(celulas):
                estilo.append(('BACKGROUND', (i, 0), (i, 0), cor))
                estilo.append(('BOX',        (i, 0), (i, 0), 0.3, colors.white))
            conteudo_t.setStyle(TableStyle(estilo))

        container = Table([[header_t], [conteudo_t]], colWidths=[largura - 1 * mm])
        container.setStyle(TableStyle([
            ('BOX',           (0, 0), (-1, -1), 0.6, self.COR_BORDA),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0.3),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0.3),
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0.3),
        ]))
        return container

    # ------------------------------------------------------------------ #
    # Legenda — fonte grande, sem transbordar
    # ------------------------------------------------------------------ #

    def _criar_legenda(self, detalhes: List[Dict]) -> Table:
        """
        Legenda em grade de 2 colunas.

        Layout de cada célula (dentro da mesma célula da Table, sem tabela aninhada):
          ■ NOME DO CURSO
            999 assentos

        O quadrado de cor é simulado como background da célula de "cor" em
        uma tabela de 2 colunas fixas por item: [cor_col | texto_col].
        Toda a lógica vive numa Table simples, sem aninhamento, para evitar
        overflow e garantir que o Reportlab consegue medir corretamente.
        """
        COLS   = 2                           # pares por linha da grade
        PAD_H  = 5 * mm                      # padding horizontal por célula
        PAD_V  = 4 * mm                      # padding vertical por célula
        COR_W  = 10 * mm                     # largura da coluna do quadrado de cor
        GAP    = 3 * mm                      # gap entre quadrado e texto
        LINHA_H = 16 * mm                    # altura fixa de cada linha da legenda

        # Largura disponível por "par" (coluna da grade)
        larg_par   = self.LARGURA_UTIL / COLS
        # Largura disponível para o texto dentro de um par
        texto_w    = larg_par - COR_W - GAP - 2 * PAD_H

        # Estilo de texto seguro — fonte grande e bold para o nome
        # Usa 11pt fixo; se o nome for muito longo, o Reportlab quebra linha
        # automaticamente dentro de texto_w (sem overflow horizontal)
        estilo_nome = ParagraphStyle(
            'LegNome', parent=self.styles['Normal'],
            fontName='Helvetica-Bold', fontSize=11, leading=13,
            textColor=colors.HexColor('#111827'),
        )
        estilo_qtd = ParagraphStyle(
            'LegQtd', parent=self.styles['Normal'],
            fontName='Helvetica', fontSize=9, leading=11,
            textColor=colors.HexColor('#6b7280'),
        )

        # Monta linhas de forma que cada "linha da grade" vira 1 linha de Table
        # com COLS*2 colunas: [cor₁, txt₁, cor₂, txt₂]
        larguras_cols = []
        for _ in range(COLS):
            larguras_cols += [COR_W, larg_par - COR_W]   # par: quadrado | texto

        linhas_dados  = []
        linhas_estilos: list = []

        def celula_texto(d, idx):
            """Retorna o Paragraph de texto para um item."""
            nome = d['curso']
            qtd  = d['total_assentos']
            # Stack nome + quantidade em VKeepTogether via \n (Paragraph cuida da quebra)
            from reportlab.platypus import KeepTogether
            return [
                Paragraph(nome, estilo_nome),
                Paragraph(f"{qtd} assentos", estilo_qtd),
            ]

        # Agrupa detalhes em pares
        for row_i in range(0, len(detalhes), COLS):
            par = detalhes[row_i: row_i + COLS]
            celulas_cor  = []
            celulas_txt  = []

            for col_j, d in enumerate(par):
                idx = row_i + col_j
                cor = self.CORES_CURSOS[idx % len(self.CORES_CURSOS)]

                celulas_cor.append('')    # conteúdo vazio; cor vem do TableStyle
                # Texto: nome em bold grande + quantidade
                nome = d['curso']
                qtd  = d['total_assentos']
                html = (
                    f'<b><font size="11" color="#111827">{nome}</font></b><br/>'
                    f'<font size="9" color="#6b7280">{qtd} assentos</font>'
                )
                celulas_txt.append(Paragraph(html, self.styles['Normal']))

                # Guarda cor para aplicar no TableStyle depois
                linhas_estilos.append((row_i // COLS, col_j * 2, cor))

            # Preenche colunas vazias se o par for incompleto
            while len(par) < COLS:
                celulas_cor.append('')
                celulas_txt.append('')
                par.append(None)

            # Intercala: [cor0, txt0, cor1, txt1]
            linha_cells = []
            for c, t in zip(celulas_cor, celulas_txt):
                linha_cells += [c, t]
            linhas_dados.append(linha_cells)

        if not linhas_dados:
            return None

        t = Table(linhas_dados, colWidths=larguras_cols, rowHeights=LINHA_H)

        style_cmds = [
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            # Padding nas colunas de texto (índices ímpares)
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('TOPPADDING',    (0, 0), (-1, -1), PAD_V),
            ('BOTTOMPADDING', (0, 0), (-1, -1), PAD_V),
            # Padding extra no texto
            ('LEFTPADDING',   (1, 0), (1, -1), GAP),
            ('LEFTPADDING',   (3, 0), (3, -1), GAP),
            # Grade suave
            ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#e5e7eb')),
            # Linhas zebradas por par de colunas (aplica à linha inteira)
        ]

        # Cores das células de "quadrado"
        for (ri, ci_par, cor) in linhas_estilos:
            col_idx = ci_par  # já é o índice par (0, 2, 4...)
            style_cmds.append(('BACKGROUND', (col_idx, ri), (col_idx, ri), cor))
            # Linhas pares com fundo levemente cinza no texto
            bg_txt = colors.white if ri % 2 == 0 else colors.HexColor('#f9fafb')
            style_cmds.append(('BACKGROUND', (col_idx + 1, ri), (col_idx + 1, ri), bg_txt))

        t.setStyle(TableStyle(style_cmds))
        return t

    # ------------------------------------------------------------------ #
    # Geração final do PDF
    # ------------------------------------------------------------------ #

    def gerar_pdf(
        self,
        nome_formatura: str,
        local: str,
        data_formatura: str,
        detalhes: List[Dict],
        assentos_vazios: List[Dict],
    ) -> BytesIO:

        doc = SimpleDocTemplate(
            self.buffer, pagesize=self.pagesize,
            rightMargin=self.MARGEM, leftMargin=self.MARGEM,
            topMargin=self.MARGEM,   bottomMargin=self.MARGEM,
        )
        story = []

        # ── Página 1: Legenda ──────────────────────────────────────────
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

        # ── Preparação ────────────────────────────────────────────────
        cores = {
            d['curso']: self.CORES_CURSOS[i % len(self.CORES_CURSOS)]
            for i, d in enumerate(detalhes)
        }
        linhas_todas   = self._agrupar_por_linha(detalhes, assentos_vazios)
        nums_ordenados = sorted(linhas_todas)
        antes_corr = [n for n in nums_ordenados if n <= 12]
        depois_corr = [n for n in nums_ordenados if n > 12]

        # ── Página 2: Antes do corredor ───────────────────────────────
        palco_html = (
            '<para align="center">'
            '<font size="11" color="white"><b>🎭 P A L C O 🎭</b></font>'
            '</para>'
        )
        palco = Table(
            [[Paragraph(palco_html, self.styles['Normal'])]],
            colWidths=[self.LARGURA_UTIL],
        )
        palco.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COR_PALCO),
            ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(palco)
        story.append(Spacer(1, 2 * mm))

        for num in antes_corr:
            filas_linha = linhas_todas[num]
            n = len(filas_linha)
            larg = self.LARGURA_UTIL / n
            bancos = [self._criar_banco(f, cores, larg) for f in filas_linha]
            t = Table([bancos], colWidths=[larg] * n)
            t.setStyle(TableStyle([
                ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING',   (0, 0), (-1, -1), 0.3),
                ('RIGHTPADDING',  (0, 0), (-1, -1), 0.3),
            ]))
            story.append(t)
            story.append(Spacer(1, 1.2 * mm))

        # ── Página 3: Depois do corredor ──────────────────────────────
        if depois_corr:
            story.append(PageBreak())

            corredor_html = (
                '<para align="center">'
                '<font size="9" color="white"><b>═══ CORREDOR ═══</b></font>'
                '</para>'
            )
            corredor = Table(
                [[Paragraph(corredor_html, self.styles['Normal'])]],
                colWidths=[self.LARGURA_UTIL],
            )
            corredor.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), self.COR_CORREDOR),
                ('ALIGN',      (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN',     (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING',    (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(corredor)
            story.append(Spacer(1, 2 * mm))

            for num in depois_corr:
                filas_linha = linhas_todas[num]
                n = len(filas_linha)
                larg = self.LARGURA_UTIL / n
                bancos = [self._criar_banco(f, cores, larg) for f in filas_linha]
                t = Table([bancos], colWidths=[larg] * n)
                t.setStyle(TableStyle([
                    ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING',   (0, 0), (-1, -1), 0.3),
                    ('RIGHTPADDING',  (0, 0), (-1, -1), 0.3),
                ]))
                story.append(t)
                story.append(Spacer(1, 1.2 * mm))

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