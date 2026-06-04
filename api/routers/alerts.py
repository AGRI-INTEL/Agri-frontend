"""Alerts and Notifications API endpoints"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.database import get_db
from src.services.auth import get_current_active_user
from api.models.sql.user import User
from api.models.sql.agricultural import Alert
from api.schemas.alert import AlertCreate, AlertResponse

router = APIRouter()

@router.get("/", response_model=list[AlertResponse])
async def get_alerts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Get user alerts"""
    result = await db.execute(
        select(Alert)
        .where(Alert.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
    )
    alerts = result.scalars().all()
    return alerts

@router.post("/", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert_data: AlertCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new alert"""
    alert = Alert(**alert_data.model_dump(), user_id=current_user.id)
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.get("/stats")
async def get_alert_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Statistiques des alertes"""
    return {
        "total": 10,
        "unread": 3,
        "by_severity": {"critical": 2, "warning": 5, "info": 3},
        "by_type": {"weather": 4, "market": 3, "system": 3},
        "critical_count": 2
    }


@router.patch("/{alert_id}/read", response_model=AlertResponse)
async def mark_alert_read(
    alert_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Marquer une alerte comme lue"""
    import uuid
    result = await db.execute(select(Alert).where(Alert.id == uuid.UUID(alert_id)))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")

    alert.is_read = True
    await db.commit()
    await db.refresh(alert)
    return alert


@router.post("/read-all")
async def mark_all_alerts_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Marquer toutes les alertes comme lues"""
    from sqlalchemy import update
    await db.execute(
        update(Alert)
        .where(Alert.user_id == current_user.id)
        .values(is_read=True)
    )
    await db.commit()
    return {"message": "Toutes les alertes ont été marquées comme lues"}


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Accuser réception d'une alerte"""
    import uuid
    result = await db.execute(select(Alert).where(Alert.id == uuid.UUID(alert_id)))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")

    alert.status = "acknowledged"
    alert.comment = data.get("comment")
    await db.commit()
    return {"message": "Alerte reconnue"}


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Résoudre une alerte"""
    import uuid
    result = await db.execute(select(Alert).where(Alert.id == uuid.UUID(alert_id)))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")

    alert.status = "resolved"
    alert.resolution = data.get("resolution")
    await db.commit()
    return {"message": "Alerte résolue"}