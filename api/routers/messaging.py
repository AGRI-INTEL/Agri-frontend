"""
API Router for private messaging — conversations, messages, files, polls, users
"""

import os
import uuid
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from pydantic import BaseModel
from typing import Optional

from config.database import get_db
from config.config import get_settings
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from src.services.messaging import messaging_service

router = APIRouter()
settings = get_settings()
UPLOAD_DIR = os.path.join(settings.UPLOAD_DIR, "messages")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _write_file(path: str, contents: bytes) -> None:
    with open(path, "wb") as f:
        f.write(contents)


class CreateConversationRequest(BaseModel):
    user_id: str


class SendMessageRequest(BaseModel):
    content: str = ""
    message_type: str = "text"
    audio_url: Optional[str] = None
    audio_duration: Optional[float] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    poll_data: Optional[dict] = None


class EditMessageRequest(BaseModel):
    content: str


class PollVoteRequest(BaseModel):
    option_index: int


# ── Users ───────────────────────────────────────────────────────────────────────────

@router.get("/users/search")
async def search_users(
    q: str = Query("", min_length=1, max_length=100),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Search users by name or email to start a conversation."""
    pattern = f"%{q}%"
    result = await db.execute(
        select(User).where(
            User.id != current_user.id,
            or_(
                User.full_name.ilike(pattern),
                User.username.ilike(pattern),
                User.email.ilike(pattern),
            ),
        ).limit(20)
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "name": u.full_name or u.username or "Utilisateur",
            "email": u.email,
            "avatar": u.avatar_url,
        }
        for u in users
    ]


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


# IMPORTANT: static routes must come BEFORE parameterized routes to avoid
# FastAPI matching "unread" as a conversation_id path parameter.

@router.get("/conversations/unread/count")
async def unread_count(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    count = await messaging_service.get_unread_count(str(current_user.id), db)
    return {"unread_count": count}


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
    before: Optional[str] = None,
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
    if not data.content and not data.audio_url and not data.file_url and not data.poll_data:
        raise HTTPException(status_code=400, detail="Contenu requis")
    try:
        msg = await messaging_service.send_message(
            conversation_id, str(current_user.id),
            content=data.content,
            message_type=data.message_type,
            db=db,
            audio_url=data.audio_url,
            audio_duration=data.audio_duration,
            file_url=data.file_url,
            file_name=data.file_name,
            file_type=data.file_type,
            poll_data=data.poll_data,
        )
        if not msg:
            raise HTTPException(status_code=404, detail="Conversation introuvable")
        await messaging_service.update_last_seen(str(current_user.id), db)
        return msg
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


# ── File upload ────────────────────────────────────────────────────────────────────

_ALLOWED_UPLOAD_MIME = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "video/mp4", "video/webm",
    "audio/mp3", "audio/wav", "audio/ogg", "audio/m4a", "audio/mpeg",
    "application/pdf",
    "text/plain", "text/csv",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
}
_DANGEROUS_EXTS = {
    ".php", ".php3", ".php4", ".php5", ".phtml",
    ".asp", ".aspx", ".jsp", ".cgi", ".sh", ".py", ".rb", ".pl",
    ".exe", ".bat", ".cmd", ".scr", ".vbs", ".js",
}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_verified_user),
):
    """Upload a file and return its URL."""
    try:
        ext = os.path.splitext(file.filename or "file")[1].lower() or ""
        if ext in _DANGEROUS_EXTS:
            raise HTTPException(status_code=400, detail=f"Extension non autorisée: {ext}")
        mime = (file.content_type or "application/octet-stream").split(";")[0].strip()
        if mime not in _ALLOWED_UPLOAD_MIME:
            raise HTTPException(status_code=400, detail=f"Type MIME non autorisé: {mime}")

        contents = await file.read()
        if len(contents) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 50 MB)")

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.normpath(os.path.join(UPLOAD_DIR, safe_name))
        if not file_path.startswith(os.path.normpath(UPLOAD_DIR)):
            raise HTTPException(status_code=400, detail="Chemin de fichier invalide")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: _write_file(file_path, contents))
        return {
            "url": f"/api/v1/messaging/files/{safe_name}",
            "name": file.filename or safe_name,
            "type": mime,
        }
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status_code=500, detail=f"Permission refusée: {e}")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Erreur système: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload: {e}")


# ── Poll vote ──────────────────────────────────────────────────────────────────────

@router.post("/polls/{message_id}/vote")
async def vote_poll(
    message_id: str,
    data: PollVoteRequest,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await messaging_service.vote_poll(message_id, str(current_user.id), data.option_index, db)
    if not result:
        raise HTTPException(status_code=404, detail="Sondage introuvable")
    return result


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


# ── File serving ────────────────────────────────────────────────────────────────────

@router.get("/files/{filename}")
async def serve_file(filename: str):
    """Serve an uploaded file."""
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return FileResponse(file_path)


# ── Presence ────────────────────────────────────────────────────────────────────────

@router.post("/presence")
async def update_presence(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await messaging_service.update_last_seen(str(current_user.id), db)
    return {"status": "ok"}


@router.get("/users/{user_id}/online")
async def get_online_status(
    user_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    return await messaging_service.get_online_status(user_id, db)
