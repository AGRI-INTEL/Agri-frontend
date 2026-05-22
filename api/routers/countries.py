"""Countries & Crops reference data endpoints"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from api.models.sql.agricultural import Country, Crop

router = APIRouter()


# ── Countries ──────────────────────────────────────────────────────────────────

@router.get("/countries")
async def list_countries(
    search: Optional[str] = Query(None, description="Recherche par nom"),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste tous les pays disponibles"""
    query = select(Country).order_by(Country.name)
    if search:
        query = query.where(Country.name.ilike(f"%{search}%"))

    try:
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            return {
                "countries": [{"id": r.id, "name": r.name, "code": r.code} for r in rows],
                "count": len(rows),
            }
    except Exception:
        pass

    # Mock fallback
    mock_countries = [
        {"id": 1, "name": "Togo", "code": "TG"},
        {"id": 2, "name": "Ghana", "code": "GH"},
        {"id": 3, "name": "Nigeria", "code": "NG"},
        {"id": 4, "name": "Côte d'Ivoire", "code": "CI"},
        {"id": 5, "name": "Burkina Faso", "code": "BF"},
        {"id": 6, "name": "Sénégal", "code": "SN"},
        {"id": 7, "name": "Mali", "code": "ML"},
        {"id": 8, "name": "Bénin", "code": "BJ"},
        {"id": 9, "name": "Niger", "code": "NE"},
        {"id": 10, "name": "Cameroun", "code": "CM"},
    ]
    if search:
        mock_countries = [c for c in mock_countries if search.lower() in c["name"].lower()]
    return {"countries": mock_countries, "count": len(mock_countries), "source": "demo"}


@router.get("/countries/{country_id}")
async def get_country(
    country_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Détails d'un pays"""
    try:
        result = await db.execute(select(Country).where(Country.id == country_id))
        country = result.scalar_one_or_none()
        if country:
            return {"id": country.id, "name": country.name, "code": country.code}
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Pays non trouvé")


# ── Crops ──────────────────────────────────────────────────────────────────────

@router.get("/crops")
async def list_crops(
    search: Optional[str] = Query(None, description="Recherche par nom"),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste toutes les cultures disponibles"""
    query = select(Crop).order_by(Crop.name)
    if search:
        query = query.where(Crop.name.ilike(f"%{search}%"))

    try:
        result = await db.execute(query)
        rows = result.scalars().all()
        if rows:
            return {
                "crops": [{"id": r.id, "name": r.name, "code": r.code} for r in rows],
                "count": len(rows),
            }
    except Exception:
        pass

    # Mock fallback
    mock_crops = [
        {"id": 1, "name": "Maïs", "code": 56},
        {"id": 2, "name": "Riz", "code": 27},
        {"id": 3, "name": "Manioc", "code": 125},
        {"id": 4, "name": "Igname", "code": 137},
        {"id": 5, "name": "Cacao", "code": 661},
        {"id": 6, "name": "Café", "code": 656},
        {"id": 7, "name": "Coton", "code": 328},
        {"id": 8, "name": "Arachide", "code": 242},
        {"id": 9, "name": "Sorgho", "code": 83},
        {"id": 10, "name": "Mil", "code": 79},
        {"id": 11, "name": "Plantain", "code": 489},
        {"id": 12, "name": "Tomate", "code": 388},
    ]
    if search:
        mock_crops = [c for c in mock_crops if search.lower() in c["name"].lower()]
    return {"crops": mock_crops, "count": len(mock_crops), "source": "demo"}


@router.get("/crops/{crop_id}")
async def get_crop(
    crop_id: int,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Détails d'une culture"""
    try:
        result = await db.execute(select(Crop).where(Crop.id == crop_id))
        crop = result.scalar_one_or_none()
        if crop:
            return {"id": crop.id, "name": crop.name, "code": crop.code}
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Culture non trouvée")
