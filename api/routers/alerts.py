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