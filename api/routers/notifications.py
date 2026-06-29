"""Notifications API endpoints"""

import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from config.database import get_db
from src.services.auth import get_current_active_user
from api.models.sql.user import User
from api.models.sql.agricultural import Alert

router = APIRouter()


class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    alert_type: str
    severity: str
    is_read: bool
    action_url: Optional[str] = None
    type: str = "alert"
    priority: str = "normal"
    created_at: datetime

    class Config:
        from_attributes = True


def _alert_to_response(a: Alert) -> NotificationResponse:
    priority_map = {"info": "low", "warning": "normal", "critical": "high", "emergency": "urgent"}
    return NotificationResponse(
        id=str(a.id),
        title=a.title,
        message=a.message,
        alert_type=a.alert_type,
        severity=a.severity,
        is_read=a.is_read,
        action_url=a.action_url,
        type="alert",
        priority=priority_map.get(a.severity, "normal"),
        created_at=a.created_at,
    )


@router.get("", response_model=List[NotificationResponse])
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Récupère les notifications de l'utilisateur connecté"""
    query = (
        select(Alert)
        .where(Alert.user_id == current_user.id)
        .order_by(Alert.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        query = query.where(Alert.is_read == False)

    try:
        result = await db.execute(query)
        alerts = result.scalars().all()
        return [_alert_to_response(a) for a in alerts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unread-count")
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Nombre de notifications non lues"""
    from sqlalchemy import func
    try:
        result = await db.execute(
            select(func.count())
            .select_from(Alert)
            .where(Alert.user_id == current_user.id, Alert.is_read == False)
        )
        count = result.scalar_one()
        return {"unread_count": count}
    except Exception:
        return {"unread_count": 0}


@router.put("/{notification_id}/read")
@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Marque une notification comme lue (accepte PUT et PATCH)"""
    try:
        result = await db.execute(
            select(Alert).where(
                Alert.id == notification_id,
                Alert.user_id == current_user.id,
            )
        )
        alert = result.scalar_one_or_none()
        if not alert:
            raise HTTPException(status_code=404, detail="Notification non trouvée")
        alert.is_read = True
        await db.commit()
        return {"message": "Notification marquée comme lue"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mark-all-read")
async def mark_all_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Marque toutes les notifications comme lues"""
    try:
        await db.execute(
            update(Alert)
            .where(Alert.user_id == current_user.id, Alert.is_read == False)
            .values(is_read=True)
        )
        await db.commit()
        return {"message": "Toutes les notifications marquées comme lues"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Supprime une notification"""
    try:
        result = await db.execute(
            select(Alert).where(
                Alert.id == notification_id,
                Alert.user_id == current_user.id,
            )
        )
        alert = result.scalar_one_or_none()
        if not alert:
            raise HTTPException(status_code=404, detail="Notification non trouvée")
        await db.delete(alert)
        await db.commit()
        return {"message": "Notification supprimée"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preferences")
async def get_notification_preferences(
    current_user: User = Depends(get_current_active_user),
):
    """Récupère les préférences de notification de l'utilisateur"""
    prefs = current_user.notification_prefs or {
        "channels": {"push": True, "email": True, "sms": False, "in_app": True},
        "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
    }
    return prefs


@router.put("/preferences")
async def update_notification_preferences(
    prefs: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Met à jour les préférences de notification de l'utilisateur"""
    try:
        current_user.notification_prefs = prefs
        await db.commit()
        return {"message": "Préférences mises à jour"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
