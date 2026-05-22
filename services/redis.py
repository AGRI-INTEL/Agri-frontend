from datetime import timedelta
from typing import Any, Optional, Union

import redis.asyncio as redis
from fastapi import HTTPException, status

from config.config import settings

class RedisClient:
    def __init__(self):
        self.redis_url = settings.redis_url
        self.pool = None
        self.client = None

    async def connect(self):
        if not self.pool:
            self.pool = redis.ConnectionPool.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=10
            )
            self.client = redis.Redis(connection_pool=self.pool)

    async def disconnect(self):
        if self.pool:
            await self.pool.disconnect()
            self.pool = None
            self.client = None

    async def get(self, key: str) -> Optional[str]:
        if not self.client:
            await self.connect()
        return await self.client.get(key)

    async def set(
        self,
        key: str,
        value: Union[str, bytes, int, float],
        expire: Optional[int] = None
    ) -> bool:
        if not self.client:
            await self.connect()
        return await self.client.set(key, value, ex=expire)

    async def delete(self, key: str) -> int:
        if not self.client:
            await self.connect()
        return await self.client.delete(key)

    async def increment(self, key: str) -> int:
        if not self.client:
            await self.connect()
        return await self.client.incr(key)

    async def exists(self, key: str) -> bool:
        if not self.client:
            await self.connect()
        return await self.client.exists(key) > 0

class RateLimiter:
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
        self.rate_limit = settings.rate_limit_per_minute
        self.window = 60  # 1 minute window

    async def is_rate_limited(self, key: str) -> bool:
        current = await self.redis.increment(key)
        if current == 1:
            await self.redis.set(key, current, expire=self.window)
        
        if current > self.rate_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded"
            )
        return False

class Cache:
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client

    async def get_or_set(
        self,
        key: str,
        func: callable,
        expire: timedelta = timedelta(minutes=5)
    ) -> Any:
        cached = await self.redis.get(key)
        if cached:
            return cached

        value = await func()
        await self.redis.set(key, value, expire=int(expire.total_seconds()))
        return value

    async def invalidate(self, key: str) -> None:
        await self.redis.delete(key)

redis_client = RedisClient()
rate_limiter = RateLimiter(redis_client)
cache = Cache(redis_client)