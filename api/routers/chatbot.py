"""
Chatbot API endpoints
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from src.services.auth import get_current_active_user
from src.services.chatbot import process_chat_message, get_chat_suggestions, _get_chatbot
from api.models.sql.user import User

router = APIRouter()

# In-memory conversation store per user: user_id -> { conv_id -> [messages] }
_chat_store: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
# Conversation metadata: user_id -> { conv_id -> { title, created_at, updated_at } }
_conv_meta: Dict[str, Dict[str, Dict[str, str]]] = {}


class ChatMessage(BaseModel):
    message: str
    context: dict = {}


class ChatResponse(BaseModel):
    type: str
    message: str
    sql_query: Optional[str] = None
    data: Optional[list[dict[str, Any]]] = None
    provider: Optional[str] = None
    timestamp: str
    error: bool


class ProviderSwitch(BaseModel):
    provider: str


class ChatFeedback(BaseModel):
    message_id: str
    rating: int
    comment: Optional[str] = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    media_type: str = "text"
    status: str = "read"
    conversation_id: str = "default"


class ConversationOut(BaseModel):
    id: str
    title: str
    updated_at: str
    message_count: int = 0
    messages: Optional[List[MessageOut]] = None


class MessageInput(BaseModel):
    content: str
    provider: Optional[str] = "kimi"


class SendMessageInput(BaseModel):
    content: str
    conversation_id: Optional[str] = None
    provider: Optional[str] = "kimi"


def _get_user_store(user_id: str) -> Dict[str, List[Dict[str, Any]]]:
    if user_id not in _chat_store:
        _chat_store[user_id] = {}
    return _chat_store[user_id]


def _get_user_meta(user_id: str) -> Dict[str, Dict[str, str]]:
    if user_id not in _conv_meta:
        _conv_meta[user_id] = {}
    return _conv_meta[user_id]


def _ensure_conv(user_id: str, conv_id: str) -> str:
    store = _get_user_store(user_id)
    if conv_id not in store:
        store[conv_id] = []
    return conv_id


@router.get("/conversations", response_model=List[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_active_user)
):
    user_id = str(current_user.id)
    store = _get_user_store(user_id)
    meta = _get_user_meta(user_id)
    convs = []
    for cid in store:
        m = meta.get(cid, {})
        convs.append(ConversationOut(
            id=cid,
            title=m.get("title", "Analyse en cours"),
            updated_at=m.get("updated_at", datetime.now(timezone.utc).isoformat()),
            message_count=len(store[cid]) // 2,
        ))
    convs.sort(key=lambda c: c.updated_at, reverse=True)
    return convs


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    current_user: User = Depends(get_current_active_user)
):
    user_id = str(current_user.id)
    conv_id = str(uuid.uuid4())
    _ensure_conv(user_id, conv_id)
    now = datetime.now(timezone.utc).isoformat()
    _get_user_meta(user_id)[conv_id] = {
        "title": "Nouvelle conversation",
        "created_at": now,
        "updated_at": now,
    }
    return ConversationOut(
        id=conv_id,
        title="Nouvelle conversation",
        updated_at=now,
        message_count=0,
        messages=[],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation_detail(
    conversation_id: str,
    current_user: User = Depends(get_current_active_user)
):
    user_id = str(current_user.id)
    _ensure_conv(user_id, conversation_id)
    store = _get_user_store(user_id)
    meta = _get_user_meta(user_id)
    m = meta.get(conversation_id, {})

    messages = []
    for i, h in enumerate(store.get(conversation_id, [])):
        messages.append(MessageOut(
            id=h.get("id", f"msg-{i}"),
            role=h["role"],
            content=h["content"],
            created_at=str(h.get("timestamp", datetime.now(timezone.utc).isoformat())),
            conversation_id=conversation_id,
            status="read",
            media_type="text",
        ))

    return ConversationOut(
        id=conversation_id,
        title=m.get("title", "Analyse en cours" if messages else "Nouvelle conversation"),
        updated_at=m.get("updated_at", datetime.now(timezone.utc).isoformat()),
        message_count=len(messages),
        messages=messages,
    )


@router.post("/conversations/{conversation_id}/messages", response_model=ChatResponse)
async def send_conversation_message(
    conversation_id: str,
    body: MessageInput,
    current_user: User = Depends(get_current_active_user)
):
    if conversation_id in ("null", "undefined", ""):
        conversation_id = "default"
    _ensure_conv(str(current_user.id), conversation_id)

    if body.provider:
        allowed = {"kimi", "deepseek", "openai"}
        if body.provider in allowed:
            _get_chatbot().switch_provider(body.provider, str(current_user.id))

    chat_message = ChatMessage(message=body.content)
    return await chat_with_agribot(chat_message, current_user)


@router.post("/messages", response_model=ChatResponse)
async def send_message(
    body: SendMessageInput,
    current_user: User = Depends(get_current_active_user),
):
    user_id = str(current_user.id)
    conv_id = body.conversation_id or "default"
    if conv_id in ("null", "undefined", ""):
        conv_id = "default"
    _ensure_conv(user_id, conv_id)

    if body.provider:
        allowed = {"kimi", "deepseek", "openai"}
        if body.provider in allowed:
            _get_chatbot().switch_provider(body.provider, user_id)

    chat_message = ChatMessage(message=body.content)
    return await chat_with_agribot(chat_message, current_user)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_agribot(
    chat_message: ChatMessage,
    current_user: User = Depends(get_current_active_user)
):
    try:
        user_id = str(current_user.id)
        response = await process_chat_message(chat_message.message, user_id)

        ts = response["timestamp"]
        store = _get_user_store(user_id)
        meta = _get_user_meta(user_id)

        conv_id = None
        for cid, msgs in store.items():
            conv_id = cid
            break
        if not conv_id:
            conv_id = str(uuid.uuid4())
            store[conv_id] = []
            now = datetime.now(timezone.utc).isoformat()
            meta[conv_id] = {"title": "Analyse en cours", "created_at": now, "updated_at": now}

        store[conv_id].append({
            "id": f"user-{uuid.uuid4().hex[:8]}",
            "role": "user",
            "content": chat_message.message,
            "timestamp": ts,
        })
        store[conv_id].append({
            "id": f"asst-{uuid.uuid4().hex[:8]}",
            "role": "assistant",
            "content": response["message"],
            "timestamp": ts,
        })
        store[conv_id] = store[conv_id][-50:]
        meta[conv_id]["updated_at"] = ts
        meta[conv_id]["title"] = chat_message.message[:60]

        return ChatResponse(
            type=response["type"],
            message=response["message"],
            sql_query=response.get("sql_query"),
            data=response.get("data"),
            provider=response.get("provider"),
            timestamp=str(ts),
            error=response["error"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur chatbot: {str(e)}")


@router.get("/suggestions", response_model=List[str])
async def get_chat_question_suggestions(
    current_user: User = Depends(get_current_active_user)
):
    return get_chat_suggestions()


@router.post("/clear-history")
async def clear_chat_history(
    current_user: User = Depends(get_current_active_user)
):
    user_id = str(current_user.id)
    if user_id in _chat_store:
        del _chat_store[user_id]
    if user_id in _conv_meta:
        del _conv_meta[user_id]
    _get_chatbot().clear_memory(user_id)
    return {"message": "Historique effacé avec succès"}


@router.post("/switch-provider")
async def switch_llm_provider(
    body: ProviderSwitch,
    current_user: User = Depends(get_current_active_user)
):
    allowed = {"kimi", "deepseek", "openai"}
    if body.provider not in allowed:
        raise HTTPException(status_code=400, detail=f"Provider invalide. Choisir parmi: {allowed}")
    _get_chatbot().switch_provider(body.provider)
    return {"message": f"Provider basculé vers: {body.provider}"}


@router.get("/status")
async def get_chatbot_status(
    current_user: User = Depends(get_current_active_user)
):
    from config.config import get_settings
    settings = get_settings()
    chatbot = _get_chatbot()

    return {
        "status": "active",
        "provider": chatbot.llm.model if chatbot.llm.available else "kimi",
        "ai_enabled": chatbot.llm.available,
        "kimi_configured": bool(settings.OPENROUTER_API_KEY),
        "deepseek_configured": bool(settings.DEEPSEEK_API_KEY or settings.OPENROUTER_API_KEY),
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "features": [
            "Requêtes SQL automatiques",
            "Analyse de données agricoles",
            "Prédictions intelligentes",
            "Conseils personnalisés",
            "Switch Kimi / DeepSeek / OpenAI",
        ],
    }


@router.post("/analyze-image")
async def analyze_image_chatbot(
    file: UploadFile = File(...),
    question: str = Form(default=""),
    current_user: User = Depends(get_current_active_user),
):
    import base64
    import httpx
    from config.config import get_settings

    settings = get_settings()

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image trop grande (max 10MB)")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    mime = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "image/jpeg")
    img_b64 = base64.b64encode(content).decode()

    api_key = getattr(settings, "OPENROUTER_API_KEY", None) or getattr(settings, "OPENAI_API_KEY", None)

    prompt = question.strip() if question.strip() else (
        "Tu es un expert agronome africain. Analyse cette image agricole et fournis: "
        "1) Ce que tu vois (culture, animal, sol, equipement, etc.) "
        "2) Etat de sante/qualite observe "
        "3) Problemes detectes (maladies, carences, parasites) "
        "4) Recommandations pratiques "
        "5) Score de sante global (0-100). "
        "Reponds en francais avec des emojis pertinents."
    )

    if api_key:
        try:
            has_openai_key = bool(getattr(settings, "OPENAI_API_KEY", None))
            base_url = "https://api.openai.com/v1" if has_openai_key else "https://openrouter.ai/api/v1"
            model = "gpt-4o-mini" if has_openai_key else "openai/gpt-4o-mini"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://agriintel360.lsgrouptogo.com",
                "X-Title": "AgriIntel360",
            }

            payload = {
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{img_b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
                "max_tokens": 800,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
                resp.raise_for_status()
                analysis_text = resp.json()["choices"][0]["message"]["content"]

            user_id = str(current_user.id)
            store = _get_user_store(user_id)
            conv_id = None
            for cid in store:
                conv_id = cid
                break
            if conv_id:
                ts = datetime.now(timezone.utc).isoformat()
                store[conv_id].append({
                    "id": f"user-{uuid.uuid4().hex[:8]}",
                    "role": "user",
                    "content": f"[Image: {file.filename}] {question}",
                    "timestamp": ts,
                })
                store[conv_id].append({
                    "id": f"asst-{uuid.uuid4().hex[:8]}",
                    "role": "assistant",
                    "content": analysis_text,
                    "timestamp": ts,
                })
                store[conv_id] = store[conv_id][-50:]

            return {
                "status": "completed",
                "filename": file.filename,
                "analysis": analysis_text,
                "model": model,
                "ai_powered": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            return {
                "status": "fallback",
                "filename": file.filename,
                "analysis": f"Analyse IA temporairement indisponible ({str(e)[:80]}). Verifiez la configuration.",
                "ai_powered": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    else:
        return {
            "status": "unconfigured",
            "filename": file.filename,
            "analysis": "Analyse d'image non disponible : aucune clé API IA configurée. Configurez OPENAI_API_KEY ou OPENROUTER_API_KEY dans le fichier .env.",
            "ai_powered": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.post("/feedback")
async def submit_feedback(
    body: ChatFeedback,
    current_user: User = Depends(get_current_active_user),
):
    if body.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating doit être 1 (👍) ou -1 (👎)")
    label = "positif" if body.rating == 1 else "négatif"
    return {
        "message": f"Feedback {label} enregistré pour le message {body.message_id}",
        "rating": body.rating,
        "comment": body.comment,
    }


@router.get("/history")
async def get_chat_history(
    current_user: User = Depends(get_current_active_user),
):
    user_id = str(current_user.id)
    store = _get_user_store(user_id)
    all_msgs = []
    for cid, msgs in store.items():
        for m in msgs:
            all_msgs.append({**m, "conversation_id": cid})
    all_msgs.sort(key=lambda x: x.get("timestamp", ""))
    return {"history": all_msgs, "count": len(all_msgs)}
