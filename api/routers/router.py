"""
Main API v1 router
"""

from fastapi import APIRouter

from api.routers import auth, users, dashboard, analytics, predictions, alerts, chatbot, community, files, geolocation

api_v1_router = APIRouter()

# Include all API routers
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_v1_router.include_router(users.router, prefix="/users", tags=["Users"])
api_v1_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_v1_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_v1_router.include_router(predictions.router, prefix="/predictions", tags=["AI & Predictions"])
api_v1_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts & Notifications"])
api_v1_router.include_router(chatbot.router, prefix="/chatbot", tags=["AI Chatbot"])
api_v1_router.include_router(community.router, prefix="/community", tags=["Communautés & Groupes"])
api_v1_router.include_router(files.router, prefix="/files", tags=["Gestion des Fichiers"])
api_v1_router.include_router(geolocation.router, prefix="/geolocation", tags=["Geolocation"])