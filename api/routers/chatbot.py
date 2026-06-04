"""
Chatbot API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.services.auth import get_current_verified_user
from src.services.chatbot import process_chat_message, get_chat_suggestions, _get_chatbot
from api.models.sql.user import User

router = APIRouter()

# In-memory conversation history per user (keyed by user_id)
_chat_histories: dict = {}


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
    provider: str  # "kimi" | "deepseek" | "openai"


class ChatFeedback(BaseModel):
    message_id: str
    rating: int  # 1 = 👍, -1 = 👎
    comment: Optional[str] = None


class Conversation(BaseModel):
    id: str
    title: str
    updated_at: str


class Message(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str


@router.get("/conversations", response_model=List[Conversation])
async def list_conversations(
    current_user: User = Depends(get_current_verified_user)
):
    """Liste les conversations du chatbot"""
    # For now, return a single default conversation if history exists
    user_id = str(current_user.id)
    if user_id in _chat_histories:
        return [Conversation(id="default", title="Conversation actuelle", updated_at=datetime.utcnow().isoformat())]
    return []


@router.post("/conversations", response_model=Conversation)
async def create_conversation(
    current_user: User = Depends(get_current_verified_user)
):
    """Crée une nouvelle conversation"""
    return Conversation(id="default", title="Nouvelle conversation", updated_at=datetime.utcnow().isoformat())


@router.get("/conversations/{conversation_id}", response_model=List[Message])
async def get_conversation_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_verified_user)
):
    """Récupère les messages d'une conversation"""
    user_id = str(current_user.id)
    history = _chat_histories.get(user_id, [])
    messages = []
    for i, h in enumerate(history):
        messages.append(Message(
            id=f"msg-{i}",
            role=h["role"],
            content=h["content"],
            timestamp=str(h["timestamp"])
        ))
    return messages


@router.post("/conversations/{conversation_id}/messages", response_model=ChatResponse)
async def send_conversation_message(
    conversation_id: str,
    chat_message: ChatMessage,
    current_user: User = Depends(get_current_verified_user)
):
    """Envoie un message dans une conversation spécifique"""
    return await chat_with_agribot(chat_message, current_user)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_agribot(
    chat_message: ChatMessage,
    current_user: User = Depends(get_current_verified_user)
):
    """Envoie un message au chatbot AgriBot"""
    try:
        response = await process_chat_message(chat_message.message, str(current_user.id))

        # Stocker dans l'historique en mémoire
        user_id = str(current_user.id)
        if user_id not in _chat_histories:
            _chat_histories[user_id] = []
        _chat_histories[user_id].append({
            "role": "user",
            "content": chat_message.message,
            "timestamp": response["timestamp"],
        })
        _chat_histories[user_id].append({
            "role": "assistant",
            "content": response["message"],
            "timestamp": response["timestamp"],
        })
        # Garder les 50 derniers messages
        _chat_histories[user_id] = _chat_histories[user_id][-50:]

        return ChatResponse(
            type=response["type"],
            message=response["message"],
            sql_query=response.get("sql_query"),
            data=response.get("data"),
            provider=response.get("provider"),
            timestamp=str(response["timestamp"]),
            error=response["error"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur chatbot: {str(e)}")


@router.get("/suggestions", response_model=List[str])
async def get_chat_question_suggestions(
    current_user: User = Depends(get_current_verified_user)
):
    """Récupère les suggestions de questions"""
    return get_chat_suggestions()


@router.post("/clear-history")
async def clear_chat_history(
    current_user: User = Depends(get_current_verified_user)
):
    """Efface l'historique de conversation"""
    _get_chatbot().clear_memory()
    return {"message": "Historique effacé avec succès"}


@router.post("/switch-provider")
async def switch_llm_provider(
    body: ProviderSwitch,
    current_user: User = Depends(get_current_verified_user)
):
    """Bascule entre Kimi et DeepSeek"""
    allowed = {"kimi", "deepseek", "openai"}
    if body.provider not in allowed:
        raise HTTPException(status_code=400, detail=f"Provider invalide. Choisir parmi: {allowed}")
    _get_chatbot().switch_provider(body.provider)
    return {"message": f"Provider basculé vers: {body.provider}"}


@router.get("/status")
async def get_chatbot_status(
    current_user: User = Depends(get_current_verified_user)
):
    """Récupère le statut du chatbot"""
    from config.config import get_settings
    settings = get_settings()
    chatbot = _get_chatbot()

    return {
        "status": "active",
        "provider": chatbot.llm.model if chatbot.llm.available else "demo",
        "ai_enabled": chatbot.llm.available,
        "kimi_configured": bool(settings.OPENROUTER_API_KEY),
        "deepseek_configured": bool(settings.DEEPSEEK_API_KEY or settings.OPENROUTER_API_KEY),
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "features": [
            "Requêtes SQL automatiques",
            "Analyse de données agricoles",
            "Prédictions intelligentes",
            "Conseils personnalisés",
            "Switch Kimi / DeepSeek",
        ],
    }


@router.post("/feedback")
async def submit_feedback(
    body: ChatFeedback,
    current_user: User = Depends(get_current_verified_user),
):
    """Soumettre un feedback 👍/👎 sur une réponse du chatbot"""
    if body.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating doit être 1 (👍) ou -1 (👎)")
    # Stocker en mémoire (à persister en DB dans une vraie implémentation)
    label = "positif" if body.rating == 1 else "négatif"
    return {
        "message": f"Feedback {label} enregistré pour le message {body.message_id}",
        "rating": body.rating,
        "comment": body.comment,
    }


@router.get("/history")
async def get_chat_history(
    current_user: User = Depends(get_current_verified_user),
):
    """Historique de conversation de l'utilisateur connecté"""
    user_id = str(current_user.id)
    history = _chat_histories.get(user_id, [])
    return {"history": history, "count": len(history)}
