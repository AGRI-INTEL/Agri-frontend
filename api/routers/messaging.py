"""
API Router for private messaging
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from src.services.messaging import messaging_service

router = APIRouter()


class CreateConversationRequest(BaseModel):
    user_id: str


class SendMessageRequest(BaseModel):
    content: str = ""
    message_type: str = "text"
    audio_url: Optional[str] = None
    audio_duration: Optional[float] = None


class EditMessageRequest(BaseModel):
    content: str


# ── Conversations ──────────────────────────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await messaging_service.get_conversations(str(current_user.id), db)


@router.post("/conversations")
async def create_conversation(
    data: CreateConversationRequest,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    if data.user_id == str(current_user.id):
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas créer une conversation avec vous-même")
    return await messaging_service.get_or_create_conversation(
        str(current_user.id), data.user_id, db
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await messaging_service.get_conversation(conversation_id, str(current_user.id), db)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return conv


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await messaging_service.delete_conversation(conversation_id, str(current_user.id), db)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {"message": "Conversation supprimée"}


# ── Messages ────────────────────────────────────────────────────────────────────────

@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: str = None,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    messages = await messaging_service.get_messages(
        conversation_id, str(current_user.id), limit, before, db
    )
    if messages is None:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return messages


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    data: SendMessageRequest,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    if not data.content and not data.audio_url:
        raise HTTPException(status_code=400, detail="Contenu requis")
    if data.audio_url:
        msg = await messaging_service.send_message(
            conversation_id, str(current_user.id), data.content, "voice", db,
            audio_url=data.audio_url, audio_duration=data.audio_duration,
        )
    else:
        msg = await messaging_service.send_message(
            conversation_id, str(current_user.id), data.content, data.message_type, db
        )
    if not msg:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    await messaging_service.update_last_seen(str(current_user.id), db)
    return msg


@router.put("/conversations/{conversation_id}/messages/{message_id}")
async def edit_message(
    conversation_id: str,
    message_id: str,
    data: EditMessageRequest,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="Contenu requis")
    msg = await messaging_service.edit_message(message_id, str(current_user.id), data.content, db)
    if not msg:
        raise HTTPException(status_code=404, detail="Message non trouvé")
    return msg


@router.delete("/conversations/{conversation_id}/messages/{message_id}")
async def delete_message(
    conversation_id: str,
    message_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await messaging_service.delete_message(message_id, str(current_user.id), db)
    if not ok:
        raise HTTPException(status_code=404, detail="Message non trouvé")
    return {"message": "Message supprimé"}


# ── Read status ─────────────────────────────────────────────────────────────────────

@router.put("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await messaging_service.mark_read(conversation_id, str(current_user.id), db)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {"message": "Marqué comme lu"}


@router.get("/conversations/unread/count")
async def unread_count(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    count = await messaging_service.get_unread_count(str(current_user.id), db)
    return {"unread_count": count}


# ── Presence ────────────────────────────────────────────────────────────────────────

@router.post("/presence")
async def update_presence(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Called by the frontend periodically to signal the user is online."""
    await messaging_service.update_last_seen(str(current_user.id), db)
    return {"status": "ok"}


@router.get("/users/{user_id}/online")
async def get_online_status(
    user_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await messaging_service.get_online_status(user_id, db)
