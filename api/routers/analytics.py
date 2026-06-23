"""Analytics API endpoints using real indicator data from the database"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db
from api.models.sql.indicators import (
    IndicateurValeur,
    CategorieIndicateurEnum,
    SousSecteursEnum,
    TypeIndicateurEnum,
)
from api.models.sql.actors import Actor
from api.models.sql.agricultural import Alert

router = APIRouter()

MAX_LIMIT = 5000

# ─── Helpers ─────────────────────────────────────────────────────────────


async def _query(
    db: AsyncSession,
    countries: Optional[List[str]] = None,
    categories: Optional[List[CategorieIndicateurEnum]] = None,
    sectors: Optional[List[SousSecteursEnum]] = None,
    type_indicateurs: Optional[List[TypeIndicateurEnum]] = None,
    min_year: Optional[int] = None,
    limit: int = MAX_LIMIT,
) -> List[tuple]:
    q = (
        select(
            IndicateurValeur.annee,
            IndicateurValeur.valeur_numerique,
            IndicateurValeur.type_indicateur,
            IndicateurValeur.categorie,
            IndicateurValeur.sous_secteur,
            Actor.pays,
        )
        .join(Actor, IndicateurValeur.actor_id == Actor.id)
        .where(IndicateurValeur.valeur_numerique != None)
    )
    if countries:
        q = q.where(Actor.pays.in_(countries))
    if categories:
        q = q.where(IndicateurValeur.categorie.in_(categories))
    if sectors:
        q = q.where(IndicateurValeur.sous_secteur.in_(sectors))
    if type_indicateurs:
        q = q.where(IndicateurValeur.type_indicateur.in_(type_indicateurs))
    if min_year:
        q = q.where(IndicateurValeur.annee >= min_year)
    result = await db.execute(q.limit(limit))
    return result.all()


async def _countries(db: AsyncSession) -> List[str]:
    rows = await db.execute(
        select(Actor.pays)
        .where(Actor.pays != None, Actor.pays != "")
        .distinct()
        .order_by(Actor.pays)
    )
    return [r[0] for r in rows.all()]


# ─── Overview ────────────────────────────────────────────────────────────


@router.get("/overview")
async def get_analytics_overview(db: AsyncSession = Depends(get_db)):
    indicators = (await db.execute(sa_func.count(IndicateurValeur.id))).scalar() or 0
    actors = (await db.execute(
        select(sa_func.count(Actor.id)).where(Actor.is_active == True)
    )).scalar() or 0
    alerts = (await db.execute(
        select(sa_func.count(Alert.id)).where(
            Alert.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
        )
    )).scalar() or 0

    countries = await _countries(db)
    countries_covered = len(countries)

    cats = (await db.execute(
        select(sa_func.count(sa_func.distinct(IndicateurValeur.categorie)))
    )).scalar() or 0

    sectors_data = (await db.execute(
        select(IndicateurValeur.sous_secteur, sa_func.count(IndicateurValeur.id))
        .group_by(IndicateurValeur.sous_secteur)
    )).all()
    by_sector = [
        {"sector": r[0].value if hasattr(r[0], "value") else str(r[0]), "count": r[1]}
        for r in sectors_data
    ]

    health_data = dict((await db.execute(
        select(IndicateurValeur.is_valide, sa_func.count(IndicateurValeur.id))
        .group_by(IndicateurValeur.is_valide)
    )).all())

    valid = health_data.get(True, 0)
    invalid = health_data.get(False, 0)

    min_year = (await db.execute(sa_func.min(IndicateurValeur.annee))).scalar() or datetime.now(timezone.utc).year
    max_year = (await db.execute(sa_func.max(IndicateurValeur.annee))).scalar() or min_year

    all_rows = await _query(db, limit=MAX_LIMIT)

    # Per-type per-year average for growth computation
    type_year_vals = defaultdict(lambda: defaultdict(list))
    for r in all_rows:
        if r.annee and r.valeur_numerique is not None:
            key = str(r.type_indicateur) if r.type_indicateur else "unknown"
            type_year_vals[key][r.annee].append(float(r.valeur_numerique))

    # Compute average YoY growth per indicator type, then combine
    growth_rates = []
    for t, yr_vals in type_year_vals.items():
        sorted_yrs = sorted(yr_vals.keys())
        if len(sorted_yrs) >= 2:
            for i in range(1, len(sorted_yrs)):
                prev_avg = sum(yr_vals[sorted_yrs[i - 1]]) / len(yr_vals[sorted_yrs[i - 1]])
                curr_avg = sum(yr_vals[sorted_yrs[i]]) / len(yr_vals[sorted_yrs[i]])
                if prev_avg > 0:
                    growth_rates.append((curr_avg - prev_avg) / prev_avg)

    growth_pct = round((sum(growth_rates) / len(growth_rates)) * 100, 1) if growth_rates else 0

    # Top indicator types by average value
    type_avg_vals = defaultdict(list)
    for r in all_rows:
        if r.annee and r.valeur_numerique is not None and r.type_indicateur:
            type_avg_vals[str(r.type_indicateur)].append(float(r.valeur_numerique))

    top_types = sorted(
        [{"indicator_type": t, "avg_value": round(sum(v) / len(v), 2)} for t, v in type_avg_vals.items()],
        key=lambda x: x["avg_value"],
        reverse=True,
    )[:10]

    # Annual totals for chart
    annual_data = defaultdict(list)
    for r in all_rows:
        if r.annee and r.valeur_numerique is not None:
            annual_data[r.annee].append(float(r.valeur_numerique))

    annual_avg = [
        {"year": str(yr), "value": round(sum(v) / len(v), 2)}
        for yr, v in sorted(annual_data.items())
    ]

    total_value = sum(sum(v) for v in annual_data.values())

    return {
        "indicators": indicators,
        "growth": f"+{growth_pct}%" if growth_pct >= 0 else f"{growth_pct}%",
        "active_users": actors,
        "alerts_7d": alerts,
        "total_production": round(total_value, 0),
        "production_unit": "valeur cumulée",
        "avg_confidence": round(
            valid / max((valid + invalid), 1), 2
        ),
        "countries_covered": countries_covered,
        "data_points": indicators,
        "system_status": "healthy",
        "top_crops": top_types[:8],
        "monthly_production": annual_avg,
        "production_by_crop": by_sector,
        "region_stats": [{"region": s["sector"], "value": s["count"]} for s in by_sector],
    }


# ─── Production Trends ───────────────────────────────────────────────────


@router.get("/trends/production")
async def get_production_trends(
    period: str = "1Y",
    crop: str = "Tous",
    db: AsyncSession = Depends(get_db),
):
    days_map = {"1M": 1, "3M": 3, "6M": 6, "1Y": 10, "2Y": 20}
    lookback = days_map.get(period, 10)
    now_year = datetime.now(timezone.utc).year
    min_year = now_year - lookback

    rows = await _query(
        db,
        type_indicateurs=[
            TypeIndicateurEnum.CHIFFRE_AFFAIRES,
            TypeIndicateurEnum.VALEUR_AJOUTEE,
            TypeIndicateurEnum.REVENU_ANNUEL,
        ],
        min_year=min_year,
        limit=1000,
    )

    by_year = defaultdict(list)
    for r in rows:
        if r.annee and r.valeur_numerique is not None:
            by_year[r.annee].append(float(r.valeur_numerique))

    data = [
        {"date": str(yr), "value": round(sum(vals) / len(vals), 2)}
        for yr, vals in sorted(by_year.items())
    ]

    return {"crop": crop, "period": period, "data": data, "unit": "valeur moyenne"}


# ─── Price Trends ────────────────────────────────────────────────────────


@router.get("/trends/prices")
async def get_price_trends(
    crop: str = "Tous",
    period: str = "1Y",
    db: AsyncSession = Depends(get_db),
):
    days_map = {"1M": 1, "3M": 3, "6M": 6, "1Y": 10, "2Y": 20}
    lookback = days_map.get(period, 10)
    now_year = datetime.now(timezone.utc).year
    min_year = now_year - lookback

    rows = await _query(
        db,
        categories=[CategorieIndicateurEnum.REVENUS],
        min_year=min_year,
        limit=1000,
    )

    by_year = defaultdict(list)
    for r in rows:
        if r.annee and r.valeur_numerique is not None:
            by_year[r.annee].append(float(r.valeur_numerique))

    data = [
        {"date": str(yr), "price": round(sum(vals) / len(vals), 2), "crop": crop}
        for yr, vals in sorted(by_year.items())
    ]

    return {"crop": crop, "period": period, "data": data, "unit": "valeur moyenne"}


# ─── Weather Trends ──────────────────────────────────────────────────────


@router.get("/trends/weather")
async def get_weather_trends(
    country: str = "Sénégal",
    period: str = "1Y",
    db: AsyncSession = Depends(get_db),
):
    days_map = {"1M": 1, "3M": 3, "6M": 6, "1Y": 10, "2Y": 20}
    lookback = days_map.get(period, 10)
    now_year = datetime.now(timezone.utc).year
    min_year = now_year - lookback

    rows = await _query(
        db,
        countries=[country],
        type_indicateurs=[
            TypeIndicateurEnum.REVENU_ANNUEL,
            TypeIndicateurEnum.CHIFFRE_AFFAIRES,
            TypeIndicateurEnum.VALEUR_AJOUTEE,
        ],
        min_year=min_year,
        limit=1000,
    )

    by_year = defaultdict(list)
    for r in rows:
        if r.annee and r.valeur_numerique is not None:
            by_year[r.annee].append(float(r.valeur_numerique))

    indicators_data = [
        {"date": str(yr), "value": round(sum(vals) / len(vals), 2)}
        for yr, vals in sorted(by_year.items())
    ]

    return {
        "country": country,
        "period": period,
        "temperature": indicators_data,
        "summary": {
            "avg_value": round(
                sum(d["value"] for d in indicators_data) / max(len(indicators_data), 1), 2
            ),
            "max_value": max((d["value"] for d in indicators_data), default=0),
            "min_value": min((d["value"] for d in indicators_data), default=0),
            "data_points": len(indicators_data),
        },
    }


# ─── Country Comparison ──────────────────────────────────────────────────


@router.get("/compare")
async def compare_countries(
    countries: str = "Sénégal,Nigeria,Ghana",
    crop: str = "Tous",
    metric: str = "production",
    db: AsyncSession = Depends(get_db),
):
    country_list = [c.strip() for c in countries.split(",") if c.strip()]

    rows = await _query(db, countries=country_list, limit=MAX_LIMIT)

    groups = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.annee and r.valeur_numerique is not None and r.pays:
            groups[r.pays][r.annee].append(float(r.valeur_numerique))

    comparison = {}
    for c in country_list:
        years_data = groups.get(c, {})
        comparison[c] = [
            {"year": yr, "value": round(sum(vals) / len(vals), 2)}
            for yr, vals in sorted(years_data.items())
        ]

    return {
        "comparison": comparison,
        "countries": country_list,
        "crop": crop,
        "metric": metric,
        "unit": "valeur moyenne",
    }


# ─── Reports ─────────────────────────────────────────────────────────────


@router.get("/reports/production")
async def get_production_analytics(
    country: Optional[str] = None,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    rows = await _query(
        db,
        countries=[country] if country else None,
        type_indicateurs=[
            TypeIndicateurEnum.REVENU_ANNUEL,
            TypeIndicateurEnum.CHIFFRE_AFFAIRES,
            TypeIndicateurEnum.VALEUR_AJOUTEE,
        ],
        limit=2000,
    )

    data = []
    total = 0.0
    for r in rows:
        if r.valeur_numerique is not None:
            val = float(r.valeur_numerique)
            if year and r.annee != year:
                continue
            total += val
            data.append({
                "year": r.annee,
                "crop_name": str(r.type_indicateur) if r.type_indicateur else "N/A",
                "country_name": r.pays or country or "N/A",
                "production_tonnes": val,
            })

    return {"summary": {"total": round(total, 2), "count": len(data)}, "data": data[:100]}


@router.get("/reports/weather")
async def get_weather_analytics(
    country: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    from api.models.sql.agricultural import StagingWeather

    try:
        q = select(StagingWeather).order_by(StagingWeather.date.desc()).limit(200)
        if country:
            q = q.where(StagingWeather.country.ilike(f"%{country}%"))
        result = await db.execute(q)
        rows = result.scalars().all()
        if rows:
            temps = [r.temperature for r in rows if r.temperature is not None]
            precips = [r.precipitation for r in rows if r.precipitation is not None]
            return {
                "summary": {
                    "avg_temp": round(sum(temps) / len(temps), 2) if temps else None,
                    "avg_precip": round(sum(precips) / len(precips), 2) if precips else None,
                },
                "data": [
                    {
                        "date": r.date.isoformat() if r.date else "",
                        "city": r.city or "",
                        "country": r.country or "",
                        "temperature": r.temperature,
                        "precipitation": r.precipitation,
                    }
                    for r in rows[:50]
                ],
            }
    except Exception:
        pass

    return {"summary": {"avg_temp": None, "avg_precip": None}, "data": []}


@router.get("/reports/economics")
async def get_economics_analytics(
    country: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    from api.models.sql.agricultural import StagingEconomic

    try:
        q = select(StagingEconomic).order_by(StagingEconomic.year.desc()).limit(100)
        if country:
            q = q.where(StagingEconomic.country_name.ilike(f"%{country}%"))
        result = await db.execute(q)
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

    return {"summary": {"count": 0}, "data": []}


@router.post("/upload-image")
async def upload_analytics_image(
    file: UploadFile = File(...),
    analysis_type: str = Form(default="general"),
):
    raise HTTPException(
        status_code=400,
        detail={
            "code": "IMAGE_NOT_SUPPORTED",
            "message": "Ce module d'analyses traite uniquement des données numériques. "
            "Utilisez l'assistant IA pour l'analyse d'images.",
        },
    )
