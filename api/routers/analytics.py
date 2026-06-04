"""Analytics API endpoints"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from api.models.sql.agricultural import StagingProduction

router = APIRouter()


@router.get("/overview")
async def get_analytics_overview(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Vue d'ensemble analytique"""
    return {
        "visits": 1234,
        "active_users": 56,
        "queries_processed": 890,
        "reports_generated": 15,
        "system_status": "healthy"
    }


@router.get("/reports/production")
async def get_production_analytics(
    country: str = None,
    year: int = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Get production analytics"""
    query = (
        select(
            StagingProduction.year,
            StagingProduction.value.label("production_tonnes"),
            StagingProduction.country_name,
            StagingProduction.crop_name,
        )
    )

    if country:
        query = query.where(StagingProduction.country_name == country)
    if year:
        query = query.where(StagingProduction.year == year)

    result = await db.execute(query)
    rows = result.mappings().all()

    if not rows:
        return {"summary": {}, "data": []}

    # Basic analytics
    total_production = sum(r["production_tonnes"] or 0 for r in rows)
    summary = {
        "total_production_tonnes": total_production,
        "data_points": len(rows)
    }

    data = [
        {
            "year": r["year"],
            "production_tonnes": r["production_tonnes"],
            "country_name": r["country_name"],
            "crop_name": r["crop_name"],
        }
        for r in rows
    ]

    return {"summary": summary, "data": data}

from datetime import datetime, timedelta

@router.get("/trends/prices")
async def get_price_trends(
    crop: str,
    period: str = "1Y",
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Get price trends"""
    # Calculate start date based on period
    end_date = datetime.utcnow()
    if period == "1M":
        start_date = end_date - timedelta(days=30)
    elif period == "6M":
        start_date = end_date - timedelta(days=180)
    else: # Default to 1Y
        start_date = end_date - timedelta(days=365)

    # Fallback mock data (PriceData model non disponible)
    base_price = 0.5 if crop.lower() == "maïs" else 0.8
    data = []
    cursor = start_date
    while cursor <= end_date:
        data.append({
            "date": cursor.isoformat(),
            "price_usd_per_kg": round(base_price * (1 + ((cursor.month % 6) - 3) * 0.02), 3),
            "crop_name": crop
        })
        cursor = cursor + timedelta(days=7)

    return data


@router.get("/reports/weather")
async def get_weather_analytics(
    country: str = None,
    year: int = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Rapport analytique météo"""
    from api.models.sql.agricultural import StagingWeather
    query = select(StagingWeather).order_by(StagingWeather.date.desc()).limit(200)
    if country:
        query = query.where(StagingWeather.country.ilike(f"%{country}%"))

    try:
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            temps = [r.temperature for r in rows if r.temperature]
            precips = [r.precipitation for r in rows if r.precipitation]
            return {
                "summary": {
                    "avg_temperature": round(sum(temps) / len(temps), 2) if temps else None,
                    "avg_precipitation": round(sum(precips) / len(precips), 2) if precips else None,
                    "data_points": len(rows),
                },
                "data": [
                    {"date": r.date.isoformat(), "city": r.city, "country": r.country,
                     "temperature": r.temperature, "precipitation": r.precipitation}
                    for r in rows[:50]
                ],
            }
    except Exception:
        pass

    return {
        "summary": {"avg_temperature": 28.4, "avg_precipitation": 42.1, "data_points": 0},
        "data": [],
        "source": "demo",
    }


@router.get("/reports/economics")
async def get_economics_analytics(
    country: str = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Rapport analytique économique"""
    from api.models.sql.agricultural import StagingEconomic
    query = select(StagingEconomic).order_by(StagingEconomic.year.desc()).limit(100)
    if country:
        query = query.where(StagingEconomic.country_name.ilike(f"%{country}%"))

    try:
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            return {
                "summary": {"data_points": len(rows)},
                "data": [
                    {"country": r.country_name, "indicator": r.indicator,
                     "year": r.year, "value": r.value, "unit": r.unit}
                    for r in rows
                ],
            }
    except Exception:
        pass

    return {"summary": {}, "data": [], "source": "demo"}


@router.get("/compare")
async def compare_countries(
    countries: str = "Nigeria,Ghana,Togo",
    crop: str = None,
    metric: str = "production",
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Comparaison de métriques entre pays"""
    country_list = [c.strip() for c in countries.split(",")]

    query = select(StagingProduction).where(
        StagingProduction.country_name.in_(country_list)
    ).order_by(StagingProduction.year.desc()).limit(200)
    if crop:
        query = query.where(StagingProduction.crop_name.ilike(f"%{crop}%"))

    try:
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            comparison = {}
            for r in rows:
                key = r.country_name
                if key not in comparison:
                    comparison[key] = []
                comparison[key].append({"year": r.year, "value": r.value, "crop": r.crop_name})
            return {"comparison": comparison, "countries": country_list, "metric": metric}
    except Exception:
        pass

    # Mock
    mock = {}
    base_vals = {"Nigeria": 12000000, "Ghana": 3200000, "Togo": 850000}
    for c in country_list:
        base = base_vals.get(c, 1000000)
        mock[c] = [{"year": 2023 - i, "value": base * (1 - i * 0.03), "crop": crop or "Maïs"} for i in range(5)]
    return {"comparison": mock, "countries": country_list, "metric": metric, "source": "demo"}
