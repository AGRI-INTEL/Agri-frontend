"""
AgriIntel360 - Main FastAPI application entry point
"""

import os
# Limit BLAS/OpenMP threads BEFORE any numpy/scipy import
# Prevents "pthread_create failed: Resource temporarily unavailable" on shared hosting
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')

import asyncio
import uvicorn
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config.config import get_settings
from config.logging import setup_logging
from api.routers.router import api_v1_router
from api.routers.websocket import websocket_router
from src.middleware.security import SecurityHeadersMiddleware
from src.middleware.logging import LoggingMiddleware
from src.middleware.security import RateLimitMiddleware
from src.services.auth import require_admin

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    try:
        from config.database import create_db_and_tables
        await asyncio.wait_for(create_db_and_tables(), timeout=15.0)
    except asyncio.TimeoutError:
        print("⚠️  Database initialization timed out — continuing without DB init")
    except Exception as e:
        print(f"⚠️  Database initialization warning (non-fatal): {e}")

    # Start background tasks
    try:
        from src.tasks.indicator_sync import start_background_tasks
        await asyncio.wait_for(start_background_tasks(app), timeout=5.0)
    except asyncio.TimeoutError:
        print("⚠️  Background task start timed out — continuing")
    except Exception as e:
        import traceback
        print(f"⚠️  Background task start warning: {e}")
        traceback.print_exc()

    print("✅ Lifespan yield — server is ready")
    yield

    print("⏹️  Lifespan shutdown started")
    try:
        from src.tasks.indicator_sync import stop_background_tasks
        await stop_background_tasks(app)
    except Exception as e:
        print(f"⚠️  Background task stop warning: {e}")

    try:
        from config.database import close_db_connections
        await close_db_connections()
    except Exception as e:
        print(f"⚠️  Database shutdown warning: {e}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Plateforme Intelligente de Décision Agricole pour l'Afrique",
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# Prevent Varnish CDN from caching API responses
@app.middleware("http")
async def no_cache_api_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Surrogate-Control"] = "no-store"
    return response


# CORS — single middleware, no duplicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "Origin",
    ],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    max_age=3600,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET_KEY)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(LoggingMiddleware)

if settings.ENVIRONMENT == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")

app.include_router(api_v1_router, prefix=settings.API_V1_STR)
app.include_router(websocket_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {
        "message": f"Bienvenue sur {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "status": "active",
    }


@app.get("/metrics", dependencies=[Depends(require_admin)])
async def metrics_endpoint():
    """Prometheus-style metrics — admin only."""
    from config.database import get_all_health_status
    health = await get_all_health_status()
    return {
        "app_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "services": health,
    }


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
