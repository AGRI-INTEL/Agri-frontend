"""
Dashboard API endpoints — données réelles depuis les indicateurs
"""

import json
from collections import defaultdict
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from config.database import get_db
from src.services.redis import get_redis

from api.models.sql.indicators import IndicateurValeur, CategorieIndicateurEnum
from api.models.sql.actors import Actor, ProducteurVegetal
from api.models.sql.agricultural import Alert
from api.schemas.dashboard import KPIStats, ProductionDataPoint


router = APIRouter()

CACHE_TTL = 300  # 5 minutes


async def _get_cached(cache_key: str):
    try:
        r = await get_redis()
        if r is not None:
            val = await r.get(cache_key)
            if val is not None:
                return json.loads(val)
    except Exception:
        pass
    return None


async def _set_cached(cache_key: str, data, ttl: int = CACHE_TTL):
    try:
        r = await get_redis()
        if r is not None:
            await r.setex(cache_key, ttl, json.dumps(data, default=str))
    except Exception:
        pass


async def _invalidate_cache(pattern: str):
    """Invalidate all cache keys matching a pattern (e.g. 'dashboard:*')."""
    try:
        r = await get_redis()
        if r is not None:
            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor=cursor, match=pattern, count=50)
                if keys:
                    await r.delete(*keys)
                if cursor == 0:
                    break
    except Exception:
        pass


async def _compute_kpis(db: AsyncSession) -> dict:
    """Compute dashboard KPIs from real indicator data (shared helper)."""
    has_real_data = False

    total_val = await db.execute(
        select(sa_func.coalesce(sa_func.sum(IndicateurValeur.valeur_numerique), 0))
    )
    raw_total = total_val.scalar() or 0
    total_production = round(float(raw_total), 0)
    if raw_total:
        has_real_data = True

    countries_q = await db.execute(
        select(sa_func.count(sa_func.distinct(Actor.pays)))
        .where(Actor.pays != None, Actor.pays != "")
    )
    countries_raw = countries_q.scalar() or 0
    countries_monitored = countries_raw
    if countries_raw:
        has_real_data = True

    actors_q = await db.execute(
        select(sa_func.count(Actor.id)).where(Actor.is_active == True)
    )
    actors_raw = actors_q.scalar() or 0
    active_farmers = actors_raw
    if actors_raw:
        has_real_data = True

    hectares_q = await db.execute(
        select(sa_func.coalesce(sa_func.sum(ProducteurVegetal.superficie_totale_ha), 0))
    )
    hectares_raw = hectares_q.scalar() or 0
    hectares = round(float(hectares_raw), 0)
    if hectares_raw:
        has_real_data = True

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
    price_index = round(sum(price_vals) / len(price_vals), 2) if price_vals else 0.0
    if price_vals:
        has_real_data = True

    return dict(
        total_production=int(total_production),
        price_index=price_index,
        weather_alerts=weather_alerts,
        countries_monitored=countries_monitored,
        active_farmers=active_farmers,
        hectares=int(hectares),
        is_estimated=not has_real_data,
    )


@router.get("/kpis", response_model=KPIStats)
async def get_dashboard_kpis(
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard KPI statistics from real indicator data (cached 5 min)"""
    cache_key = "dashboard:kpis"
    cached = await _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        result = await _compute_kpis(db)
        await _set_cached(cache_key, result)
        return result
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
    """Get dashboard overview data from real indicators (cached 5 min)"""
    cache_key = "dashboard:overview"
    cached = await _get_cached(cache_key)
    if cached is not None:
        return cached

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

    from api.models.sql.agricultural import StagingWeather
    weather_summary = None
    try:
        wq = await db.execute(
            select(StagingWeather).order_by(StagingWeather.date.desc()).limit(1)
        )
        wr = wq.scalar_one_or_none()
        if wr:
            weather_summary = {
                "average_temperature": wr.temperature,
                "rainfall_mm": wr.precipitation,
                "drought_risk": "unknown",
                "city": wr.city,
                "country": wr.country,
            }
    except Exception:
        pass

    result = {
        "kpis": {
            "total_production": kpis["total_production"],
            "price_index": kpis["price_index"],
            "weather_alerts": kpis["weather_alerts"],
            "countries_monitored": kpis["countries_monitored"],
            "active_farmers": kpis.get("active_farmers"),
            "hectares": kpis.get("hectares"),
            "is_estimated": kpis.get("is_estimated", True),
        },
        "recent_alerts": recent_alerts,
        "top_crops": top_crops[:6],
        "weather_summary": weather_summary,
    }
    await _set_cached("dashboard:overview", result)
    return result


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
            from api.models.sql.agricultural import Country
            country_rows = await db.execute(
                select(Country.name, Country.latitude, Country.longitude)
                .where(Country.latitude != None, Country.longitude != None)
            )
            coordinates = {
                r.name: [r.longitude, r.latitude]
                for r in country_rows.all()
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
    df = pd.DataFrame(data)
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
    body {{ font-family: 'DejaVu Sans', sans-serif; font-size: 12px; }}
    h1 {{ color: #2563eb; font-size: 20px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ background: #2563eb; color: white; padding: 8px 12px; text-align: left; }}
    td {{ padding: 6px 12px; border-bottom: 1px solid #e5e7eb; }}
    tr:nth-child(even) {{ background: #f9fafb; }}
    .footer {{ margin-top: 24px; font-size: 10px; color: #6b7280; text-align: center; }}
</style></head>
<body>
<h1>AgriIntel360 — Export des données</h1>
<p>Généré le {datetime.now(timezone.utc).strftime('%d/%m/%Y à %H:%M UTC')}</p>
{table_html}
<div class="footer">Document généré par AgriIntel360 — Plateforme Intelligente de Décision Agricole</div>
</body></html>"""

    if data:
        df_html = df.to_html(classes="data-table", index=False, border=0)
        table_html = df_html.replace('\n', '')
        html = html.replace('{table_html}', table_html)
    else:
        html = html.replace('{table_html}', '<p>Aucune donnée disponible.</p>')

    try:
        from weasyprint import HTML as WeasyprintHTML
        pdf_bytes = WeasyprintHTML(string=html).write_pdf()
        return io.BytesIO(pdf_bytes)
    except ImportError:
        try:
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", uni=True)
            pdf.set_font("DejaVu", "", 16)
            pdf.cell(200, 10, "AgriIntel360 - Export", ln=True, align="C")
            pdf.set_font("DejaVu", "", 10)
            for _, row in df.head(50).iterrows():
                text = " | ".join(str(v)[:60] for v in row)
                pdf.cell(200, 8, text, ln=True)
            return io.BytesIO(pdf.output(dest="S").encode("latin-1"))
        except ImportError:
            raise RuntimeError(
                "PDF export requires weasyprint or fpdf. "
                "Install with: pip install weasyprint"
            )


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
