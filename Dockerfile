# ── Stage 1 : builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential g++ python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --prefer-binary -r requirements.txt --target=/build/packages

# ── Stage 2 : runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# No build tools — only the compiled wheels from stage 1
COPY --from=builder /build/packages /usr/local/lib/python3.12/site-packages

RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    mkdir -p /app/uploads /app/logs && \
    chown -R appuser:appuser /app

COPY --chown=appuser:appuser . .

USER appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "\
import urllib.request, sys; \
resp = urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=5); \
sys.exit(0 if getattr(resp, 'status', 200) == 200 else 1)" || exit 1

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WORKERS:-1}"]
