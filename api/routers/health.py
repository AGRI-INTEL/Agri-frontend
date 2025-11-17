"""
Health check endpoints
"""

from fastapi import APIRouter, Depends
from datetime import datetime
import psutil
import platform

from config.database import get_all_health_status
from config.config import get_settings

settings = get_settings()

health_router = APIRouter(tags=["Health"])


@health_router.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }


@health_router.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with database status"""
    db_status = await get_all_health_status()
    
    # System information
    system_info = {
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "cpu_usage": psutil.cpu_percent(),
        "memory_usage": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent if platform.system() != 'Windows' else psutil.disk_usage('C:\\').percent
    }
    
    # Overall health status
    all_healthy = all(db_status.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "databases": db_status,
        "system": system_info
    }


@health_router.get("/health/ready")
async def readiness_check():
    """Kubernetes readiness probe"""
    db_status = await get_all_health_status()
    
    # Service is ready if at least PostgreSQL is healthy
    ready = db_status.get("postgresql", False)
    
    if ready:
        return {"status": "ready"}
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Service not ready")


@health_router.get("/health/live")
async def liveness_check():
    """Kubernetes liveness probe"""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}