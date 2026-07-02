"""
Agricultural Calendar API endpoints
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.database import get_db
from src.services.auth import get_current_verified_user
from src.services.calendar import calendar_service
from api.models.sql.user import User
from api.models.sql.agricultural import Country, Crop

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/crops")
async def get_available_crops():
    """Returns list of available crops with their seasons from calendar service"""
    crops_with_seasons = []
    for crop_name, events in calendar_service.CROP_CALENDARS.items():
        season_months = set()
        for evt in events:
            if evt["start_month"] <= evt["end_month"]:
                season_months.update(range(evt["start_month"], evt["end_month"] + 1))
            else:
                season_months.update(range(evt["start_month"], 13))
                season_months.update(range(1, evt["end_month"] + 1))
        crops_with_seasons.append({
            "name": crop_name,
            "events": len(events),
            "season_months": sorted(season_months),
        })
    return {"crops": crops_with_seasons, "count": len(crops_with_seasons)}


@router.get("/seasons/{country}")
async def get_seasonal_forecast(
    country: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    current_user: User = Depends(get_current_verified_user),
):
    """Returns seasonal forecast for a given country and optional month"""
    import datetime
    target_month = month or datetime.datetime.now().month
    forecast = calendar_service.get_seasonal_forecast(country, target_month)
    if not forecast:
        raise HTTPException(status_code=404, detail="Prévisions saisonnières non disponibles pour ce pays")
    return forecast


@router.get("/{crop}/{country}/{year}")
async def get_calendar(
    crop: str,
    country: str,
    year: int,
    current_user: User = Depends(get_current_verified_user),
):
    """Returns monthly agricultural calendar for a crop in a country for a given year"""
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="Année invalide. Choisissez une année entre 2000 et 2100")
    result = calendar_service.get_calendar(crop, country, year)
    if not result or not result.get("calendar"):
        raise HTTPException(status_code=404, detail="Calendrier non trouvé pour cette culture et ce pays")
    return result
