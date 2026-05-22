"""
Main API v1 router
"""

from fastapi import APIRouter

from api.routers import (
    auth, users, dashboard, analytics, predictions,
    alerts, chatbot, community, files, geolocation,
    weather, economics, countries, notifications, admin,
)
from api.routers.health import health_router
from api.routers.websocket import websocket_router

api_v1_router = APIRouter()

# ── Core ───────────────────────────────────────────────────────────────────────
api_v1_router.include_router(auth.router,          prefix="/auth",          tags=["Authentication"])
api_v1_router.include_router(users.router,         prefix="/users",         tags=["Users"])

# ── Data & Analytics ──────────────────────────────────────────────────────────
api_v1_router.include_router(dashboard.router,     prefix="/dashboard",     tags=["Dashboard"])
api_v1_router.include_router(analytics.router,     prefix="/analytics",     tags=["Analytics"])
api_v1_router.include_router(weather.router,       prefix="/weather",       tags=["Météo"])
api_v1_router.include_router(economics.router,     prefix="/economics",     tags=["Économie"])
api_v1_router.include_router(countries.router,     prefix="/reference",     tags=["Référentiel (Pays & Cultures)"])

# ── AI & Predictions ──────────────────────────────────────────────────────────
api_v1_router.include_router(predictions.router,   prefix="/predictions",   tags=["AI & Prédictions"])
api_v1_router.include_router(chatbot.router,       prefix="/chatbot",       tags=["AI Chatbot"])

# ── Alerts & Notifications ────────────────────────────────────────────────────
api_v1_router.include_router(alerts.router,        prefix="/alerts",        tags=["Alertes"])
api_v1_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])

# ── Community & Files ─────────────────────────────────────────────────────────
api_v1_router.include_router(community.router,     prefix="/community",     tags=["Communautés & Groupes"])
api_v1_router.include_router(files.router,         prefix="/files",         tags=["Gestion des Fichiers"])

# ── Geolocation ───────────────────────────────────────────────────────────────
api_v1_router.include_router(geolocation.router,   prefix="/geolocation",   tags=["Géolocalisation"])

# ── Admin ─────────────────────────────────────────────────────────────────────
api_v1_router.include_router(admin.router,         prefix="/admin",         tags=["Administration"])

# ── Infrastructure ────────────────────────────────────────────────────────────
api_v1_router.include_router(health_router,                                  tags=["Health"])
api_v1_router.include_router(websocket_router,                               tags=["WebSocket"])
