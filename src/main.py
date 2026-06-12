"""
AgriIntel360 - Main FastAPI application entry point
"""

import os
import uvicorn
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config.config import get_settings

# Commented out database imports to avoid connection issues
# from config.database import create_db_and_tables, close_db_connections
from config.logging import setup_logging

# Uncommented router imports
from api.routers.router import api_v1_router

# from api.routers.health import health_router
from api.routers.websocket import websocket_router
from src.middleware.security import SecurityHeadersMiddleware
from src.middleware.logging import LoggingMiddleware
from src.middleware.security import RateLimitMiddleware


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    setup_logging()
    # try:
    #     from config.database import create_db_and_tables
    #
    #     await create_db_and_tables()
    # except Exception as e:
    #     # Do not fail app startup in development when DB is unavailable.
    #     # Log the error and continue so frontend/dev work can proceed.
    #     print(f"❌ Database initialization error: {e}")
    #     if settings.DEBUG:
    #         print("⚠️  Database startup failure (continuing in DEBUG mode)")
    #     else:
    #         # In production, we should fail early.
    #         raise

    yield

    # Shutdown
    try:
        from config.database import close_db_connections

        await close_db_connections()
    except Exception as e:
        print(f"⚠️  Database shutdown warning: {e}")


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Plateforme Intelligente de Décision Agricole pour l'Afrique",
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)


# Ensure CORS headers are always present (including on exceptions)
@app.middleware("http")
async def ensure_cors_headers(request: Request, call_next):
    # Skip WebSocket requests (handled by the WS router directly)
    if request.scope.get("type") == "websocket":
        return await call_next(request)
    
    origin = request.headers.get("origin")
    
    # Handle OPTIONS preflight quickly
    if request.method == "OPTIONS":
        from fastapi.responses import Response
        res = Response(status_code=204)
        
        if origin and (
            origin in settings.BACKEND_CORS_ORIGINS
            or "*" in settings.BACKEND_CORS_ORIGINS
        ):
            res.headers["Access-Control-Allow-Origin"] = origin
        elif settings.BACKEND_CORS_ORIGINS:
            # Fallback to the first allowed origin instead of joining them
            res.headers["Access-Control-Allow-Origin"] = settings.BACKEND_CORS_ORIGINS[0]
            
        res.headers["Access-Control-Allow-Credentials"] = "true"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept, Origin"
        return res

    try:
        response = await call_next(request)
    except Exception as exc:
        response = JSONResponse(status_code=500, content={"detail": str(exc)})

    if origin and (
        origin in settings.BACKEND_CORS_ORIGINS or "*" in settings.BACKEND_CORS_ORIGINS
    ):
        response.headers["Access-Control-Allow-Origin"] = origin
    elif settings.BACKEND_CORS_ORIGINS:
        # Fallback to the first allowed origin
        response.headers["Access-Control-Allow-Origin"] = settings.BACKEND_CORS_ORIGINS[0]
        
    response.headers.setdefault("Access-Control-Allow-Credentials", "true")
    response.headers.setdefault(
        "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    )
    response.headers.setdefault(
        "Access-Control-Allow-Headers",
        "Content-Type, Authorization, X-Requested-With, Accept, Origin",
    )

    return response


# CORS Middleware
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

# Security Middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET_KEY)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(LoggingMiddleware)

# Trusted Host Middleware
if settings.ENVIRONMENT == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

# Static files
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")

# Include API routers (API v1 routes go through middleware)
app.include_router(api_v1_router, prefix=settings.API_V1_STR)

# WebSocket router bypasses HTTP middleware (BaseHTTPMiddleware doesn't support WS)
app.include_router(websocket_router, prefix=settings.API_V1_STR)


# Simple test endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"Bienvenue sur {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "status": "active",
    }


# Health check endpoint — géré par health_router dans /api/v1/health


# Metrics endpoint
@app.get("/metrics")
async def metrics_endpoint():
    """Metrics endpoint for Prometheus"""
    # Simple metrics response
    return {
        "app_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running",
        "uptime": "available",
        "requests_total": 0,
        "errors_total": 0,
    }


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
