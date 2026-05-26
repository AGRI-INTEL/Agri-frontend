"""Mock endpoints to avoid 404s during development.

These provide minimal, safe responses for frontend dev environment.
"""

from fastapi import APIRouter
from typing import Any
from datetime import datetime

router = APIRouter()


@router.get("/actors")
async def list_actors(limit: int = 100, page: int = 1) -> Any:
    return {
        "data": [
            {"id": "actor-1", "name": "Ferme démo", "type": "farmer", "location": "Unknown"}
        ],
        "meta": {"page": page, "limit": limit, "total": 1}
    }


@router.get("/dashboard/kpis")
async def dashboard_kpis() -> Any:
    return {
        "kpis": {"active_farmers": 50000, "hectares": 2500000, "countries": 12}
    }


@router.get("/dashboard/production")
async def dashboard_production() -> Any:
    return {
        "production": {"estimate_tonnes": 120000, "trend": "stable"}
    }


@router.get("/analytics/overview")
async def analytics_overview() -> Any:
    return {"overview": {"visits": 1234, "active": 56}}


@router.get("/chatbot/conversations")
async def chatbot_conversations() -> Any:
    return {"data": [], "meta": {"total": 0}}


@router.get("/files")
async def list_files() -> Any:
    return {"data": []}
