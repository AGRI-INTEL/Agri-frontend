"""WebSocket endpoints for real-time notifications — authenticated"""

import json
import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.websockets import WebSocketState
from src.services.auth import AuthService

logger = logging.getLogger("app")

websocket_router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections"""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"[WS] User {user_id} connected")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                logger.info(f"[WS] User {user_id} disconnected")
            except ValueError:
                pass

    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    if connection.client_state == WebSocketState.CONNECTED:
                        await connection.send_text(json.dumps(message))
                    else:
                        disconnected.append(connection)
                except Exception as e:
                    logger.error(f"[WS] Error sending to {user_id}: {e}")
                    disconnected.append(connection)
            for conn in disconnected:
                self.disconnect(conn, user_id)

    async def broadcast(self, message: dict):
        for user_id in self.active_connections:
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()


@websocket_router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    """Authenticated WebSocket endpoint. Requires ?token=<JWT> in query."""
    try:
        token_data = AuthService.verify_token(token, token_type="access")
        user_id = str(token_data.user_id)
    except Exception:
        await websocket.close(code=4001, reason="Authentification requise")
        return

    await manager.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif message.get("type") == "subscribe":
                topics = message.get("topics", [])
                logger.info(f"[WS] User {user_id} subscribed to: {topics}")
                await websocket.send_text(json.dumps({
                    "type": "subscription_confirmed",
                    "topics": topics
                }))

    except WebSocketDisconnect:
        logger.info(f"[WS] Disconnected user: {user_id}")
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"[WS] Error for user {user_id}: {e}")
        manager.disconnect(websocket, user_id)


@websocket_router.websocket("/ws/anonymous")
async def websocket_anonymous_endpoint(websocket: WebSocket):
    """Explicit anonymous WebSocket endpoint — no auth required."""
    await websocket.accept()
    logger.info("[WS] Anonymous connection established")
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass


async def send_notification(user_id: str, notification: dict):
    message = {
        "type": "notification",
        "data": notification,
        "timestamp": notification.get("timestamp")
    }
    await manager.send_personal_message(message, user_id)


async def send_alert(user_id: str, alert: dict):
    message = {
        "type": "alert",
        "data": alert,
        "timestamp": alert.get("timestamp")
    }
    await manager.send_personal_message(message, user_id)


async def broadcast_system_message(message: str):
    msg = {
        "type": "system_message",
        "message": message,
        "timestamp": None
    }
    await manager.broadcast(msg)
