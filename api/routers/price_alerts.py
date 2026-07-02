"""
Price Alerts API endpoints
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db
from src.services.auth import get_current_active_user
from src.services.price_alerts import price_alert_service
from api.models.sql.user import User
from api.models.sql.price_alert import PriceAlert
from api.schemas.price_alert import (
    PriceAlertCreate,
    PriceAlertUpdate,
    PriceAlertResponse,
    PriceAlertCheckResult,
)

router = APIRouter()


@router.get("", response_model=list[PriceAlertResponse])
async def list_price_alerts(
    status: Optional[str] = Query(None, description="Filter: active, inactive, triggered"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await price_alert_service.get_alerts(db, current_user.id, status=status)


@router.post("", response_model=PriceAlertResponse, status_code=status.HTTP_201_CREATED)
async def create_price_alert(
    data: PriceAlertCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await price_alert_service.create_alert(db, current_user.id, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{alert_id}", response_model=PriceAlertResponse)
async def get_price_alert(
    alert_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await _get_user_alert(db, alert_id, current_user.id)
    return alert


@router.put("/{alert_id}", response_model=PriceAlertResponse)
async def update_price_alert(
    alert_id: str,
    data: PriceAlertUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await _get_user_alert(db, alert_id, current_user.id)
    try:
        return await price_alert_service.update_alert(db, alert, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_price_alert(
    alert_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await _get_user_alert(db, alert_id, current_user.id)
    await price_alert_service.delete_alert(db, alert)


@router.post("/{alert_id}/check", response_model=PriceAlertCheckResult)
async def check_price_alert(
    alert_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await _get_user_alert(db, alert_id, current_user.id)
    return await price_alert_service.check_alert_condition(db, alert)


async def _get_user_alert(db: AsyncSession, alert_id: str, user_id: uuid.UUID) -> PriceAlert:
    try:
        uid = uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alerte de prix non trouvée")
    alert = await price_alert_service.get_alert(db, uid)
    if not alert or alert.user_id != user_id:
        raise HTTPException(status_code=404, detail="Alerte de prix non trouvée")
    return alert
