"""
Price Alert business logic service
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.sql.price_alert import PriceAlert, PriceAlertCondition
from api.schemas.price_alert import PriceAlertCreate, PriceAlertUpdate
from src.services.market_data import market_data_service

logger = logging.getLogger(__name__)


class PriceAlertService:

    async def get_alerts(
        self,
        db: AsyncSession,
        user_id: UUID,
        status: Optional[str] = None,
    ) -> list[PriceAlert]:
        query = select(PriceAlert).where(PriceAlert.user_id == user_id)
        if status == "active":
            query = query.where(PriceAlert.is_active == True)
        elif status == "inactive":
            query = query.where(PriceAlert.is_active == False)
        elif status == "triggered":
            query = query.where(PriceAlert.last_triggered_at.isnot(None))
        query = query.order_by(PriceAlert.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_alert(self, db: AsyncSession, alert_id: UUID) -> Optional[PriceAlert]:
        result = await db.execute(select(PriceAlert).where(PriceAlert.id == alert_id))
        return result.scalar_one_or_none()

    async def create_alert(
        self,
        db: AsyncSession,
        user_id: UUID,
        data: PriceAlertCreate,
    ) -> PriceAlert:
        alert = PriceAlert(
            user_id=user_id,
            crop=data.crop.lower().strip(),
            market=data.market.strip(),
            condition=PriceAlertCondition(data.condition),
            threshold=data.threshold,
            currency=data.currency,
        )
        db.add(alert)
        await db.commit()
        await db.refresh(alert)
        return alert

    async def update_alert(
        self,
        db: AsyncSession,
        alert: PriceAlert,
        data: PriceAlertUpdate,
    ) -> PriceAlert:
        update_data = data.model_dump(exclude_none=True)
        if "condition" in update_data:
            update_data["condition"] = PriceAlertCondition(update_data["condition"])
        if "crop" in update_data:
            update_data["crop"] = update_data["crop"].lower().strip()
        if "market" in update_data:
            update_data["market"] = update_data["market"].strip()
        for key, value in update_data.items():
            setattr(alert, key, value)
        await db.commit()
        await db.refresh(alert)
        return alert

    async def delete_alert(self, db: AsyncSession, alert: PriceAlert) -> None:
        await db.delete(alert)
        await db.commit()

    async def check_alert_condition(
        self,
        db: AsyncSession,
        alert: PriceAlert,
    ) -> dict:
        current_price = await self._get_current_price(alert.crop, alert.market)
        if current_price is None:
            return {
                "alert_id": alert.id,
                "crop": alert.crop,
                "market": alert.market,
                "condition": alert.condition.value,
                "threshold": alert.threshold,
                "current_price": None,
                "triggered": False,
                "message": f"Impossible de récupérer le prix actuel pour {alert.crop} à {alert.market}",
            }

        if alert.condition == PriceAlertCondition.ABOVE:
            triggered = current_price > alert.threshold
        else:
            triggered = current_price < alert.threshold

        if triggered:
            alert.last_triggered_at = datetime.now(timezone.utc)
            await db.commit()

        direction = "dépasse" if alert.condition == PriceAlertCondition.ABOVE else "descend en dessous de"
        status = "DÉCLENCHÉE" if triggered else "Non déclenchée"
        message = (
            f"Alerte {alert.crop} à {alert.market} : prix actuel {current_price:.0f} {alert.currency} "
            f"{direction} {alert.threshold:.0f} {alert.currency} — {status}"
        )

        return {
            "alert_id": alert.id,
            "crop": alert.crop,
            "market": alert.market,
            "condition": alert.condition.value,
            "threshold": alert.threshold,
            "current_price": current_price,
            "triggered": triggered,
            "message": message,
        }

    async def check_all_alerts_for_crop(
        self,
        db: AsyncSession,
        crop: str,
        market: Optional[str] = None,
    ) -> list[dict]:
        query = select(PriceAlert).where(
            PriceAlert.is_active == True,
            PriceAlert.crop == crop.lower().strip(),
        )
        if market:
            query = query.where(PriceAlert.market == market.strip())
        result = await db.execute(query)
        alerts = result.scalars().all()

        results = []
        for alert in alerts:
            check = await self.check_alert_condition(db, alert)
            results.append(check)
        return results

    async def _get_current_price(self, crop: str, market: str) -> Optional[float]:
        try:
            prices = await market_data_service.fetch_prices(crop=crop)
            if not prices:
                return None
            market_prices = [
                p["price"]
                for p in prices
                if p.get("price") is not None
                and (market.lower() in (p.get("market") or "").lower())
            ]
            if not market_prices:
                market_prices = [
                    p["price"]
                    for p in prices
                    if p.get("price") is not None
                ]
            if not market_prices:
                return None
            return sum(market_prices) / len(market_prices)
        except Exception as e:
            logger.warning("Failed to fetch current price for %s/%s: %s", crop, market, e)
            return None


price_alert_service = PriceAlertService()
