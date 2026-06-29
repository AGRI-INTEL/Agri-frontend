"""
Background task to periodically sync external indicator data
"""
import asyncio
import logging
from datetime import datetime, timezone

from config.database import async_session_maker
from src.services.indicators_fetch import fetch_all_external_indicators

logger = logging.getLogger(__name__)

SYNC_INTERVAL_HOURS = 6


async def sync_external_indicators_periodically():
    """Run periodic sync of World Bank data every SYNC_INTERVAL_HOURS"""
    while True:
        try:
            logger.info("Starting periodic external indicator sync...")
            async with async_session_maker() as db:
                result = await fetch_all_external_indicators(db=db)
                saved = result.get("saved", 0)
                total = result.get("count", 0)
                logger.info(f"Sync complete: {total} fetched, {saved} saved")

                # Update last sync timestamp
                from sqlalchemy import text
                try:
                    await db.execute(
                        text("""
                            INSERT INTO sync_metadata (key, value, updated_at)
                            VALUES ('last_indicator_sync', :ts, NOW())
                            ON CONFLICT (key) DO UPDATE SET value = :ts2, updated_at = NOW()
                        """),
                        {"ts": datetime.now(timezone.utc).isoformat(), "ts2": datetime.now(timezone.utc).isoformat()}
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
        except asyncio.CancelledError:
            logger.info("Periodic sync task cancelled — stopping")
            break
        except Exception as e:
            logger.error(f"Periodic sync failed: {e}")

        try:
            await asyncio.sleep(SYNC_INTERVAL_HOURS * 3600)
        except asyncio.CancelledError:
            logger.info("Periodic sync task cancelled during sleep — stopping")
            break


async def start_background_tasks(app):
    """Start background tasks on application startup"""
    try:
        task = asyncio.create_task(sync_external_indicators_periodically())
        app.state.sync_task = task
        logger.info("Background indicator sync task started")
    except Exception as e:
        logger.error(f"Failed to start background sync task: {e}")


async def stop_background_tasks(app):
    """Stop background tasks on application shutdown"""
    task = getattr(app.state, "sync_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Background indicator sync task stopped")
