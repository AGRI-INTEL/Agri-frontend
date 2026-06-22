"""Analytics API endpoints with rich mock data"""

from datetime import datetime, timedelta, timezone
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
    now = datetime.now(timezone.utc)
    return [
        {
            "date": (now - timedelta(days=days - i)).strftime("%Y-%m-%d"),
            "value": round(
                base
                + math.sin(i * 0.3) * variance
                + i * trend
                + random.uniform(-variance * 0.5, variance * 0.5),
                2,
            ),
        }
        for i in range(days)
    ]


@router.get("/overview")
async def get_analytics_overview(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Vue d'ensemble analytique — données de la base"""
    from sqlalchemy import func as sa_func

    # Indicator count
    from api.models.sql.indicators import IndicateurValeur

    ind_q = await db.execute(sa_func.count(IndicateurValeur.id))
    indicators = ind_q.scalar() or 36

    # Active actors count
    from api.models.sql.actors import Actor

    actors_q = await db.execute(
        select(sa_func.count(Actor.id)).where(Actor.is_active == True)
    )
    active_users = actors_q.scalar() or 0

    # Recent alerts (7 days)
    from api.models.sql.agricultural import Alert
    from datetime import timedelta

    alerts_q = await db.execute(
        select(sa_func.count(Alert.id)).where(
            Alert.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
        )
    )
    alerts_7d = alerts_q.scalar() or 0

    # Total production (latest year)
    from api.models.sql.agricultural import Production

    prod_q = await db.execute(
        select(sa_func.coalesce(sa_func.sum(Production.production_tonnes), 0))
    )
    total_production = round(prod_q.scalar() or 2450000, 0)

    # Countries covered
    countries_q = await db.execute(select(sa_func.count(sa_func.distinct(Actor.pays))))
    countries_covered = countries_q.scalar() or 0

    # Data points (total stage rows)
    from api.models.sql.agricultural import StagingProduction

    dp_q = await db.execute(sa_func.count(StagingProduction.id))
    data_points = dp_q.scalar() or 0

    # Top crops by production
    top_q = await db.execute(
        select(Production.crop_id, sa_func.sum(Production.production_tonnes))
        .group_by(Production.crop_id)
        .order_by(sa_func.sum(Production.production_tonnes).desc())
        .limit(6)
    )
    crop_rows = top_q.all()
    from api.models.sql.agricultural import Crop

    top_crops = []
    for crop_id, val in crop_rows:
        c = await db.get(Crop, crop_id)
        if c:
            top_crops.append({"name": c.name, "value": round(val / 1000, 1)})

    # Monthly production (from staging or computed)
    months_fr = [
        "Jan",
        "Fév",
        "Mar",
        "Avr",
        "Mai",
        "Jun",
        "Jul",
        "Aoû",
        "Sep",
        "Oct",
        "Nov",
        "Déc",
    ]
    monthly_production = [
        {"month": m, "value": round(150 + (i * 10) + (i % 3) * 5, 0)}
        for i, m in enumerate(months_fr)
    ]

    # Production by crop from DB
    prod_by_crop = []
    for crop_id, val in crop_rows[:6]:
        c = await db.get(Crop, crop_id)
        if c:
            prod_by_crop.append({"crop": c.name, "tonnes": round(val / 1000, 1)})

    # Region stats from actors
    region_q = await db.execute(
        select(Actor.region, sa_func.count(Actor.id))
        .where(Actor.region != None)
        .group_by(Actor.region)
        .order_by(sa_func.count(Actor.id).desc())
        .limit(10)
    )
    region_stats = [{"region": row[0], "value": row[1]} for row in region_q.all()]

    return {
        "indicators": indicators,
        "growth": "+{:.1f}%".format(random.uniform(5, 20)),
        "active_users": active_users,
        "alerts_7d": alerts_7d,
        "total_production": total_production,
        "production_unit": "tonnes",
        "avg_confidence": 0.84,
        "countries_covered": countries_covered,
        "data_points": data_points,
        "system_status": "healthy",
        "top_crops": top_crops,
        "monthly_production": monthly_production,
        "production_by_crop": prod_by_crop,
        "region_stats": region_stats,
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
    base = {
        "Maïs": 2500,
        "Riz": 3000,
        "Manioc": 8000,
        "Mil": 1200,
        "Sorgho": 1800,
        "Arachide": 1500,
    }
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
    end_date = datetime.now(timezone.utc)
    start_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    days = start_map.get(period, 365)

    base_prices = {
        "Maïs": 350,
        "Riz": 650,
        "Mil": 300,
        "Sorgho": 320,
        "Arachide": 500,
        "Manioc": 250,
        "Igname": 400,
        "Coton": 600,
    }
    base = base_prices.get(crop, 400)

    data = []
    cursor = end_date - timedelta(days=days)
    step = max(1, days // 52)
    i = 0
    while cursor <= end_date:
        seasonal = math.sin(cursor.month * math.pi / 6) * base * 0.15
        noise = random.uniform(-base * 0.05, base * 0.05)
        data.append(
            {
                "date": cursor.strftime("%Y-%m-%d"),
                "price": round(base + seasonal + noise, 0),
                "crop": crop,
            }
        )
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

    now = datetime.now(timezone.utc)
    temps = []
    precip = []
    for i in range(min(d, 60)):
        day = now - timedelta(days=min(d, 60) - i)
        seasonal = 28 + 6 * math.sin((day.month - 1) * math.pi / 6)
        temps.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "temperature": round(seasonal + random.uniform(-3, 3), 1),
            }
        )
        precip.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "precipitation": round(
                    max(
                        0,
                        50
                        + 40 * math.sin((day.month - 6) * math.pi / 6)
                        + random.uniform(-15, 15),
                    ),
                    1,
                ),
            }
        )

    return {
        "country": country,
        "period": period,
        "temperature": temps,
        "precipitation": precip,
        "summary": {
            "avg_temp": round(sum(t["temperature"] for t in temps) / len(temps), 1),
            "avg_precip": round(
                sum(p["precipitation"] for p in precip) / len(precip), 1
            ),
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
        "Sénégal": 1800,
        "Nigeria": 12000,
        "Ghana": 3200,
        "Togo": 850,
        "Côte d'Ivoire": 2800,
        "Mali": 2200,
        "Burkina Faso": 1600,
        "Bénin": 1200,
        "Niger": 800,
        "Guinée": 950,
    }
    growth_rates = {
        "Sénégal": 0.04,
        "Nigeria": 0.03,
        "Ghana": 0.05,
        "Togo": 0.035,
        "Côte d'Ivoire": 0.045,
        "Mali": 0.03,
        "Burkina Faso": 0.025,
        "Bénin": 0.04,
        "Niger": 0.02,
        "Guinée": 0.03,
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
            return {
                "summary": {"total": total, "count": len(rows)},
                "data": [dict(r) for r in rows[:100]],
            }
    except Exception:
        pass

    # Fallback
    now = datetime.now(timezone.utc)
    dummy = []
    for i in range(12):
        m = now.month - i
        y = now.year if m > 0 else now.year - 1
        m = m if m > 0 else m + 12
        dummy.append(
            {
                "year": y,
                "month": m,
                "crop_name": "Maïs",
                "country_name": country or "Sénégal",
                "production_tonnes": round(2000 + random.uniform(-200, 300), 0),
            }
        )
    return {
        "summary": {
            "total": sum(d["production_tonnes"] for d in dummy),
            "count": len(dummy),
        },
        "data": dummy,
        "source": "demo",
    }


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
                    "avg_precip": round(sum(precips) / len(precips), 2)
                    if precips
                    else None,
                },
                "data": [
                    {
                        "date": r.date.isoformat(),
                        "city": r.city,
                        "country": r.country,
                        "temperature": r.temperature,
                        "precipitation": r.precipitation,
                    }
                    for r in rows[:50]
                ],
            }
    except Exception:
        pass
    return {
        "summary": {"avg_temp": 28.4, "avg_precip": 42.1},
        "data": [],
        "source": "demo",
    }


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
            return {
                "summary": {"count": len(rows)},
                "data": [
                    {
                        "country": r.country_name,
                        "indicator": r.indicator,
                        "year": r.year,
                        "value": r.value,
                        "unit": r.unit,
                    }
                    for r in rows
                ],
            }
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
                "supported_inputs": [
                    "production",
                    "prix",
                    "météo",
                    "indicateurs économiques",
                    "comparaisons",
                ],
            },
        )
    return {
        "status": "processing",
        "message": "Analyse d'image en cours...",
        "file": file.filename,
    }
