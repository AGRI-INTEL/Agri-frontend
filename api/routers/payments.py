"""
Payments & Subscriptions API endpoints
"""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import get_db
from src.services.auth import get_current_active_user
from src.services.payments import payments_service
from api.models.sql.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/plans")
async def get_subscription_plans(
    db: AsyncSession = Depends(get_db),
):
    """List available subscription plans with pricing"""
    try:
        await payments_service.seed_plans(db)
        plans = await payments_service.get_plans(db)
        return {"plans": plans, "count": len(plans)}
    except Exception as e:
        logger.error("Error fetching plans: %s", e)
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération des plans")


@router.post("/subscribe")
async def subscribe(
    body: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Subscribe to a plan (creates pending payment)"""
    plan_slug = body.get("plan", "").lower().strip()
    billing_cycle = body.get("billing_cycle", "monthly").lower().strip()

    if not plan_slug:
        raise HTTPException(status_code=400, detail="Plan requis")

    try:
        result = await payments_service.subscribe(current_user.id, plan_slug, billing_cycle, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Subscription error: %s", e)
        raise HTTPException(status_code=500, detail="Erreur lors de la souscription")


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None),
):
    """Flutterwave/Paystack webhook handler"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON invalide")

    result = await payments_service.handle_webhook(payload, x_signature)
    return result


@router.get("/history")
async def get_billing_history(
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """User billing history"""
    try:
        history = await payments_service.get_billing_history(current_user.id, db, limit)
        return {"invoices": history, "count": len(history)}
    except Exception as e:
        logger.error("Billing history error: %s", e)
        return {"invoices": [], "count": 0}


@router.get("/current")
async def get_current_subscription(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Current subscription details"""
    try:
        sub = await payments_service.get_current_subscription(current_user.id, db)
        if not sub:
            return {
                "has_subscription": False,
                "plan": "free",
                "message": "Vous êtes sur le plan Gratuit",
            }
        return {"has_subscription": True, **sub}
    except Exception as e:
        logger.error("Current subscription error: %s", e)
        return {"has_subscription": False, "plan": "free"}


@router.put("/cancel")
async def cancel_subscription(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel subscription"""
    try:
        result = await payments_service.cancel_subscription(current_user.id, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Cancel subscription error: %s", e)
        raise HTTPException(status_code=500, detail="Erreur lors de l'annulation")
