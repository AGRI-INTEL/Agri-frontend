"""
Main API v1 router
"""

from fastapi import APIRouter

from api.routers.auth import router as auth_router
from api.routers.users import router as users_router
from api.routers.dashboard import router as dashboard_router
from api.routers.analytics import router as analytics_router
from api.routers.predictions import router as predictions_router
from api.routers.alerts import router as alerts_router
from api.routers.chatbot import router as chatbot_router
from api.routers.community import router as community_router
from api.routers.files import router as files_router
from api.routers.geolocation import router as geolocation_router
from api.routers.weather import router as weather_router
from api.routers.economics import router as economics_router
from api.routers.countries import router as countries_router
from api.routers.notifications import router as notifications_router
from api.routers.admin import router as admin_router
from api.routers.actors import router as actors_router
from api.routers.messaging import router as messaging_router
from api.routers.indicators import router as indicators_router
from api.routers.health import health_router
from api.routers.websocket import websocket_router

api_v1_router = APIRouter()

@api_v1_router.get("/")
async def api_v1_root():
    return {"message": "AgriIntel360 API v1", "status": "operational"}

# ── Core ───────────────────────────────────────────────────────────────────────
api_v1_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_v1_router.include_router(users_router, prefix="/users", tags=["Users"])

# ── Data & Analytics ──────────────────────────────────────────────────────────
api_v1_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_v1_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
api_v1_router.include_router(
    indicators_router, prefix="/indicators", tags=["Indicateurs Agricoles"]
)
api_v1_router.include_router(weather_router, prefix="/weather", tags=["Météo"])
api_v1_router.include_router(economics_router, prefix="/economics", tags=["Économie"])
api_v1_router.include_router(
    countries_router, prefix="/reference", tags=["Référentiel (Pays & Cultures)"]
)

# ── AI & Predictions ──────────────────────────────────────────────────────────
api_v1_router.include_router(
    predictions_router, prefix="/predictions", tags=["AI & Prédictions"]
)
api_v1_router.include_router(chatbot_router, prefix="/chatbot", tags=["AI Chatbot"])

# ── Alerts & Notifications ────────────────────────────────────────────────────
api_v1_router.include_router(alerts_router, prefix="/alerts", tags=["Alertes"])
api_v1_router.include_router(
    notifications_router, prefix="/notifications", tags=["Notifications"]
)

# ── Community & Files ─────────────────────────────────────────────────────────
api_v1_router.include_router(
    community_router, prefix="/community", tags=["Communautés & Groupes"]
)
api_v1_router.include_router(
    files_router, prefix="/files", tags=["Gestion des Fichiers"]
)

# ── Geolocation ───────────────────────────────────────────────────────────────
api_v1_router.include_router(
    geolocation_router, prefix="/geolocation", tags=["Géolocalisation"]
)

# ── Actors ────────────────────────────────────────────────────────────────────
api_v1_router.include_router(
    actors_router, prefix="/actors", tags=["Acteurs Agricoles"]
)

# ── Messaging ─────────────────────────────────────────────────────────────────
api_v1_router.include_router(
    messaging_router, prefix="/messaging", tags=["Messagerie"]
)

# ── Admin ─────────────────────────────────────────────────────────────────────
api_v1_router.include_router(admin_router, prefix="/admin", tags=["Administration"])

# ── Infrastructure ────────────────────────────────────────────────────────────
api_v1_router.include_router(health_router, prefix="/health", tags=["Health"])
# WebSocket router is now mounted directly on the app in main.py to bypass HTTP middleware
