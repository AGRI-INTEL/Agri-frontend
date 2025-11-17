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