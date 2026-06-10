"""
Redis services for caching and blacklisting
"""

from datetime import timedelta
from typing import Optional

from config.config import get_settings

settings = get_settings()

_redis_pool = None


async def get_redis():
    global _redis_pool
    if _redis_pool is None:
        if not settings.REDIS_URL:
            return None
        import redis.asyncio as redis
        _redis_pool = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    return _redis_pool


async def add_token_to_blacklist(token: str, expires_delta: timedelta):
    pool = await get_redis()
    if pool is None:
        return
    await pool.setex(f"blacklist:{token}", expires_delta, 1)


async def is_token_blacklisted(token: str) -> bool:
    pool = await get_redis()
    if pool is None:
        return False
    return await pool.exists(f"blacklist:{token}")
