"""
Dashboard API endpoints
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from api.models.sql.agricultural import StagingProduction

router = APIRouter()


@router.get("/overview")
async def get_dashboard_overview(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard overview data"""
    return {
        "kpis": {
            "total_production": 1250000,
            "price_index": 125.5,
            "weather_alerts": 3,
            "countries_monitored": 15
        },
        "recent_alerts": [],
        "top_crops": [
            {"name": "Maïs", "production": 450000, "change": 5.2},
            {"name": "Riz", "production": 320000, "change": -2.1},
            {"name": "Manioc", "production": 280000, "change": 8.7}
        ],
        "weather_summary": {
            "average_temperature": 28.5,
            "rainfall_mm": 45.2,
            "drought_risk": "medium"
        }
    }


@router.get("/charts/production")
async def get_production_chart_data(
    country: str = None,
    crop: str = None,
    year: int = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Get production chart data from staging table with fallback"""
    query = (
        select(
            StagingProduction.country_name.label("country"),
            StagingProduction.crop_name.label("crop"),
            StagingProduction.value.label("production"),
            StagingProduction.year,
        )
    )

    if country:
        query = query.where(StagingProduction.country_name == country)
    if crop:
        query = query.where(StagingProduction.crop_name == crop)
    if year:
        query = query.where(StagingProduction.year == year)

    try:
        result = await db.execute(query)
        rows = result.mappings().all()
        if rows:
            data = [dict(r) for r in rows]
            return {"data": data, "total": len(data)}
    except Exception:
        pass

    # Fallback mock
    return {
        "data": [
            {"country": "Nigeria", "crop": "Maïs", "production": 12000000, "year": 2023},
            {"country": "Ghana", "crop": "Cacao", "production": 800000, "year": 2023},
            {"country": "Togo", "crop": "Coton", "production": 150000, "year": 2023}
        ],
        "total": 3
    }


@router.get("/charts/prices")
async def get_price_chart_data(
    country: str = None,
    crop: str = None,
    period: str = "1M",
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Get price trend chart data"""
    return {
        "data": [
            {"date": "2024-01-01", "price": 450, "crop": "Maïs"},
            {"date": "2024-02-01", "price": 475, "crop": "Maïs"},
            {"date": "2024-03-01", "price": 460, "crop": "Maïs"}
        ],
        "total": 3
    }


@router.get("/maps/production")
async def get_production_map_data(
    crop: str = None,
    year: int = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Get production data for map visualization"""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "country": "Nigeria",
                    "production": 12000000,
                    "crop": "Maïs",
                    "density": 2500
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [8.6753, 9.0820]
                }
            }
        ]
    }


import pandas as pd
import io
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from api.models.sql.agricultural import Production, Country, Crop


async def get_production_data(db: AsyncSession):
    query = (
        select(
            Production.year,
            Production.production_tonnes,
            Production.yield_tonnes_per_ha,
            Country.name.label("country_name"),
            Crop.name.label("crop_name")
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
    with pd.ExcelWriter(stream, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Dashboard Data')
    stream.seek(0)
    return stream

async def export_to_pdf(data):
    # TODO: Implement PDF export using a library like reportlab
    raise NotImplementedError("PDF export is not yet implemented.")

EXPORT_FORMATS = {
    "csv": {"exporter": export_to_csv, "content_type": "text/csv"},
    "excel": {"exporter": export_to_excel, "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "pdf": {"exporter": export_to_pdf, "content_type": "application/pdf"}
}

@router.get("/export/{format}")
async def export_dashboard_data(
    format: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db)
):
    """Export dashboard data in various formats"""
    if format not in EXPORT_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}. Supported formats are: {list(EXPORT_FORMATS.keys())}"
        )

    data = await get_production_data(db)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No data available to export."
        )

    try:
        exporter = EXPORT_FORMATS[format]["exporter"]
        content_type = EXPORT_FORMATS[format]["content_type"]
        
        file_stream = await exporter(data)
        
        return StreamingResponse(
            iter([file_stream.getvalue()]),
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename=dashboard_export.{format}"}
        )

    except NotImplementedError as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to export data: {e}")


@router.get("/charts/weather")
async def get_weather_chart_data(
    country: str = None,
    period: str = "1M",
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Données météo pour graphiques dashboard"""
    from datetime import timedelta
    from api.models.sql.agricultural import StagingWeather
    days = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}.get(period, 30)
    since = datetime.utcnow() - timedelta(days=days)

    try:
        query = select(StagingWeather).where(StagingWeather.date >= since).order_by(StagingWeather.date)
        if country:
            query = query.where(StagingWeather.country.ilike(f"%{country}%"))
        result = await db.execute(query.limit(200))
        rows = result.scalars().all()
        if rows:
            return {
                "data": [
                    {"date": r.date.isoformat(), "temperature": r.temperature,
                     "precipitation": r.precipitation, "humidity": r.humidity,
                     "city": r.city, "country": r.country}
                    for r in rows
                ],
                "period": period,
            }
    except Exception:
        pass

    # Mock
    from datetime import timedelta
    data = []
    for i in range(min(days, 30)):
        d = datetime.utcnow() - timedelta(days=days - i)
        data.append({
            "date": d.strftime("%Y-%m-%d"),
            "temperature": round(26 + (i % 5) * 0.8, 1),
            "precipitation": round(5 + (i % 7) * 4, 1),
            "humidity": round(65 + (i % 4) * 3, 1),
            "city": "Lomé", "country": country or "Togo",
        })
    return {"data": data, "period": period, "source": "demo"}


@router.get("/charts/economics")
async def get_economics_chart_data(
    country: str = None,
    indicator: str = "agricultural_gdp",
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Données économiques pour graphiques dashboard"""
    from api.models.sql.agricultural import StagingEconomic
    try:
        query = (
            select(StagingEconomic)
            .where(StagingEconomic.indicator == indicator)
            .order_by(StagingEconomic.year)
            .limit(100)
        )
        if country:
            query = query.where(StagingEconomic.country_name.ilike(f"%{country}%"))
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            return {
                "data": [
                    {"year": r.year, "value": r.value, "unit": r.unit,
                     "country": r.country_name, "indicator": r.indicator}
                    for r in rows
                ],
                "indicator": indicator,
            }
    except Exception:
        pass

    # Mock
    countries_data = [("Togo", 1.8), ("Ghana", 12.4), ("Nigeria", 98.2)]
    data = []
    for name, base in countries_data:
        if country and country.lower() not in name.lower():
            continue
        for yr in range(2019, 2024):
            data.append({"year": yr, "value": round(base * (1 + (yr - 2019) * 0.03), 2),
                         "unit": "billion USD", "country": name, "indicator": indicator})
    return {"data": data, "indicator": indicator, "source": "demo"}
