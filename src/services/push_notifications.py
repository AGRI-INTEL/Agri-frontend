"""
Firebase Cloud Messaging (FCM) push notification service
"""

import logging
from typing import Optional

from config.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    FIREBASE_AVAILABLE = True
except ImportError:
    firebase_admin = None
    messaging = None
    FIREBASE_AVAILABLE = False

FCM_API_URL = "https://fcm.googleapis.com/fcm/send"


class PushNotificationService:
    def __init__(self):
        self._firebase_app = None
        self._init_firebase()

    def _init_firebase(self):
        if not FIREBASE_AVAILABLE:
            logger.info("firebase-admin not installed — will use REST API fallback")
            return
        if self._firebase_app is not None:
            return
        try:
            if not firebase_admin._apps:
                if settings.FCM_SERVER_KEY:
                    self._firebase_app = firebase_admin.initialize_app()
                else:
                    logger.warning("FCM_SERVER_KEY not set — Firebase SDK not initialized")
            else:
                self._firebase_app = firebase_admin.get_app()
        except Exception as e:
            logger.warning("Firebase SDK init failed: %s — will use REST API fallback", e)

    async def send_push_notification(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
    ) -> bool:
        if FIREBASE_AVAILABLE and self._firebase_app is not None:
            return await self._send_via_sdk(token, title, body, data)
        return await self._send_via_rest(token, title, body, data)

    async def send_bulk_push(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: Optional[dict] = None,
    ) -> list[bool]:
        if not tokens:
            return []

        results = []
        batch_size = 500
        for i in range(0, len(tokens), batch_size):
            batch = tokens[i : i + batch_size]
            if FIREBASE_AVAILABLE and self._firebase_app is not None:
                result = await self._send_bulk_via_sdk(batch, title, body, data)
                results.extend(result)
            else:
                for token in batch:
                    ok = await self._send_via_rest(token, title, body, data)
                    results.append(ok)
        return results

    async def send_topic_notification(
        self, topic: str, title: str, body: str
    ) -> bool:
        if FIREBASE_AVAILABLE and self._firebase_app is not None:
            return await self._send_topic_via_sdk(topic, title, body)
        return await self._send_topic_via_rest(topic, title, body)

    async def _send_via_sdk(
        self, token: str, title: str, body: str, data: Optional[dict] = None
    ) -> bool:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=token,
            )
            response = messaging.send(message)
            logger.info("Push sent via SDK to token=%s... response=%s", token[:16], response)
            return True
        except Exception as e:
            logger.error("Push SDK send failed for token=%s...: %s", token[:16], e)
            return False

    async def _send_bulk_via_sdk(
        self, tokens: list[str], title: str, body: str, data: Optional[dict] = None
    ) -> list[bool]:
        try:
            messages = [
                messaging.Message(
                    notification=messaging.Notification(title=title, body=body),
                    data={k: str(v) for k, v in (data or {}).items()},
                    token=token,
                )
                for token in tokens
            ]
            response = messaging.send_all(messages)
            results = []
            for idx, resp in enumerate(response.responses):
                success = resp.success
                if not success:
                    logger.warning(
                        "Push SDK bulk failed for idx=%s token=%s...: %s",
                        idx,
                        tokens[idx][:16],
                        resp.exception,
                    )
                results.append(success)
            return results
        except Exception as e:
            logger.error("Push SDK bulk send failed: %s", e)
            return [False] * len(tokens)

    async def _send_via_rest(
        self, token: str, title: str, body: str, data: Optional[dict] = None
    ) -> bool:
        if not settings.FCM_SERVER_KEY:
            logger.warning("FCM_SERVER_KEY not set — cannot send push")
            return False
        try:
            import httpx

            payload = {
                "to": token,
                "notification": {"title": title, "body": body},
                "data": {k: str(v) for k, v in (data or {}).items()},
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    FCM_API_URL,
                    headers={
                        "Authorization": f"key={settings.FCM_SERVER_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code == 200:
                    logger.info("Push sent via REST to token=%s...", token[:16])
                    return True
                logger.warning(
                    "Push REST failed for token=%s...: %s %s",
                    token[:16],
                    response.status_code,
                    response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("Push REST send failed for token=%s...: %s", token[:16], e)
            return False

    async def _send_topic_via_sdk(self, topic: str, title: str, body: str) -> bool:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                topic=topic,
            )
            response = messaging.send(message)
            logger.info("Topic push sent via SDK topic=%s response=%s", topic, response)
            return True
        except Exception as e:
            logger.error("Push SDK topic send failed for topic=%s: %s", topic, e)
            return False

    async def _send_topic_via_rest(self, topic: str, title: str, body: str) -> bool:
        if not settings.FCM_SERVER_KEY:
            logger.warning("FCM_SERVER_KEY not set — cannot send topic push")
            return False
        try:
            import httpx

            payload = {
                "to": f"/topics/{topic}",
                "notification": {"title": title, "body": body},
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    FCM_API_URL,
                    headers={
                        "Authorization": f"key={settings.FCM_SERVER_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code == 200:
                    logger.info("Topic push sent via REST topic=%s", topic)
                    return True
                logger.warning(
                    "Topic push REST failed for topic=%s: %s %s",
                    topic,
                    response.status_code,
                    response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("Topic push REST send failed for topic=%s: %s", topic, e)
            return False


push_service = PushNotificationService()
