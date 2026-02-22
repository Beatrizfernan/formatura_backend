"""
Script para processar cursos e suas siglas/abreviações
Baseado no PDF: COLAÇÃO DE GRAU 2025.2
SIGLAS EXATAMENTE COMO NO PDF (com correção de duplicatas)
"""

from mongoengine import connect
from config import MONGO_URI
from app.models.curso import Curso


# ------------------------------------------------------------------------------
# Conexão com o MongoDB
# ------------------------------------------------------------------------------
connect(host=MONGO_URI)


# ------------------------------------------------------------------------------
# Dicionário base de cursos e siglas - EXATAMENTE COMO NO PDF
# ------------------------------------------------------------------------------
CURSOS_SIGLAS = {
    # FAMED
    "FISIOTERAPIA": "FISIO",

    # FFOE
    "FARMÁCIA": "Farm",
    "ODONTOLOGIA": "ODONTO",
    "ENFERMAGEM": "ENFERM",

    # LABOMAR
    "OCEANOGRAFIA": "OCEAN",
    "CIÊNCIAS AMBIENTAIS": "C. AMB",

    # UFC VIRTUAL
    "SISTEMAS E MÍDIAS DIGITAIS": "S.M.D",
    "ADMINISTRAÇÃO PÚBLICA": "ADM. P",
    "FÍSICA": "FIS",
    "LETRAS": "LETRAS",
    "MATEMÁTICA": "MAT",
    "QUÍMICA": "QUIM",

    # ICA
    "CINEMA E AUDIOVISUAL": "CINE & AUDI",
    "DANÇA": "DANÇ",
    "DESIGN - MODA": "MODA",
    "FILOSOFIA": "FILOS",
    "GASTRONOMIA": "GASTR",
    "JORNALISMO": "JORN",
    "MÚSICA": "MUSC",
    "PUBLICIDADE E PROPAGANDA": "PUBLI & PROPAG",
    "TEATRO": "TEATR",

    # IEFES
    "EDUCACAO FÍSICA": "ED. FIS",

    # IAUD
    "ARQUITETURA E URBANISMO": "ARQ & URB",
    "DESIGN": "DESIG",

    # DIREITO
    "DIREITO": "DIR",

    # CENTRO DE CIÊNCIAS
    "BIOTECNOLOGIA": "BIOTEC",
    "CIÊNCIAS BIOLÓGICAS - BACHARELADO": "C. BIO - BACH",
    "CIÊNCIAS BIOLÓGICAS - LICENCIATURA": "C. BIO - LICEN",
    "CIÊNCIA DA COMPUTAÇÃO": "C. COMP",
    "CIÊNCIA DE DADOS": "C. DAD",
    "ESTATÍSTICA": "ESTAT",
    "FÍSICA - BACHARELADO": "FIS - BACH",
    "FÍSICA - LICENCIATURA": "FIS - LICEN",
    "GEOGRAFIA - BACHARELADO": "GEO - BACH",
    "GEOGRAFIA - LICENCIATURA": "GEO - LICEN",
    "GEOLOGIA": "GEOL",
    "MATEMÁTICA - BACHARELADO": "MAT - BACH",
    "MATEMÁTICA - LICENCIATURA": "MAT - LICEN",
    "MATEMÁTICA INDUSTRIAL": "MAT. I",
    "QUÍMICA - BACHARELADO": "QUIM - BACH",
    "QUÍMICA - LICENCIATURA": "QUIM - LICEN",

    # AGRÁRIAS
    "AGRONOMIA": "AGRO",
    "ECONOMIA ECOLÓGICA": "E. ECO",
    "ENGENHARIA DE ALIMENTOS": "ENG. A",
    "ENGENHARIA DE PESCA": "ENG. PESCA",  # ✅ CORRIGIDO: era "ENG. P" (conflitava com Petróleo)

    "GESTÃO DE POLÍTICAS PÚBLICAS": "G.P.P",
    "ZOOTECNIA": "ZOO",

    # TECNOLOGIA
    "ENGENHARIA AMBIENTAL": "ENG. AMB",
    "ENGENHARIA CIVIL": "ENG. C",
    "ENGENHARIA DE COMPUTAÇÃO": "ENG. COMP",
    "ENGENHARIA ELÉTRICA": "ENG. E",
    "ENGENHARIA DE ENERGIAS RENOVÁVEIS": "ENG. E. R",
    "ENGENHARIA MECÂNICA": "ENG. M",
    "ENGENHARIA METALÚRGICA": "ENG. MET",
    "ENGENHARIA DE PETRÓLEO": "ENG. PETR",  # ✅ CORRIGIDO: era "ENG. P" (conflitava com Pesca)
    "ENGENHARIA DE PRODUÇÃO MECÂNICA": "ENG. PROD. MEC",
    "ENGENHARIA DE TELECOMUNICAÇÕES": "ENG. TELE",
    "ENGENHARIA QUÍMICA": "ENG. Q",

    # FEAAC
    "ADMINISTRAÇÃO": "ADM",
    "CIÊNCIAS ATUARIAIS": "C. ATU",
    "CIÊNCIAS CONTÁBEIS": "C. CONT",
    "CIÊNCIAS ECONÔMICAS": "C. ECO",
    "FINANÇAS": "FINÇ",
    "SECRETARIADO EXECUTIVO": "S. EXEC",

    # HUMANIDADES
    "BIBLIOTECONOMIA": "BIBLIO",
    "CIÊNCIAS SOCIAIS": "C. SOC",
    "HISTÓRIA": "HIST",
    "LETRAS-LIBRAS": "L. LIBR",
    "LICENCIATURA INTERCULTURAL INDÍGENA PITAKAJÁ": "L.I.I.P",
    "LICENCIATURA INTERCULTURAL INDÍGENA KUABA": "L.I.I.K",
    "PSICOLOGIA": "PSIC",

    # EDUCAÇÃO
    "PEDAGOGIA": "PEDG",

    # CAMPI
    "ANÁLISE E DESENVOLVIMENTO DE SISTEMAS": "ADS",
    "SEGURANÇA DA INFORMAÇÃO": "SEG. INFO",
    "ENGENHARIA DE PRODUÇÃO": "ENG. PROD",
    "ENGENHARIA DE SOFTWARE": "ENG. SOFT",
    "DESIGN DIGITAL": "DES. DIG",
    "REDES DE COMPUTADORES": "REDES",
    "SISTEMAS DE INFORMAÇÃO": "SIST. INFO",
    "ENGENHARIA AMBIENTAL E SANITÁRIA": "ENG. AMB. SAN",
    "ENGENHARIA DE MINAS": "ENG. MINAS",
}


# ------------------------------------------------------------------------------
# Remove duplicados por abreviação (mantém o mais antigo)
# ------------------------------------------------------------------------------
def remover_duplicados_por_abreviacao(abreviacao: str):
    cursos = Curso.objects(abreviacao=abreviacao).order_by("id")

    if cursos.count() > 1:
        # mantém o primeiro, apaga o resto
        for curso in cursos[1:]:
            curso.delete()


# ------------------------------------------------------------------------------
# Carga no banco
# ------------------------------------------------------------------------------
def carregar_cursos():
    print("=" * 80)
    print("CARREGANDO CURSOS COM ABREVIAÇÕES NO BANCO DE DADOS")
    print("SIGLAS EXATAMENTE COMO NO PDF (com correções de duplicatas)")
    print("=" * 80)
    print()

    criados = atualizados = erros = 0

    for nome_curso, sigla in CURSOS_SIGLAS.items():
        try:
            # 🔥 limpa duplicados antes de qualquer coisa
            remover_duplicados_por_abreviacao(sigla)

            curso = Curso.buscar_por_nome(nome_curso)

            if curso:
                if curso.abreviacao != sigla:
                    curso.abreviacao = sigla
                    curso.save()
                    print(f"✓ ATUALIZADO: {nome_curso} → {sigla}")
                    atualizados += 1
                else:
                    print(f"  OK: {nome_curso} → {sigla}")
            else:
                Curso(nome=nome_curso, abreviacao=sigla).save()
                print(f"✓ CRIADO: {nome_curso} → {sigla}")
                criados += 1

        except Exception as e:
            print(f"✗ ERRO ao processar {nome_curso}: {e}")
            erros += 1

    print()
    print("=" * 80)
    print("RESUMO:")
    print(f"  • Cursos criados: {criados}")
    print(f"  • Cursos atualizados: {atualizados}")
    print(f"  • Erros: {erros}")
    print(f"  • Total processado: {len(CURSOS_SIGLAS)}")
    print("=" * 80)


if __name__ == "__main__":
    carregar_cursos()
    print("\n✓ Script executado com sucesso!")