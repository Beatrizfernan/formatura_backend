"""
Configurações da aplicação
Todas as variáveis sensíveis devem vir de variáveis de ambiente
"""
import os
from dotenv import load_dotenv

load_dotenv()


MONGO_URI = os.environ.get('MONGO_URI')

if not MONGO_URI:
    raise ValueError(
        "❌ ERRO: Variável MONGO_URI não definida!\n"
        "Para desenvolvimento local, crie um arquivo .env com:\n"
        "MONGO_URI=mongodb+srv://...\n\n"
        "Para Docker, rode com:\n"
        "docker run -e MONGO_URI='...' seu-container"
    )