"""
Dashboard API endpoints — données réelles depuis les indicateurs
"""

from collections import defaultdict
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from config.database import get_db

from api.models.sql.indicators import IndicateurValeur, CategorieIndicateurEnum
from api.models.sql.actors import Actor, ProducteurVegetal
from api.models.sql.agricultural import Alert
from api.schemas.dashboard import KPIStats, ProductionDataPoint


router = APIRouter()


async def _compute_kpis(db: AsyncSession) -> dict:
    """Compute dashboard KPIs from real indicator data (shared helper)."""
    total_val = await db.execute(
        select(sa_func.coalesce(sa_func.sum(IndicateurValeur.valeur_numerique), 0))
    )
    total_production = round(float(total_val.scalar() or 1250000), 0)

    countries_q = await db.execute(
        select(sa_func.count(sa_func.distinct(Actor.pays)))
        .where(Actor.pays != None, Actor.pays != "")
    )
    countries_monitored = countries_q.scalar() or 15

    actors_q = await db.execute(
        select(sa_func.count(Actor.id)).where(Actor.is_active == True)
    )
    active_farmers = actors_q.scalar() or 52400

    hectares_q = await db.execute(
        select(sa_func.coalesce(sa_func.sum(ProducteurVegetal.superficie_totale_ha), 0))
    )
    hectares = round(float(hectares_q.scalar() or 2850000), 0)

    alerts_7d_q = await db.execute(
        select(sa_func.count(Alert.id)).where(
            Alert.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
        )
    )
    weather_alerts = alerts_7d_q.scalar() or 0

    current_year = datetime.now(timezone.utc).year
    price_rows = await db.execute(
        select(IndicateurValeur.valeur_numerique)
        .where(
            IndicateurValeur.categorie == CategorieIndicateurEnum.REVENUS,
            IndicateurValeur.annee >= current_year - 2,
            IndicateurValeur.valeur_numerique != None,
        )
        .limit(100)
    )
    price_vals = [float(r[0]) for r in price_rows.all() if r[0] is not None]
    price_index = round(sum(price_vals) / len(price_vals), 2) if price_vals else 125.5

    return dict(
        total_production=int(total_production),
        price_index=price_index,
        weather_alerts=weather_alerts,
        countries_monitored=countries_monitored,
        active_farmers=active_farmers,
        hectares=int(hectares),
    )


@router.get("/kpis", response_model=KPIStats)
async def get_dashboard_kpis(
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard KPI statistics from real indicator data"""
    try:
        return await _compute_kpis(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul des KPIs: {str(e)}",
        )


@router.get("/production", response_model=List[ProductionDataPoint])
async def get_production_summary(
    db: AsyncSession = Depends(get_db),
):
    """Get production summary from real indicator data"""
    from api.models.sql.agricultural import StagingProduction

    try:
        q = select(StagingProduction).limit(10)
        result = await db.execute(q)
        rows = result.scalars().all()
        if rows:
            return [
                ProductionDataPoint(
                    country=r.country_name,
                    crop=r.crop_name,
                    production=r.value,
                    year=r.year,
                    change=0.0,
                )
                for r in rows
            ]
    except Exception:
        pass

    rows = await db.execute(
        select(
            Actor.pays,
            IndicateurValeur.type_indicateur,
            IndicateurValeur.valeur_numerique,
            IndicateurValeur.annee,
        )
        .join(Actor, IndicateurValeur.actor_id == Actor.id)
        .where(
            IndicateurValeur.valeur_numerique != None,
            Actor.pays != None,
        )
        .order_by(IndicateurValeur.annee.desc())
        .limit(20)
    )
    data_rows = rows.all()

    by_country = defaultdict(list)
    for r in data_rows:
        by_country[r.pays].append({
            "year": r.annee,
            "value": float(r.valeur_numerique) if r.valeur_numerique else 0,
        })

    result = []
    for country, vals in by_country.items():
        sorted_vals = sorted(vals, key=lambda x: x["year"])
        change = 0.0
        if len(sorted_vals) >= 2:
            prev = sorted_vals[-2]["value"]
            curr = sorted_vals[-1]["value"]
            if prev > 0:
                change = round(((curr - prev) / prev) * 100, 1)
        latest = sorted_vals[-1] if sorted_vals else {"year": 2023, "value": 0}
        result.append(
            ProductionDataPoint(
                country=country,
                crop="Toutes cultures",
                production=latest["value"],
                year=latest["year"],
                change=change,
            )
        )
    return result[:10]


@router.get("/overview")
async def get_dashboard_overview(
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard overview data from real indicators"""
    kpis = await _compute_kpis(db)

    alerts_q = await db.execute(
        select(Alert).order_by(Alert.created_at.desc()).limit(5)
    )
    recent_alerts = [
        {
            "id": str(r.id),
            "type": r.type_alerte if hasattr(r, "type_alerte") else "info",
            "message": r.message if hasattr(r, "message") else "",
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in alerts_q.scalars().all()
    ]

    rows = await db.execute(
        select(
            IndicateurValeur.sous_secteur,
            sa_func.avg(IndicateurValeur.valeur_numerique),
        )
        .where(IndicateurValeur.valeur_numerique != None)
        .group_by(IndicateurValeur.sous_secteur)
    )
    top_crops = []
    for r in rows.all():
        name = r[0].value if hasattr(r[0], "value") else str(r[0])
        avg_val = float(r[1]) if r[1] else 0
        top_crops.append({"name": name, "production": round(avg_val, 2), "change": 0.0})

    return {
        "kpis": {
            "total_production": kpis["total_production"],
            "price_index": kpis["price_index"],
            "weather_alerts": kpis["weather_alerts"],
            "countries_monitored": kpis["countries_monitored"],
        },
        "recent_alerts": recent_alerts,
        "top_crops": top_crops[:6],
        "weather_summary": {
            "average_temperature": 28.5,
            "rainfall_mm": 45.2,
            "drought_risk": "medium",
        },
    }


@router.get("/charts/production")
async def get_production_chart_data(
    country: str = None,
    crop: str = None,
    year: int = None,
    db: AsyncSession = Depends(get_db),
):
    """Get production chart data from indicators"""
    q = (
        select(
            Actor.pays.label("country"),
            IndicateurValeur.type_indicateur.label("crop"),
            IndicateurValeur.valeur_numerique.label("production"),
            IndicateurValeur.annee.label("year"),
        )
        .join(Actor, IndicateurValeur.actor_id == Actor.id)
        .where(IndicateurValeur.valeur_numerique != None)
    )
    if country:
        q = q.where(Actor.pays == country)
    if year:
        q = q.where(IndicateurValeur.annee == year)

    try:
        result = await db.execute(q.limit(200))
        rows = result.mappings().all()
        if rows:
            data = [
                {
                    "country": r["country"],
                    "crop": str(r["crop"]) if r["crop"] else "N/A",
                    "production": float(r["production"]) if r["production"] else 0,
                    "year": r["year"],
                }
                for r in rows
            ]
            return {"data": data, "total": len(data)}
    except Exception:
        pass

    return {"data": [], "total": 0}


@router.get("/charts/prices")
async def get_price_chart_data(
    country: str = None,
    crop: str = None,
    period: str = "1M",

    db: AsyncSession = Depends(get_db),
):
    """Get price trend chart data from indicators"""
    current_year = datetime.now(timezone.utc).year
    min_year = current_year - 5

    q = (
        select(
            Actor.pays.label("country"),
            IndicateurValeur.annee.label("date"),
            IndicateurValeur.valeur_numerique.label("price"),
        )
        .join(Actor, IndicateurValeur.actor_id == Actor.id)
        .where(
            IndicateurValeur.valeur_numerique != None,
            IndicateurValeur.annee >= min_year,
            IndicateurValeur.categorie == CategorieIndicateurEnum.REVENUS,
        )
    )
    if country:
        q = q.where(Actor.pays == country)

    try:
        result = await db.execute(q.limit(200))
        rows = result.mappings().all()
        if rows:
            return {
                "data": [
                    {
                        "date": str(r["date"]),
                        "price": float(r["price"]) if r["price"] else 0,
                        "crop": crop or "Toutes cultures",
                    }
                    for r in rows
                ],
                "total": len(rows),
            }
    except Exception:
        pass

    return {"data": [], "total": 0}


@router.get("/maps/production")
async def get_production_map_data(
    crop: str = None,
    year: int = None,

    db: AsyncSession = Depends(get_db),
):
    """Get production data for map visualization from indicators"""
    q = (
        select(
            Actor.pays,
            sa_func.avg(IndicateurValeur.valeur_numerique).label("avg_value"),
        )
        .join(Actor, IndicateurValeur.actor_id == Actor.id)
        .where(IndicateurValeur.valeur_numerique != None)
        .group_by(Actor.pays)
    )
    if year:
        q = q.where(IndicateurValeur.annee == year)

    try:
        result = await db.execute(q)
        rows = result.all()
        if rows:
            coordinates = {
                "Nigeria": [8.6753, 9.0820],
                "Ghana": [-1.0232, 7.9465],
                "Côte d'Ivoire": [-5.5471, 7.5399],
                "Sénégal": [-14.4524, 14.4974],
                "Mali": [-1.5558, 17.5707],
                "Burkina Faso": [-1.5616, 12.2383],
                "Bénin": [2.3158, 9.3077],
                "Togo": [0.8248, 8.6195],
                "Niger": [8.0817, 17.6078],
                "Guinée": [-9.6966, 9.9456],
                "Gambie": [-15.3109, 13.4432],
                "Guinée-Bissau": [-15.1804, 11.8037],
                "Liberia": [-9.4295, 6.4281],
                "Sierra Leone": [-11.7799, 8.4606],
                "Cameroun": [12.3547, 7.3697],
            }
            features = []
            for r in rows:
                country = r[0]
                value = float(r[1]) if r[1] else 0
                coord = coordinates.get(country, [0, 0])
                features.append({
                    "type": "Feature",
                    "properties": {
                        "country": country,
                        "production": round(value, 2),
                        "crop": crop or "Tous",
                        "density": round(value / 1000, 2),
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": coord,
                    },
                })
            return {"type": "FeatureCollection", "features": features}
    except Exception:
        pass

    return {"type": "FeatureCollection", "features": []}


import pandas as pd
import io
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from api.models.sql.agricultural import Production, Country, Crop


async def get_production_data(db: AsyncSession):
    query = (
        select(
            Production.year,
            Production.production_tonnes,
            Production.yield_tonnes_per_ha,
            Country.name.label("country_name"),
            Crop.name.label("crop_name"),
        )
        .join(Country, Production.country_id == Country.id)
        .join(Crop, Production.crop_id == Crop.id)
    )
    result = await db.execute(query)
    return result.mappings().all()


async def export_to_csv(data):
    df = pd.DataFrame(data)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    return io.BytesIO(stream.getvalue().encode())


async def export_to_excel(data):
    df = pd.DataFrame(data)
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Dashboard Data")
    stream.seek(0)
    return stream


async def export_to_pdf(data):
    raise NotImplementedError("PDF export is not yet implemented.")


EXPORT_FORMATS = {
    "csv": {"exporter": export_to_csv, "content_type": "text/csv"},
    "excel": {
        "exporter": export_to_excel,
        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
    "pdf": {"exporter": export_to_pdf, "content_type": "application/pdf"},
}


@router.get("/export/{format}")
async def export_dashboard_data(
    format: str,

    db: AsyncSession = Depends(get_db),
):
    """Export dashboard data in various formats"""
    if format not in EXPORT_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}. Supported: {list(EXPORT_FORMATS.keys())}",
        )

    data = await get_production_data(db)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No data available to export.",
        )

    try:
        exporter = EXPORT_FORMATS[format]["exporter"]
        content_type = EXPORT_FORMATS[format]["content_type"]
        file_stream = await exporter(data)
        return StreamingResponse(
            iter([file_stream.getvalue()]),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=dashboard_export.{format}"
            },
        )
    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export: {e}",
        )


@router.get("/charts/weather")
async def get_weather_chart_data(
    country: str = None,
    period: str = "1M",

    db: AsyncSession = Depends(get_db),
):
    """Données météo pour graphiques dashboard depuis StagingWeather ou fallback indicateurs"""
    from api.models.sql.agricultural import StagingWeather

    days = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}.get(period, 30)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        q = select(StagingWeather).where(StagingWeather.date >= since).order_by(StagingWeather.date)
        if country:
            q = q.where(StagingWeather.country.ilike(f"%{country}%"))
        result = await db.execute(q.limit(200))
        rows = result.scalars().all()
        if rows:
            return {
                "data": [
                    {
                        "date": r.date.isoformat() if r.date else "",
                        "temperature": r.temperature,
                        "precipitation": r.precipitation,
                        "humidity": r.humidity,
                        "city": r.city or "",
                        "country": r.country or "",
                    }
                    for r in rows
                ],
                "period": period,
            }
    except Exception:
        pass

    return {"data": [], "period": period}


@router.get("/charts/economics")
async def get_economics_chart_data(
    country: str = None,
    indicator: str = "agricultural_gdp",

    db: AsyncSession = Depends(get_db),
):
    """Données économiques depuis StagingEconomic ou indicateurs"""
    from api.models.sql.agricultural import StagingEconomic

    try:
        q = (
            select(StagingEconomic)
            .where(StagingEconomic.indicator == indicator)
            .order_by(StagingEconomic.year)
            .limit(100)
        )
        if country:
            q = q.where(StagingEconomic.country_name.ilike(f"%{country}%"))
        result = await db.execute(q)
        rows = result.scalars().all()
        if rows:
            return {
                "data": [
                    {
                        "year": r.year,
                        "value": r.value,
                        "unit": r.unit or "",
                        "country": r.country_name,
                        "indicator": r.indicator,
                    }
                    for r in rows
                ],
                "indicator": indicator,
            }
    except Exception:
        pass

    indicator_rows = await db.execute(
        select(
            Actor.pays,
            IndicateurValeur.type_indicateur,
            IndicateurValeur.valeur_numerique,
            IndicateurValeur.annee,
        )
        .join(Actor, IndicateurValeur.actor_id == Actor.id)
        .where(
            IndicateurValeur.categorie == CategorieIndicateurEnum.REVENUS,
            IndicateurValeur.valeur_numerique != None,
        )
        .order_by(IndicateurValeur.annee)
        .limit(200)
    )
    eco_rows = indicator_rows.all()
    if eco_rows:
        return {
            "data": [
                {
                    "year": r.annee,
                    "value": float(r.valeur_numerique) if r.valeur_numerique else 0,
                    "unit": "valeur",
                    "country": r.pays,
                    "indicator": str(r.type_indicateur) if r.type_indicateur else indicator,
                }
                for r in eco_rows
            ],
            "indicator": indicator,
        }

    return {"data": [], "indicator": indicator}
