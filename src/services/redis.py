"""
Redis services for caching and blacklisting
"""

import redis.asyncio as redis
from datetime import timedelta

from config.config import get_settings

settings = get_settings()

# Redis connection pool
redis_pool = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)


async def add_token_to_blacklist(token: str, expires_delta: timedelta):
    """Add a token to the blacklist with an expiration time."""
    # The key will be the token itself, and the value can be anything (e.g., 1)
    # The expiration will be set to the same as the token's expiration
    await redis_pool.setex(f"blacklist:{token}", expires_delta, 1)


async def is_token_blacklisted(token: str) -> bool:
    """Check if a token is in the blacklist."""
    return await redis_pool.exists(f"blacklist:{token}")
