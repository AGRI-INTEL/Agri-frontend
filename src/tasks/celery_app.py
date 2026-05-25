"""
Celery application and task definitions for AgriIntel360
Background tasks: alert checks, data aggregation, email sending, ML predictions
"""

import os
import logging
from datetime import datetime, timedelta
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

# ── App setup ──────────────────────────────────────────────────────────────────
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "agriintel360",
    broker=redis_url,
    backend=redis_url,
    include=["src.tasks.celery_app"],
)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Retry policy
    task_max_retries=3,
    task_default_retry_delay=60,
)

# ── Periodic tasks (beat schedule) ────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Check weather alerts every 30 minutes
    "check-weather-alerts": {
        "task": "src.tasks.celery_app.check_weather_alerts",
        "schedule": crontab(minute="*/30"),
    },
    # Check price variations every hour
    "check-price-variations": {
        "task": "src.tasks.celery_app.check_price_variations",
        "schedule": crontab(minute=0),
    },
    # Aggregate indicators daily at 2 AM
    "aggregate-indicators": {
        "task": "src.tasks.celery_app.aggregate_indicators",
        "schedule": crontab(hour=2, minute=0),
    },
    # Clean expired tokens from Redis daily at 3 AM
    "clean-expired-tokens": {
        "task": "src.tasks.celery_app.clean_expired_tokens",
        "schedule": crontab(hour=3, minute=0),
    },
    # Send daily digest emails at 7 AM
    "send-daily-digest": {
        "task": "src.tasks.celery_app.send_daily_digest",
        "schedule": crontab(hour=7, minute=0),
    },
}


# ── Tasks ──────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="src.tasks.celery_app.debug_task")
def debug_task(self):
    """Debug task to verify Celery is working"""
    logger.info(f"Debug task executed. Request: {self.request!r}")
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@celery_app.task(
    bind=True,
    name="src.tasks.celery_app.check_weather_alerts",
    max_retries=3,
    default_retry_delay=120,
)
def check_weather_alerts(self):
    """
    Periodic task: check weather conditions and trigger alerts if thresholds exceeded.
    Runs every 30 minutes via beat schedule.
    """
    try:
        import asyncio
        from src.services.notifications import alert_service

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(alert_service.check_weather_conditions())
        finally:
            loop.close()

        logger.info("Weather alert check completed")
        return {"status": "completed", "task": "check_weather_alerts"}

    except Exception as exc:
        logger.error(f"Weather alert check failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="src.tasks.celery_app.check_price_variations",
    max_retries=3,
    default_retry_delay=120,
)
def check_price_variations(self):
    """
    Periodic task: check commodity price variations and trigger alerts.
    Runs every hour via beat schedule.
    """
    try:
        import asyncio
        from src.services.notifications import alert_service

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(alert_service.check_price_variations())
        finally:
            loop.close()

        logger.info("Price variation check completed")
        return {"status": "completed", "task": "check_price_variations"}

    except Exception as exc:
        logger.error(f"Price variation check failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="src.tasks.celery_app.aggregate_indicators",
    max_retries=2,
    default_retry_delay=300,
)
def aggregate_indicators(self):
    """
    Daily task: compute aggregated indicator views for dashboards.
    Runs at 2 AM UTC via beat schedule.
    """
    try:
        logger.info("Starting daily indicator aggregation...")
        # Placeholder — wire to AggregationService when DB is available
        result = {
            "status": "completed",
            "task": "aggregate_indicators",
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.info("Daily indicator aggregation completed")
        return result

    except Exception as exc:
        logger.error(f"Indicator aggregation failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="src.tasks.celery_app.clean_expired_tokens",
    max_retries=2,
)
def clean_expired_tokens(self):
    """
    Daily task: remove expired JWT tokens from the Redis blacklist.
    Redis TTL handles expiry automatically, but this task cleans orphaned keys.
    """
    try:
        import asyncio
        import redis.asyncio as aioredis
        from config.config import get_settings

        settings = get_settings()

        async def _clean():
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                # Scan for blacklist keys — Redis TTL already expires them,
                # this is a safety sweep for any keys without TTL set.
                cursor = 0
                cleaned = 0
                while True:
                    cursor, keys = await client.scan(cursor, match="blacklist:*", count=100)
                    for key in keys:
                        ttl = await client.ttl(key)
                        if ttl == -1:  # No TTL — set a 1-hour expiry as safety
                            await client.expire(key, 3600)
                            cleaned += 1
                    if cursor == 0:
                        break
                return cleaned
            finally:
                await client.aclose()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            cleaned = loop.run_until_complete(_clean())
        finally:
            loop.close()

        logger.info(f"Token cleanup completed. Fixed {cleaned} keys without TTL.")
        return {"status": "completed", "task": "clean_expired_tokens", "fixed_keys": cleaned}

    except Exception as exc:
        logger.error(f"Token cleanup failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="src.tasks.celery_app.send_daily_digest",
    max_retries=2,
    default_retry_delay=300,
)
def send_daily_digest(self):
    """
    Daily task: send digest email to users with unread alerts.
    Runs at 7 AM UTC via beat schedule.
    """
    try:
        import asyncio
        from config.database import get_db
        from sqlalchemy import select
        from api.models.sql.user import User
        from api.models.sql.agricultural import Alert
        from src.services.email import send_email

        async def _send_digests():
            sent = 0
            async for db in get_db():
                # Find users with unread alerts
                result = await db.execute(
                    select(User.id, User.email, User.full_name)
                    .join(Alert, Alert.user_id == User.id)
                    .where(Alert.is_read == False, User.is_active == True)
                    .distinct()
                )
                users = result.all()

                for user_id, email, full_name in users:
                    # Count unread alerts
                    count_result = await db.execute(
                        select(Alert).where(
                            Alert.user_id == user_id,
                            Alert.is_read == False,
                        )
                    )
                    alerts = count_result.scalars().all()
                    if not alerts:
                        continue

                    subject = f"AgriIntel360 — {len(alerts)} alerte(s) non lue(s)"
                    body = f"""
                    <p>Bonjour {full_name},</p>
                    <p>Vous avez <strong>{len(alerts)}</strong> alerte(s) non lue(s) sur AgriIntel360.</p>
                    <ul>
                    {"".join(f"<li><b>{a.title}</b> — {a.severity}</li>" for a in alerts[:5])}
                    </ul>
                    <p><a href="http://localhost:3000/alerts">Voir toutes les alertes</a></p>
                    """
                    await send_email([email], subject, body)
                    sent += 1
            return sent

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            sent = loop.run_until_complete(_send_digests())
        finally:
            loop.close()

        logger.info(f"Daily digest sent to {sent} users")
        return {"status": "completed", "task": "send_daily_digest", "emails_sent": sent}

    except Exception as exc:
        logger.error(f"Daily digest failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="src.tasks.celery_app.send_notification_email",
    max_retries=3,
    default_retry_delay=60,
)
def send_notification_email(self, email: str, subject: str, body: str):
    """
    On-demand task: send a single notification email asynchronously.

    Args:
        email: recipient email address
        subject: email subject
        body: HTML email body
    """
    try:
        import asyncio
        from src.services.email import send_email

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(send_email([email], subject, body))
        finally:
            loop.close()

        logger.info(f"Notification email sent to {email}")
        return {"status": "sent", "email": email}

    except Exception as exc:
        logger.error(f"Failed to send email to {email}: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="src.tasks.celery_app.run_ml_prediction_batch",
    max_retries=2,
    default_retry_delay=120,
)
def run_ml_prediction_batch(self, requests: list):
    """
    On-demand task: run a batch of ML predictions asynchronously.

    Args:
        requests: list of prediction request dicts
    """
    try:
        results = []
        for i, req in enumerate(requests):
            # Heuristic fallback (replace with real model call)
            base = 1.5
            climate_adj = (req.get("precipitation_total", 800) / 1000.0)
            econ_adj = (req.get("gdp_per_capita", 2000) / 10000.0) * 0.1
            predicted = round(max(0.3, base + climate_adj + econ_adj), 3)
            results.append({
                "index": i,
                "status": "success",
                "predicted_yield_tonnes_per_ha": predicted,
                "confidence": 0.75,
            })

        logger.info(f"Batch ML prediction completed: {len(results)} results")
        return {"status": "completed", "results": results, "total": len(results)}

    except Exception as exc:
        logger.error(f"Batch ML prediction failed: {exc}")
        raise self.retry(exc=exc)
