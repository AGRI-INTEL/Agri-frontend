FROM python:3.11-slim AS builder

# Création d'un utilisateur non privilégié
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Mise à jour des paquets système et correction des vulnérabilités
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libc6-dev \
        libpq-dev \
        postgresql-client \
        gdal-bin \
        libgdal-dev \
        libproj-dev \
        proj-data \
        proj-bin \
        libgeos-dev \
        git \
        curl \
        gnupg2 \
        build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

# Configuration de la sécurité
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/home/appuser/.local/bin:${PATH}"

WORKDIR /app

# Installation des dépendances Python
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --timeout=600 --no-cache-dir -r requirements.txt

# Configuration des variables d'environnement pour GDAL
ENV GDAL_CONFIG=/usr/bin/gdal-config \
    GEOS_CONFIG=/usr/bin/geos-config

# Copie du code de l'application
COPY --chown=appuser:appuser . .

# Création du répertoire uploads avec les bonnes permissions
RUN mkdir -p /app/uploads && \
    chown -R appuser:appuser /app/uploads

# Passage à l'utilisateur non privilégié
USER appuser

# Exposition du port
EXPOSE 8000

# Vérification de la santé
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Démarrage de l'application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]