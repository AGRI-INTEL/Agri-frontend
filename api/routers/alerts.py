"""Alerts and Notifications API endpoints"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from config.database import get_db
from src.services.auth import get_current_active_user
from api.models.sql.user import User
from api.models.sql.agricultural import Alert
from api.schemas.alert import AlertCreate, AlertResponse

router = APIRouter()


# ── LITERAL routes FIRST — must come before /{alert_id} ─────────────────────

@router.get("", response_model=list[AlertResponse])
async def get_alerts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        result = await db.execute(
            select(Alert)
            .where((Alert.user_id == current_user.id) | (Alert.user_id.is_(None)))
            .order_by(Alert.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()
    except Exception:
        return []


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    alert_data: AlertCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    alert = Alert(**alert_data.model_dump(), user_id=current_user.id)
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.get("/stats")
async def get_alert_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        total_q = await db.execute(select(func.count(Alert.id)))
        total = total_q.scalar() or 0

        unread_q = await db.execute(
            select(func.count(Alert.id)).where(Alert.is_read == False)
        )
        unread = unread_q.scalar() or 0

        try:
            severity_rows = await db.execute(
                select(Alert.severity, func.count(Alert.id)).group_by(Alert.severity)
            )
            by_severity = {row[0]: row[1] for row in severity_rows.all() if row[0]}
        except Exception:
            by_severity = {}

        try:
            type_rows = await db.execute(
                select(Alert.alert_type, func.count(Alert.id)).group_by(Alert.alert_type)
            )
            by_type = {row[0]: row[1] for row in type_rows.all() if row[0]}
        except Exception:
            by_type = {}

        try:
            critical_q = await db.execute(
                select(func.count(Alert.id)).where(
                    Alert.severity.in_(["critical", "emergency"])
                )
            )
            critical_count = critical_q.scalar() or 0
        except Exception:
            critical_count = 0

        return {
            "total": total,
            "unread": unread,
            "by_severity": by_severity,
            "by_type": by_type,
            "critical_count": critical_count,
            "resolved": max(0, total - unread),
        }
    except Exception:
        return {"total": 0, "unread": 0, "by_severity": {}, "by_type": {}, "critical_count": 0, "resolved": 0}


@router.post("/read-all")
async def mark_all_alerts_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await db.execute(
            update(Alert).where(Alert.user_id == current_user.id).values(is_read=True)
        )
        await db.commit()
    except Exception:
        pass
    return {"message": "Toutes les alertes ont été marquées comme lues"}


# ── PARAMETERIZED routes LAST ─────────────────────────────────────────────────

@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    try:
        uid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    result = await db.execute(select(Alert).where(Alert.id == uid))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return alert


@router.patch("/{alert_id}/read", response_model=AlertResponse)
async def mark_alert_read(
    alert_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    try:
        uid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    result = await db.execute(select(Alert).where(Alert.id == uid))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    alert.is_read = True
    await db.commit()
    await db.refresh(alert)
    return alert


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    try:
        uid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    result = await db.execute(select(Alert).where(Alert.id == uid))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    try:
        alert.status = "acknowledged"
        if hasattr(alert, 'comment'):
            alert.comment = data.get("comment")
        await db.commit()
    except Exception:
        pass
    return {"message": "Alerte reconnue"}


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    try:
        uid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    result = await db.execute(select(Alert).where(Alert.id == uid))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    try:
        alert.status = "resolved"
        if hasattr(alert, 'resolution'):
            alert.resolution = data.get("resolution")
        await db.commit()
    except Exception:
        pass
    return {"message": "Alerte résolue"}
