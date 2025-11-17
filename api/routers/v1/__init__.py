"""
API v1 - Routeurs organisés par sous-secteurs et fonctionnalités
Architecture REST moderne avec OpenAPI enrichie
"""

from fastapi import APIRouter
from api.routers.v1 import auth, users, sectors, analytics, geolocation, community, alerts

# Routeur principal v1
api_v1_router = APIRouter(prefix="/v1")

# Authentification et gestion des utilisateurs
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_v1_router.include_router(users.router, prefix="/users", tags=["Users"])

# Routeurs par secteurs (coeur métier)
api_v1_router.include_router(sectors.router, prefix="/sectors", tags=["Sectors"])

# Services transversaux
api_v1_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_v1_router.include_router(geolocation.router, prefix="/geolocation", tags=["Geolocation"])
api_v1_router.include_router(community.router, prefix="/community", tags=["Community"])
api_v1_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts & Notifications"])

# Health check
@api_v1_router.get("/health", tags=["System"])
async def health_check():
    """Vérification de l'état de l'API"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "service": "AgriIntel360 API"
    }