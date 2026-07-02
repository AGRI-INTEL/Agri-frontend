"""
Twilio SMS service for alerting farmers without smartphones
"""

import logging
from typing import Optional

from config.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

try:
    from twilio.rest import Client as TwilioClient

    TWILIO_AVAILABLE = True
except ImportError:
    TwilioClient = None
    TWILIO_AVAILABLE = False

TWILIO_API_URL = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"


class SMSService:
    def __init__(self):
        self._client: Optional[TwilioClient] = None
        if TWILIO_AVAILABLE and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            try:
                self._client = TwilioClient(
                    settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
                )
                logger.info("Twilio client initialized")
            except Exception as e:
                logger.warning("Twilio client init failed: %s — will use REST fallback", e)

    async def send_sms(self, to: str, body: str) -> bool:
        if not settings.TWILIO_PHONE_NUMBER:
            logger.warning("TWILIO_PHONE_NUMBER not set — cannot send SMS")
            return False

        if self._client is not None:
            return await self._send_via_sdk(to, body)
        return await self._send_via_rest(to, body)

    async def send_bulk_sms(self, numbers: list[str], body: str) -> list[bool]:
        if not numbers:
            return []
        results = []
        for number in numbers:
            ok = await self.send_sms(number, body)
            results.append(ok)
        return results

    async def _send_via_sdk(self, to: str, body: str) -> bool:
        try:
            message = self._client.messages.create(
                body=body,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=to,
            )
            logger.info("SMS sent via SDK to %s — sid=%s", to, message.sid)
            return True
        except Exception as e:
            logger.error("SMS SDK send failed to %s: %s", to, e)
            return False

    async def _send_via_rest(self, to: str, body: str) -> bool:
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            logger.warning("Twilio credentials not configured — cannot send SMS")
            return False
        try:
            import httpx

            auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            payload = {
                "To": to,
                "From": settings.TWILIO_PHONE_NUMBER,
                "Body": body,
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(TWILIO_API_URL, data=payload, auth=auth)
                if response.status_code == 201:
                    resp_json = response.json()
                    logger.info(
                        "SMS sent via REST to %s — sid=%s", to, resp_json.get("sid")
                    )
                    return True
                logger.warning(
                    "SMS REST failed to %s: %s %s",
                    to,
                    response.status_code,
                    response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("SMS REST send failed to %s: %s", to, e)
            return False


sms_service = SMSService()
