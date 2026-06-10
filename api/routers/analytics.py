"""Analytics API endpoints with rich mock data"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import random
import math

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from api.models.sql.agricultural import StagingProduction

router = APIRouter()

# ─── Image-capable model registry ─────────────────────────────────────────────
CURRENT_ANALYTICS_MODEL = "agri_analytics_v3"
MODEL_SUPPORTS_IMAGES = False


def _generate_timeseries(days: int, base: float, variance: float, trend: float = 0):
    now = datetime.utcnow()
    return [
        {
            "date": (now - timedelta(days=days - i)).strftime("%Y-%m-%d"),
            "value": round(base + math.sin(i * 0.3) * variance + i * trend + random.uniform(-variance * 0.5, variance * 0.5), 2),
        }
        for i in range(days)
    ]


@router.get("/overview")
async def get_analytics_overview(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Vue d'ensemble analytique enrichie"""
    return {
        "indicators": 36,
        "growth": "+12.5%",
        "active_users": 128,
        "alerts_7d": 7,
        "total_production": 2450000,
        "production_unit": "tonnes",
        "avg_confidence": 0.84,
        "countries_covered": 14,
        "data_points": 18450,
        "system_status": "healthy",
        "top_crops": [
            {"name": "Maïs", "value": 42},
            {"name": "Riz", "value": 28},
            {"name": "Manioc", "value": 18},
            {"name": "Arachide", "value": 12},
        ],
        "monthly_production": [
            {"month": "Jan", "value": 185},
            {"month": "Fév", "value": 172},
            {"month": "Mar", "value": 198},
            {"month": "Avr", "value": 215},
            {"month": "Mai", "value": 240},
            {"month": "Jun", "value": 256},
            {"month": "Jul", "value": 268},
            {"month": "Aoû", "value": 245},
            {"month": "Sep", "value": 220},
            {"month": "Oct", "value": 198},
            {"month": "Nov", "value": 175},
            {"month": "Déc", "value": 160},
        ],
        "production_by_crop": [
            {"crop": "Maïs", "tonnes": 45},
            {"crop": "Riz", "tonnes": 32},
            {"crop": "Manioc", "tonnes": 28},
            {"crop": "Mil", "tonnes": 18},
            {"crop": "Sorgho", "tonnes": 15},
            {"crop": "Arachide", "tonnes": 12},
        ],
        "region_stats": [
            {"region": "Dakar", "value": 320},
            {"region": "Thiès", "value": 280},
            {"region": "Saint-Louis", "value": 195},
            {"region": "Kaolack", "value": 210},
            {"region": "Ziguinchor", "value": 175},
            {"region": "Kolda", "value": 145},
        ],
    }


@router.get("/trends/production")
async def get_production_trends(
    period: str = "1Y",
    crop: str = "Maïs",
    current_user: User = Depends(get_current_verified_user),
):
    """Tendances de production"""
    days = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "2Y": 730}
    d = days.get(period, 365)
    base = {"Maïs": 2500, "Riz": 3000, "Manioc": 8000, "Mil": 1200, "Sorgho": 1800, "Arachide": 1500}
    b = base.get(crop, 2000)
    data = _generate_timeseries(min(d, 365), b, b * 0.1, 0.5 / d)
    return {"crop": crop, "period": period, "data": data, "unit": "kg/ha"}


@router.get("/trends/prices")
async def get_price_trends(
    crop: str = "Maïs",
    period: str = "1Y",
    current_user: User = Depends(get_current_verified_user),
):
    """Tendances des prix"""
    end_date = datetime.utcnow()
    start_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    days = start_map.get(period, 365)

    base_prices = {
        "Maïs": 350, "Riz": 650, "Mil": 300, "Sorgho": 320,
        "Arachide": 500, "Manioc": 250, "Igname": 400, "Coton": 600,
    }
    base = base_prices.get(crop, 400)

    data = []
    cursor = end_date - timedelta(days=days)
    step = max(1, days // 52)
    i = 0
    while cursor <= end_date:
        seasonal = math.sin(cursor.month * math.pi / 6) * base * 0.15
        noise = random.uniform(-base * 0.05, base * 0.05)
        data.append({
            "date": cursor.strftime("%Y-%m-%d"),
            "price": round(base + seasonal + noise, 0),
            "crop": crop,
        })
        cursor += timedelta(days=step)
        i += 1

    return {"crop": crop, "period": period, "data": data, "unit": "FCFA/kg"}


@router.get("/trends/weather")
async def get_weather_trends(
    country: str = "Sénégal",
    period: str = "1Y",
    current_user: User = Depends(get_current_verified_user),
):
    """Tendances météo"""
    days = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    d = days.get(period, 365)

    now = datetime.utcnow()
    temps = []
    precip = []
    for i in range(min(d, 60)):
        day = now - timedelta(days=min(d, 60) - i)
        seasonal = 28 + 6 * math.sin((day.month - 1) * math.pi / 6)
        temps.append({
            "date": day.strftime("%Y-%m-%d"),
            "temperature": round(seasonal + random.uniform(-3, 3), 1),
        })
        precip.append({
            "date": day.strftime("%Y-%m-%d"),
            "precipitation": round(max(0, 50 + 40 * math.sin((day.month - 6) * math.pi / 6) + random.uniform(-15, 15)), 1),
        })

    return {
        "country": country,
        "period": period,
        "temperature": temps,
        "precipitation": precip,
        "summary": {
            "avg_temp": round(sum(t["temperature"] for t in temps) / len(temps), 1),
            "avg_precip": round(sum(p["precipitation"] for p in precip) / len(precip), 1),
            "max_temp": max(t["temperature"] for t in temps),
            "min_temp": min(t["temperature"] for t in temps),
        },
    }


@router.get("/compare")
async def compare_countries(
    countries: str = "Sénégal,Nigeria,Ghana",
    crop: str = "Maïs",
    metric: str = "production",
    current_user: User = Depends(get_current_verified_user),
):
    """Comparaison entre pays"""
    country_list = [c.strip() for c in countries.split(",")]

    base_vals = {
        "Sénégal": 1800, "Nigeria": 12000, "Ghana": 3200, "Togo": 850,
        "Côte d'Ivoire": 2800, "Mali": 2200, "Burkina Faso": 1600, "Bénin": 1200,
        "Niger": 800, "Guinée": 950,
    }
    growth_rates = {
        "Sénégal": 0.04, "Nigeria": 0.03, "Ghana": 0.05, "Togo": 0.035,
        "Côte d'Ivoire": 0.045, "Mali": 0.03, "Burkina Faso": 0.025, "Bénin": 0.04,
        "Niger": 0.02, "Guinée": 0.03,
    }

    comparison = {}
    for c in country_list:
        base = base_vals.get(c, 1000)
        growth = growth_rates.get(c, 0.03)
        comparison[c] = [
            {"year": 2020 + i, "value": round(base * (1 + growth) ** i, 0)}
            for i in range(5)
        ]

    return {
        "comparison": comparison,
        "countries": country_list,
        "crop": crop,
        "metric": metric,
        "unit": "tonnes" if metric == "production" else "FCFA/kg",
    }


@router.get("/reports/production")
async def get_production_analytics(
    country: str = None,
    year: int = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Production analytics from DB with fallback"""
    try:
        query = select(
            StagingProduction.year,
            StagingProduction.value.label("production_tonnes"),
            StagingProduction.country_name,
            StagingProduction.crop_name,
        )
        if country:
            query = query.where(StagingProduction.country_name == country)
        if year:
            query = query.where(StagingProduction.year == year)
        result = await db.execute(query)
        rows = result.mappings().all()
        if rows:
            total = sum(r["production_tonnes"] or 0 for r in rows)
            return {"summary": {"total": total, "count": len(rows)}, "data": [dict(r) for r in rows[:100]]}
    except Exception:
        pass

    # Fallback
    now = datetime.utcnow()
    dummy = []
    for i in range(12):
        m = now.month - i
        y = now.year if m > 0 else now.year - 1
        m = m if m > 0 else m + 12
        dummy.append({
            "year": y, "month": m, "crop_name": "Maïs",
            "country_name": country or "Sénégal",
            "production_tonnes": round(2000 + random.uniform(-200, 300), 0),
        })
    return {"summary": {"total": sum(d["production_tonnes"] for d in dummy), "count": len(dummy)}, "data": dummy, "source": "demo"}


@router.get("/reports/weather")
async def get_weather_analytics(
    country: str = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Weather analytics with DB fallback"""
    from api.models.sql.agricultural import StagingWeather
    try:
        query = select(StagingWeather).order_by(StagingWeather.date.desc()).limit(200)
        if country:
            query = query.where(StagingWeather.country.ilike(f"%{country}%"))
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            temps = [r.temperature for r in rows if r.temperature]
            precips = [r.precipitation for r in rows if r.precipitation]
            return {
                "summary": {
                    "avg_temp": round(sum(temps) / len(temps), 2) if temps else None,
                    "avg_precip": round(sum(precips) / len(precips), 2) if precips else None,
                },
                "data": [{"date": r.date.isoformat(), "city": r.city, "country": r.country,
                          "temperature": r.temperature, "precipitation": r.precipitation} for r in rows[:50]],
            }
    except Exception:
        pass
    return {"summary": {"avg_temp": 28.4, "avg_precip": 42.1}, "data": [], "source": "demo"}


@router.get("/reports/economics")
async def get_economics_analytics(
    country: str = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Economic indicators analytics"""
    from api.models.sql.agricultural import StagingEconomic
    try:
        query = select(StagingEconomic).order_by(StagingEconomic.year.desc()).limit(100)
        if country:
            query = query.where(StagingEconomic.country_name.ilike(f"%{country}%"))
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            return {"summary": {"count": len(rows)}, "data": [{
                "country": r.country_name, "indicator": r.indicator,
                "year": r.year, "value": r.value, "unit": r.unit,
            } for r in rows]}
    except Exception:
        pass
    return {"summary": {"count": 0}, "data": [], "source": "demo"}


@router.post("/upload-image")
async def upload_analytics_image(
    file: UploadFile = File(...),
    analysis_type: str = Form(default="general"),
    current_user: User = Depends(get_current_verified_user),
):
    """Upload image for analytics visual analysis"""
    if not MODEL_SUPPORTS_IMAGES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "IMAGE_NOT_SUPPORTED",
                "message": f'Impossible de lire "{file.filename}" (ce modèle ne supporte pas les images). '
                           f'Le modèle "{CURRENT_ANALYTICS_MODEL}" est un modèle d\'analyse de données '
                           f"qui traite uniquement des données numériques et textuelles. "
                           f"Pour l'analyse d'images, utilisez plutôt l'assistant IA.",
                "model": CURRENT_ANALYTICS_MODEL,
                "supported_inputs": ["production", "prix", "météo", "indicateurs économiques", "comparaisons"],
            }
        )
    return {"status": "processing", "message": "Analyse d'image en cours...", "file": file.filename}
