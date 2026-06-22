"""
Session management services using Redis (with fallback if Redis unavailable)
"""

import redis.asyncio as redis
import json
from datetime import timedelta, datetime, timezone
from typing import Optional

from config.config import get_settings

settings = get_settings()

class SessionService:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._initialized = False

    async def _ensure_connection(self) -> bool:
        """Lazy initialize Redis connection. Returns True if successful."""
        if self._initialized:
            return self.redis_client is not None
        
        try:
            self.redis_client = await redis.from_url(settings.REDIS_URL, decode_responses=True)
            await self.redis_client.ping()
            self._initialized = True
            return True
        except Exception as e:
            print(f"⚠️  Redis connection failed (session service will degrade): {e}")
            self._initialized = True
            return False

    async def create_session(self, user_id: str, user_agent: str, ip_address: str) -> Optional[str]:
        """Create a session. Returns None if Redis is unavailable."""
        if not await self._ensure_connection():
            return None
        try:
            session_id = f"session:{user_id}:{user_agent}:{ip_address}"
            session_data = {
                "user_id": user_id,
                "user_agent": user_agent,
                "ip_address": ip_address,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await self.redis_client.set(session_id, json.dumps(session_data), ex=timedelta(days=7))
            return session_id
        except Exception as e:
            print(f"⚠️  Failed to create session: {e}")
            return None

    async def get_sessions(self, user_id: str) -> list:
        """Get user sessions. Returns empty list if Redis unavailable."""
        if not await self._ensure_connection():
            return []
        try:
            session_keys = await self.redis_client.keys(f"session:{user_id}:*")
            sessions = []
            for key in session_keys:
                session_data = await self.redis_client.get(key)
                if session_data:
                    sessions.append(json.loads(session_data))
            return sessions
        except Exception as e:
            print(f"⚠️  Failed to get sessions: {e}")
            return []

    async def revoke_session(self, session_id: str) -> bool:
        """Revoke a session. Returns True if successful."""
        if not await self._ensure_connection():
            return False
        try:
            await self.redis_client.delete(session_id)
            return True
        except Exception as e:
            print(f"⚠️  Failed to revoke session: {e}")
            return False

    async def revoke_all_other_sessions(self, user_id: str, current_session_id: Optional[str] = None) -> bool:
        """Revoke all sessions for a user, except for the current session if provided."""
        if not await self._ensure_connection():
            return False
        try:
            session_keys = await self.redis_client.keys(f"session:{user_id}:*")
            keys_to_delete = [key for key in session_keys if key != current_session_id]
            if keys_to_delete:
                await self.redis_client.delete(*keys_to_delete)
            return True
        except Exception as e:
            print(f"⚠️  Failed to revoke other sessions: {e}")
            return False

session_service = SessionService()
