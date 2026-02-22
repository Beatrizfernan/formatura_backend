# ETAPA 1: Imagem Base
# ============================================================================
# FROM = qual sistema operacional base usar
FROM python:3.11-slim

# Evita que Python crie arquivos .pyc (bytecode)
# Por que? Em containers, não precisamos deles (economiza espaço)
ENV PYTHONDONTWRITEBYTECODE=1

# Faz o Python mostrar logs imediatamente (sem buffer)
# Por que? Crucial para ver logs em tempo real no Kubernetes
ENV PYTHONUNBUFFERED=1

ENV PORT=5000

WORKDIR /app


# ============================================================================
# ETAPA 5: Instalar Dependências do Sistema
# ============================================================================
# RUN = executa comandos durante a construção da imagem
# Aqui instalamos pacotes necessários do sistema operacional

RUN apt-get update && apt-get install -y \
    # gcc = compilador C (algumas libs Python precisam)
    gcc \
    # build-essential = ferramentas de compilação
    build-essential \
    # Limpa cache do apt para reduzir tamanho da imagem
    && rm -rf /var/lib/apt/lists/*


COPY requirements.txt .


RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt



COPY . .


RUN useradd -m -u 1000 appuser && \
    # Dá permissão para o usuário acessar /app
    chown -R appuser:appuser /app

# USER = a partir daqui, comandos rodam como este usuário
USER appuser


EXPOSE 5000



HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/')" || exit 1


CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "run:app"]