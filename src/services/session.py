"""
Session management services using Redis
"""

import redis.asyncio as redis
import json
from datetime import timedelta, datetime

from config.config import get_settings

settings = get_settings()

class SessionService:
    def __init__(self):
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def create_session(self, user_id: str, user_agent: str, ip_address: str) -> str:
        session_id = f"session:{user_id}:{user_agent}:{ip_address}"
        session_data = {
            "user_id": user_id,
            "user_agent": user_agent,
            "ip_address": ip_address,
            "created_at": datetime.utcnow().isoformat()
        }
        await self.redis_client.set(session_id, json.dumps(session_data), ex=timedelta(days=7))
        return session_id

    async def get_sessions(self, user_id: str) -> list:
        session_keys = await self.redis_client.keys(f"session:{user_id}:*")
        sessions = []
        for key in session_keys:
            session_data = await self.redis_client.get(key)
            if session_data:
                sessions.append(json.loads(session_data))
        return sessions

    async def revoke_session(self, session_id: str):
        await self.redis_client.delete(session_id)

session_service = SessionService()
