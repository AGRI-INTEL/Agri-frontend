"""
Redis services for caching and blacklisting
"""

import logging
from datetime import timedelta

from config.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis_pool = None


async def get_redis():
    global _redis_pool
    if _redis_pool is None:
        if not settings.REDIS_URL:
            return None
        try:
            import redis.asyncio as redis
            _redis_pool = redis.from_url(
                settings.REDIS_URL, encoding="utf-8", decode_responses=True
            )
            # Verify connection works
            await _redis_pool.ping()
        except Exception as e:
            logger.warning("Redis unavailable (%s) — token blacklisting disabled", e)
            _redis_pool = None
            return None
    return _redis_pool


async def add_token_to_blacklist(token: str, expires_delta: timedelta):
    try:
        pool = await get_redis()
        if pool is None:
            return
        await pool.setex(f"blacklist:{token}", expires_delta, 1)
    except Exception as e:
        logger.warning("Redis add_blacklist failed: %s", e)


async def is_token_blacklisted(token: str) -> bool:
    try:
        pool = await get_redis()
        if pool is None:
            return False
        return bool(await pool.exists(f"blacklist:{token}"))
    except Exception as e:
        logger.warning("Redis is_blacklisted failed: %s", e)
        return False


async def mark_totp_code_used(user_id: str, code: str, ttl_seconds: int = 90) -> bool:
    """Store a TOTP code as used. Returns True if the code is new (not yet used)."""
    try:
        pool = await get_redis()
        if pool is None:
            return True  # No Redis — allow code (degraded mode)
        key = f"totp_used:{user_id}:{code}"
        result = await pool.set(key, 1, ex=ttl_seconds, nx=True)
        return result is not None  # True = newly set (first use), None = already existed
    except Exception as e:
        logger.warning("Redis mark_totp_code_used failed: %s", e)
        return True  # Allow code on Redis failure
