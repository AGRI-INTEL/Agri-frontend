"""Weather API endpoints"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from api.models.sql.agricultural import StagingWeather

router = APIRouter()


@router.get("/current")
async def get_current_weather(
    country: Optional[str] = Query(None, description="Nom du pays"),
    city: Optional[str] = Query(None, description="Nom de la ville"),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Données météo les plus récentes par pays/ville"""
    query = select(StagingWeather).order_by(desc(StagingWeather.date))
    if country:
        query = query.where(StagingWeather.country.ilike(f"%{country}%"))
    if city:
        query = query.where(StagingWeather.city.ilike(f"%{city}%"))
    query = query.limit(20)

    try:
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            return {
                "data": [
                    {
                        "city": r.city,
                        "country": r.country,
                        "temperature": r.temperature,
                        "humidity": r.humidity,
                        "precipitation": r.precipitation,
                        "wind_speed": r.wind_speed,
                        "weather_condition": r.weather_condition,
                        "date": r.date.isoformat() if r.date else None,
                        "lat": r.lat,
                        "lon": r.lon,
                    }
                    for r in rows
                ],
                "count": len(rows),
            }
    except Exception:
        pass

    # Fallback mock
    return {
        "data": [
            {
                "city": city or "Lomé",
                "country": country or "Togo",
                "temperature": 28.5,
                "humidity": 72.0,
                "precipitation": 12.3,
                "wind_speed": 15.2,
                "weather_condition": "Partiellement nuageux",
                "date": datetime.utcnow().isoformat(),
                "lat": 6.1375,
                "lon": 1.2123,
            }
        ],
        "count": 1,
        "source": "demo",
    }


@router.get("/forecast")
async def get_weather_forecast(
    country: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=14),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Prévisions météo sur N jours (données récentes de la DB ou mock)"""
    since = datetime.utcnow() - timedelta(days=days)
    query = select(StagingWeather).where(StagingWeather.date >= since).order_by(StagingWeather.date)
    if country:
        query = query.where(StagingWeather.country.ilike(f"%{country}%"))
    if city:
        query = query.where(StagingWeather.city.ilike(f"%{city}%"))

    try:
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            return {
                "forecast": [
                    {
                        "date": r.date.isoformat(),
                        "city": r.city,
                        "country": r.country,
                        "temperature_min": round(r.temperature - 3, 1),
                        "temperature_max": round(r.temperature + 3, 1),
                        "temperature_avg": r.temperature,
                        "humidity": r.humidity,
                        "precipitation": r.precipitation,
                        "wind_speed": r.wind_speed,
                        "condition": r.weather_condition or "Inconnu",
                    }
                    for r in rows
                ],
                "days": days,
            }
    except Exception:
        pass

    # Mock forecast
    base_temp = 28.0
    forecast = []
    for i in range(days):
        day = datetime.utcnow() + timedelta(days=i)
        forecast.append({
            "date": day.strftime("%Y-%m-%d"),
            "city": city or "Lomé",
            "country": country or "Togo",
            "temperature_min": round(base_temp - 3 + (i % 3), 1),
            "temperature_max": round(base_temp + 4 + (i % 2), 1),
            "temperature_avg": round(base_temp + (i % 3) * 0.5, 1),
            "humidity": round(70 + (i % 5) * 2, 1),
            "precipitation": round(5 + (i % 4) * 3, 1),
            "wind_speed": round(12 + (i % 3), 1),
            "condition": ["Ensoleillé", "Nuageux", "Pluie légère", "Partiellement nuageux"][i % 4],
        })
    return {"forecast": forecast, "days": days, "source": "demo"}


@router.get("/history")
async def get_weather_history(
    country: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Historique météo avec filtres"""
    query = select(StagingWeather).order_by(desc(StagingWeather.date))
    if country:
        query = query.where(StagingWeather.country.ilike(f"%{country}%"))
    if city:
        query = query.where(StagingWeather.city.ilike(f"%{city}%"))
    if start_date:
        query = query.where(StagingWeather.date >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.where(StagingWeather.date <= datetime.fromisoformat(end_date))
    query = query.limit(limit)

    try:
        result = await db.execute(query)
        rows = result.scalars().all()
        return {
            "history": [
                {
                    "date": r.date.isoformat(),
                    "city": r.city,
                    "country": r.country,
                    "temperature": r.temperature,
                    "humidity": r.humidity,
                    "precipitation": r.precipitation,
                    "wind_speed": r.wind_speed,
                    "pressure": r.pressure,
                    "condition": r.weather_condition,
                }
                for r in rows
            ],
            "count": len(rows),
        }
    except Exception:
        return {"history": [], "count": 0, "source": "demo"}
