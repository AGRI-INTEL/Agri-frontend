"""WebSocket endpoints for real-time notifications"""

import json
import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from fastapi.websockets import WebSocketState

logger = logging.getLogger("app")

websocket_router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Connect a user"""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"User {user_id} connected via WebSocket")
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Disconnect a user"""
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
                logger.info(f"User {user_id} disconnected from WebSocket")
            except ValueError:
                pass
    
    async def send_personal_message(self, message: dict, user_id: str):
        """Send message to specific user"""
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    if connection.client_state == WebSocketState.CONNECTED:
                        await connection.send_text(json.dumps(message))
                    else:
                        disconnected.append(connection)
                except Exception as e:
                    logger.error(f"Error sending message to {user_id}: {e}")
                    disconnected.append(connection)
            
            # Remove disconnected connections
            for conn in disconnected:
                self.disconnect(conn, user_id)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected users"""
        for user_id, connections in self.active_connections.items():
            await self.send_personal_message(message, user_id)


manager = ConnectionManager()


@websocket_router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for real-time notifications"""
    await manager.connect(websocket, user_id)
    
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            
            elif message.get("type") == "subscribe":
                # Handle subscription to specific topics (alerts, etc.)
                topics = message.get("topics", [])
                logger.info(f"User {user_id} subscribed to topics: {topics}")
                await websocket.send_text(json.dumps({
                    "type": "subscription_confirmed",
                    "topics": topics
                }))
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(websocket, user_id)


async def send_notification(user_id: str, notification: dict):
    """Send notification to specific user"""
    message = {
        "type": "notification",
        "data": notification,
        "timestamp": notification.get("timestamp")
    }
    await manager.send_personal_message(message, user_id)


async def send_alert(user_id: str, alert: dict):
    """Send alert to specific user"""
    message = {
        "type": "alert",
        "data": alert,
        "timestamp": alert.get("timestamp")
    }
    await manager.send_personal_message(message, user_id)


async def broadcast_system_message(message: str):
    """Broadcast system message to all users"""
    msg = {
        "type": "system_message",
        "message": message,
        "timestamp": None  # Add timestamp
    }
    await manager.broadcast(msg)