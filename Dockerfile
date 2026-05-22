FROM python:3.12-slim

# Copier les packages depuis le .venv local (pas besoin d'internet)
COPY .venv/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY .venv/bin /usr/local/bin_venv

# Libs système minimales déjà présentes dans python:3.12-slim
# On installe uniquement ce qui est strictement nécessaire au runtime
# en utilisant les packages déjà dans l'image de base
RUN apt-get update --fix-missing -o Acquire::Retries=3 || true && \
    apt-get install -y --no-install-recommends libpq5 curl 2>/dev/null || true && \
    rm -rf /var/lib/apt/lists/*

# Utilisateur non-root
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copier le code (sans .venv grâce au .dockerignore)
COPY --chown=appuser:appuser . .

# Dossiers nécessaires
RUN mkdir -p /app/uploads /app/logs && \
    chown -R appuser:appuser /app/uploads /app/logs

USER appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["python3", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
