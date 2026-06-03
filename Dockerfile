FROM python:3.12-slim

WORKDIR /app

# Removed apt-get step to avoid build failures when the builder
# has no DNS/network access to Debian mirrors. Most Python
# dependencies in `requirements.txt` use prebuilt wheels (e.g.
# `psycopg2-binary`) so system `libpq5` is not required here.
# If Docker cannot resolve PyPI during build, use host networking
# for the build stage or configure daemon DNS settings.

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends build-essential g++ python3-dev && rm -rf /var/lib/apt/lists/*

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=20

# Use BuildKit cache to avoid re-downloading large wheels on retries.
# Requires BuildKit enabled: `DOCKER_BUILDKIT=1` and `COMPOSE_DOCKER_CLI_BUILD=1` when building.
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --prefer-binary --retries $PIP_RETRIES --timeout $PIP_DEFAULT_TIMEOUT -r requirements.txt

# Ensure psutil is installed (some deployments import it directly)
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install psutil==5.9.5

COPY . .

RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    mkdir -p /app/uploads /app/logs && \
    chown -R appuser:appuser /app/uploads /app/logs

USER appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys;\
resp=urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=5);\
sys.exit(0 if getattr(resp, 'status', 200)==200 else 1)" || exit 1

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
