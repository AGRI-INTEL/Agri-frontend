"""
Payments & Subscriptions service
"""

import uuid
import logging
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from config.config import get_settings
from api.models.sql.base import Base
from api.models.sql.user import User
from sqlalchemy import Column, String, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func as sa_func

settings = get_settings()
logger = logging.getLogger(__name__)


# ── SQLAlchemy Models ─────────────────────────────────────────────────────


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    slug = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    price_monthly = Column(Float, nullable=False)
    price_yearly = Column(Float, nullable=True)
    currency = Column(String(3), default="XOF", nullable=False)
    features = Column(JSONB, nullable=True)
    limits = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Column.Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=sa_func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=sa_func.now(), onupdate=sa_func.now(), nullable=False)


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    billing_cycle = Column(String(10), default="monthly", nullable=False)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    trial_end = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    payment_method = Column(String(50), nullable=True)
    auto_renew = Column(Boolean, default=True, nullable=False)
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=sa_func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=sa_func.now(), onupdate=sa_func.now(), nullable=False)

    user = relationship("User")
    plan = relationship("SubscriptionPlan")


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("user_subscriptions.id"), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="XOF", nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    payment_method = Column(String(50), nullable=True)
    payment_reference = Column(String(255), nullable=True)
    invoice_url = Column(String(500), nullable=True)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=sa_func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=sa_func.now(), onupdate=sa_func.now(), nullable=False)

    user = relationship("User")
    subscription = relationship("UserSubscription")


# ── Default Plans ─────────────────────────────────────────────────────────


DEFAULT_PLANS = [
    {
        "name": "Gratuit",
        "slug": "free",
        "description": "Accès de base aux fonctionnalités de la plateforme",
        "price_monthly": 0,
        "price_yearly": 0,
        "currency": "XOF",
        "features": {
            "indicators": True,
            "weather": True,
            "alerts": True,
            "community": True,
            "chatbot_messages": 20,
            "reports": False,
            "predictions": False,
            "api_access": False,
        },
        "limits": {
            "projects": 1,
            "team_members": 1,
            "storage_mb": 50,
        },
        "sort_order": 0,
    },
    {
        "name": "Pro",
        "slug": "pro",
        "description": "Pour les agriculteurs et professionnels du secteur",
        "price_monthly": 15000,
        "price_yearly": 150000,
        "currency": "XOF",
        "features": {
            "indicators": True,
            "weather": True,
            "alerts": True,
            "community": True,
            "chatbot_messages": 500,
            "reports": True,
            "predictions": True,
            "api_access": True,
        },
        "limits": {
            "projects": 10,
            "team_members": 5,
            "storage_mb": 500,
        },
        "sort_order": 1,
    },
    {
        "name": "Enterprise",
        "slug": "enterprise",
        "description": "Pour les organisations, coopératives et institutions",
        "price_monthly": 50000,
        "price_yearly": 500000,
        "currency": "XOF",
        "features": {
            "indicators": True,
            "weather": True,
            "alerts": True,
            "community": True,
            "chatbot_messages": 999999,
            "reports": True,
            "predictions": True,
            "api_access": True,
        },
        "limits": {
            "projects": 999,
            "team_members": 50,
            "storage_mb": 5000,
        },
        "sort_order": 2,
    },
]


# ── Service ────────────────────────────────────────────────────────────────


class PaymentsService:

    async def seed_plans(self, db: AsyncSession) -> None:
        """Ensure default subscription plans exist in the database"""
        for plan_data in DEFAULT_PLANS:
            existing = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.slug == plan_data["slug"]))
            if not existing.scalar_one_or_none():
                plan = SubscriptionPlan(**plan_data)
                db.add(plan)
        await db.commit()

    async def get_plans(self, db: AsyncSession) -> list[dict]:
        """List available subscription plans with pricing"""
        result = await db.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.sort_order)
        )
        plans = result.scalars().all()
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "slug": p.slug,
                "description": p.description,
                "price_monthly": p.price_monthly,
                "price_yearly": p.price_yearly,
                "currency": p.currency,
                "features": p.features or {},
                "limits": p.limits or {},
            }
            for p in plans
        ]

    async def get_current_subscription(self, user_id: uuid.UUID, db: AsyncSession) -> Optional[dict]:
        """Get the current active subscription for a user"""
        result = await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_(["active", "trialing", "past_due"]),
            )
            .order_by(desc(UserSubscription.created_at))
            .limit(1)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            return None

        plan = await db.get(SubscriptionPlan, sub.plan_id)
        return {
            "id": str(sub.id),
            "plan_id": str(sub.plan_id),
            "plan_name": plan.name if plan else "Inconnu",
            "plan_slug": plan.slug if plan else "unknown",
            "status": sub.status,
            "billing_cycle": sub.billing_cycle,
            "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
            "auto_renew": sub.auto_renew,
            "features": plan.features if plan else {},
            "limits": plan.limits if plan else {},
        }

    async def subscribe(
        self, user_id: uuid.UUID, plan_slug: str, billing_cycle: str, db: AsyncSession
    ) -> dict:
        """Subscribe to a plan — creates a pending subscription"""
        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.slug == plan_slug, SubscriptionPlan.is_active == True)
        )
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise ValueError("Plan non trouvé ou inactif")

        if billing_cycle not in ("monthly", "yearly"):
            raise ValueError("Cycle de facturation invalide. Choisissez monthly ou yearly")

        price = plan.price_yearly if billing_cycle == "yearly" else plan.price_monthly

        now = datetime.now(timezone.utc)
        from datetime import timedelta
        period_end = now + timedelta(days=365 if billing_cycle == "yearly" else 30)

        sub = UserSubscription(
            user_id=user_id,
            plan_id=plan.id,
            status="pending",
            billing_cycle=billing_cycle,
            current_period_start=now,
            current_period_end=period_end,
            metadata={"price_at_subscription": price},
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)

        invoice = Invoice(
            user_id=user_id,
            subscription_id=sub.id,
            amount=price,
            currency=plan.currency,
            status="pending",
            period_start=now,
            period_end=period_end,
        )
        db.add(invoice)
        await db.commit()
        await db.refresh(invoice)

        return {
            "subscription_id": str(sub.id),
            "invoice_id": str(invoice.id),
            "plan": plan.slug,
            "plan_name": plan.name,
            "amount": price,
            "currency": plan.currency,
            "status": "pending",
            "message": "Abonnement créé. En attente de paiement.",
        }

    async def handle_webhook(self, payload: dict, signature: Optional[str]) -> dict:
        """Handle Flutterwave/Paystack webhook with signature verification stub"""
        event = payload.get("event", payload.get("event_type", "unknown"))
        data = payload.get("data", {})

        tx_ref = data.get("tx_ref", data.get("reference", ""))
        status = data.get("status", "completed")

        logger.info("Webhook reçu: event=%s, ref=%s, status=%s", event, tx_ref, status)

        if signature:
            secret = settings.JWT_SECRET_KEY
            expected = hmac.new(
                secret.encode(), str(payload).encode(), hashlib.sha256
            ).hexdigest()
            if signature != expected:
                logger.warning("Signature webhook invalide")
                return {"status": "error", "message": "Signature invalide"}

        return {
            "status": "success",
            "event": event,
            "reference": tx_ref,
            "message": "Webhook traité avec succès",
        }

    async def get_billing_history(self, user_id: uuid.UUID, db: AsyncSession, limit: int = 20) -> list[dict]:
        """Get billing history for a user"""
        result = await db.execute(
            select(Invoice)
            .where(Invoice.user_id == user_id)
            .order_by(desc(Invoice.created_at))
            .limit(limit)
        )
        invoices = result.scalars().all()
        return [
            {
                "id": str(inv.id),
                "subscription_id": str(inv.subscription_id) if inv.subscription_id else None,
                "amount": inv.amount,
                "currency": inv.currency,
                "status": inv.status,
                "payment_method": inv.payment_method,
                "payment_reference": inv.payment_reference,
                "period_start": inv.period_start.isoformat() if inv.period_start else None,
                "period_end": inv.period_end.isoformat() if inv.period_end else None,
                "paid_at": inv.paid_at.isoformat() if inv.paid_at else None,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
            }
            for inv in invoices
        ]

    async def cancel_subscription(self, user_id: uuid.UUID, db: AsyncSession) -> dict:
        """Cancel a user's active subscription"""
        result = await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_(["active", "trialing", "past_due"]),
            )
            .order_by(desc(UserSubscription.created_at))
            .limit(1)
        )
        sub = result.scalar_one_or_none()
        if not sub:
            raise ValueError("Aucun abonnement actif trouvé")

        sub.status = "cancelled"
        sub.cancelled_at = datetime.now(timezone.utc)
        sub.auto_renew = False
        await db.commit()

        return {"message": "Abonnement annulé avec succès", "subscription_id": str(sub.id)}


payments_service = PaymentsService()
