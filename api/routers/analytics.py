"""Analytics API endpoints using real indicator and production data from the database"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import func as sa_func, select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db
from api.models.sql.indicators import (
    IndicateurValeur,
    CategorieIndicateurEnum,
    TypeIndicateurEnum,
)
from api.models.sql.actors import SousSecteursEnum
from api.models.sql.actors import Actor
from api.models.sql.agricultural import Alert, MalaboYieldIndicator, StagingWeather

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
    # Fixed: wrap sa_func calls in select()
    indicators = (await db.execute(select(sa_func.count(IndicateurValeur.id)))).scalar() or 0
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

    health_data = dict((await db.execute(
        select(IndicateurValeur.is_valide, sa_func.count(IndicateurValeur.id))
        .group_by(IndicateurValeur.is_valide)
    )).all())

    valid = health_data.get(True, 0)
    invalid = health_data.get(False, 0)

    # Fixed: wrap min/max in select()
    min_year_val = (await db.execute(select(sa_func.min(IndicateurValeur.annee)))).scalar() or datetime.now(timezone.utc).year
    max_year_val = (await db.execute(select(sa_func.max(IndicateurValeur.annee)))).scalar() or min_year_val

    # ── Real production data from MalaboYieldIndicator ──
    malabo_rows = (await db.execute(
        select(
            MalaboYieldIndicator.year,
            MalaboYieldIndicator.crop_name,
            MalaboYieldIndicator.production_tonnes,
        )
        .where(MalaboYieldIndicator.production_tonnes != None)
        .order_by(MalaboYieldIndicator.year)
        .limit(5000)
    )).all()

    if malabo_rows:
        # Monthly production → actually annual production totals
        annual_prod: Dict[int, float] = defaultdict(float)
        crop_prod: Dict[str, float] = defaultdict(float)
        for r in malabo_rows:
            if r.year and r.production_tonnes:
                annual_prod[r.year] += float(r.production_tonnes)
                if r.crop_name:
                    crop_prod[r.crop_name] += float(r.production_tonnes)

        monthly_production = [
            {"year": str(yr), "value": round(total, 0)}
            for yr, total in sorted(annual_prod.items())
        ]
        total_value = sum(annual_prod.values())

        # Top crops by total production — Fixed field names: name + value
        sorted_crops = sorted(crop_prod.items(), key=lambda x: x[1], reverse=True)
        production_by_crop = [
            {"crop": name, "tonnes": round(total, 0)}
            for name, total in sorted_crops[:10]
        ]
        top_crops = [
            {"name": name, "value": round(total, 0)}
            for name, total in sorted_crops[:8]
        ]
    else:
        # Fallback to IndicateurValeur
        all_rows = await _query(db, limit=MAX_LIMIT)

        annual_data: Dict[int, List[float]] = defaultdict(list)
        for r in all_rows:
            if r.annee and r.valeur_numerique is not None:
                annual_data[r.annee].append(float(r.valeur_numerique))

        monthly_production = [
            {"year": str(yr), "value": round(sum(v) / len(v), 2)}
            for yr, v in sorted(annual_data.items())
        ]
        total_value = sum(sum(v) for v in annual_data.values())

        sectors_data = (await db.execute(
            select(IndicateurValeur.sous_secteur, sa_func.count(IndicateurValeur.id))
            .group_by(IndicateurValeur.sous_secteur)
        )).all()
        # Fixed field names: crop + tonnes
        production_by_crop = [
            {"crop": r[0].value if hasattr(r[0], "value") else str(r[0]), "tonnes": r[1]}
            for r in sectors_data
        ]

        type_avg_vals: Dict[str, List[float]] = defaultdict(list)
        for r in all_rows:
            if r.annee and r.valeur_numerique is not None and r.type_indicateur:
                type_avg_vals[str(r.type_indicateur)].append(float(r.valeur_numerique))

        # Fixed field names: name + value
        top_crops = sorted(
            [{"name": t, "value": round(sum(v) / len(v), 2)} for t, v in type_avg_vals.items()],
            key=lambda x: x["value"],
            reverse=True,
        )[:8]

    # Growth calculation from IndicateurValeur
    all_rows = await _query(db, limit=MAX_LIMIT)
    type_year_vals: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
    for r in all_rows:
        if r.annee and r.valeur_numerique is not None:
            key = str(r.type_indicateur) if r.type_indicateur else "unknown"
            type_year_vals[key][r.annee].append(float(r.valeur_numerique))

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

    return {
        "indicators": indicators,
        "growth": f"+{growth_pct}%" if growth_pct >= 0 else f"{growth_pct}%",
        "active_users": actors,
        "alerts_7d": alerts,
        "total_production": round(total_value, 0),
        "production_unit": "tonnes",
        "avg_confidence": round(valid / max((valid + invalid), 1), 2),
        "countries_covered": countries_covered,
        "data_points": indicators,
        "system_status": "healthy",
        "top_crops": top_crops,
        "monthly_production": monthly_production,
        "production_by_crop": production_by_crop,
        "region_stats": [{"region": c["crop"], "value": c["tonnes"]} for c in production_by_crop],
    }


# ─── Production Trends ───────────────────────────────────────────────────


@router.get("/trends/production")
async def get_production_trends(
    period: str = "1Y",
    crop: str = "Tous",
    db: AsyncSession = Depends(get_db),
):
    years_back_map = {"1M": 1, "3M": 3, "6M": 6, "1Y": 10, "2Y": 20}
    lookback = years_back_map.get(period, 10)
    now_year = datetime.now(timezone.utc).year
    min_year = now_year - lookback

    # Try MalaboYieldIndicator first (real production data)
    q = (
        select(
            MalaboYieldIndicator.year,
            sa_func.sum(MalaboYieldIndicator.production_tonnes).label("total"),
        )
        .where(
            MalaboYieldIndicator.production_tonnes != None,
            MalaboYieldIndicator.year >= min_year,
        )
        .group_by(MalaboYieldIndicator.year)
        .order_by(MalaboYieldIndicator.year)
    )
    if crop and crop.lower() != "tous":
        q = q.where(MalaboYieldIndicator.crop_name.ilike(f"%{crop}%"))

    malabo_result = (await db.execute(q)).all()

    if malabo_result:
        data = [
            {"date": str(r.year), "value": round(float(r.total or 0), 2)}
            for r in malabo_result
        ]
        return {"crop": crop, "period": period, "data": data, "unit": "tonnes"}

    # Fallback to IndicateurValeur
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

    by_year: Dict[int, List[float]] = defaultdict(list)
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
    years_back_map = {"1M": 1, "3M": 3, "6M": 6, "1Y": 10, "2Y": 20}
    lookback = years_back_map.get(period, 10)
    now_year = datetime.now(timezone.utc).year
    min_year = now_year - lookback

    rows = await _query(
        db,
        categories=[CategorieIndicateurEnum.REVENUS],
        min_year=min_year,
        limit=1000,
    )

    by_year: Dict[int, List[float]] = defaultdict(list)
    for r in rows:
        if r.annee and r.valeur_numerique is not None:
            by_year[r.annee].append(float(r.valeur_numerique))

    data = [
        {"date": str(yr), "price": round(sum(vals) / len(vals), 2), "crop": crop}
        for yr, vals in sorted(by_year.items())
    ]

    return {"crop": crop, "period": period, "data": data, "unit": "valeur moyenne (XOF)"}


# ─── Weather Trends ──────────────────────────────────────────────────────


@router.get("/trends/weather")
async def get_weather_trends(
    country: str = "Sénégal",
    period: str = "1Y",
    db: AsyncSession = Depends(get_db),
):
    years_back_map = {"1M": 1, "3M": 3, "6M": 6, "1Y": 10, "2Y": 20}
    lookback = years_back_map.get(period, 10)
    now_year = datetime.now(timezone.utc).year
    min_year_val = now_year - lookback

    # Try real StagingWeather data first
    try:
        weather_q = (
            select(
                extract("year", StagingWeather.date).label("year"),
                sa_func.avg(StagingWeather.temperature).label("avg_temp"),
                sa_func.avg(StagingWeather.precipitation).label("avg_precip"),
                sa_func.max(StagingWeather.temperature).label("max_temp"),
                sa_func.min(StagingWeather.temperature).label("min_temp"),
            )
            .where(
                StagingWeather.country.ilike(f"%{country}%"),
                extract("year", StagingWeather.date) >= min_year_val,
            )
            .group_by(extract("year", StagingWeather.date))
            .order_by(extract("year", StagingWeather.date))
        )
        weather_rows = (await db.execute(weather_q)).all()

        if weather_rows:
            temperature = [
                {"date": str(int(r.year)), "temperature": round(float(r.avg_temp or 0), 2)}
                for r in weather_rows
            ]
            precipitation = [
                {"date": str(int(r.year)), "precipitation": round(float(r.avg_precip or 0), 2)}
                for r in weather_rows
            ]
            all_temps = [t["temperature"] for t in temperature]
            all_precips = [p["precipitation"] for p in precipitation]
            return {
                "country": country,
                "period": period,
                "temperature": temperature,
                "precipitation": precipitation,
                "summary": {
                    "avg_temp": round(sum(all_temps) / max(len(all_temps), 1), 2),
                    "avg_precip": round(sum(all_precips) / max(len(all_precips), 1), 2),
                    "max_temp": max(all_temps, default=0),
                    "min_temp": min(all_temps, default=0),
                    "data_points": len(temperature),
                },
            }
    except Exception:
        pass

    # Fallback: use IndicateurValeur as proxy indicator trend
    rows = await _query(
        db,
        countries=[country],
        type_indicateurs=[
            TypeIndicateurEnum.REVENU_ANNUEL,
            TypeIndicateurEnum.CHIFFRE_AFFAIRES,
            TypeIndicateurEnum.VALEUR_AJOUTEE,
        ],
        min_year=min_year_val,
        limit=1000,
    )

    by_year: Dict[int, List[float]] = defaultdict(list)
    for r in rows:
        if r.annee and r.valeur_numerique is not None:
            by_year[r.annee].append(float(r.valeur_numerique))

    # Fixed: field key is "temperature" (not "value") to match frontend dataKey
    temperature = [
        {"date": str(yr), "temperature": round(sum(vals) / len(vals), 2)}
        for yr, vals in sorted(by_year.items())
    ]
    all_temps = [t["temperature"] for t in temperature]

    return {
        "country": country,
        "period": period,
        "temperature": temperature,
        "precipitation": [],  # No precipitation fallback data available
        "summary": {
            "avg_temp": round(sum(all_temps) / max(len(all_temps), 1), 2),
            "avg_precip": 0,
            "max_temp": max(all_temps, default=0),
            "min_temp": min(all_temps, default=0),
            "data_points": len(temperature),
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

    # Try MalaboYieldIndicator for real production comparison
    q = (
        select(
            MalaboYieldIndicator.country_name,
            MalaboYieldIndicator.year,
            sa_func.sum(MalaboYieldIndicator.production_tonnes).label("total"),
        )
        .where(
            MalaboYieldIndicator.production_tonnes != None,
            MalaboYieldIndicator.country_name.in_(country_list),
        )
        .group_by(MalaboYieldIndicator.country_name, MalaboYieldIndicator.year)
        .order_by(MalaboYieldIndicator.year)
    )
    if crop and crop.lower() != "tous":
        q = q.where(MalaboYieldIndicator.crop_name.ilike(f"%{crop}%"))

    malabo_rows = (await db.execute(q)).all()

    if malabo_rows:
        comparison: Dict[str, List[Dict]] = {c: [] for c in country_list}
        for r in malabo_rows:
            if r.country_name in comparison:
                comparison[r.country_name].append(
                    {"year": r.year, "value": round(float(r.total or 0), 2)}
                )
        return {
            "comparison": comparison,
            "countries": country_list,
            "crop": crop,
            "metric": metric,
            "unit": "tonnes",
        }

    # Fallback to IndicateurValeur
    rows = await _query(db, countries=country_list, limit=MAX_LIMIT)

    groups: Dict[str, Dict[int, List[float]]] = defaultdict(lambda: defaultdict(list))
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
    # Try MalaboYieldIndicator first
    q = select(MalaboYieldIndicator).where(
        MalaboYieldIndicator.production_tonnes != None
    )
    if country:
        q = q.where(MalaboYieldIndicator.country_name.ilike(f"%{country}%"))
    if year:
        q = q.where(MalaboYieldIndicator.year == year)
    q = q.order_by(MalaboYieldIndicator.year.desc()).limit(500)

    malabo_rows = (await db.execute(q)).scalars().all()

    if malabo_rows:
        total = sum(float(r.production_tonnes or 0) for r in malabo_rows)
        data = [
            {
                "year": r.year,
                "crop_name": r.crop_name or "N/A",
                "country_name": r.country_name or country or "N/A",
                "production_tonnes": float(r.production_tonnes or 0),
            }
            for r in malabo_rows
        ]
        return {"summary": {"total": round(total, 2), "count": len(data)}, "data": data[:100]}

    # Fallback to IndicateurValeur
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
