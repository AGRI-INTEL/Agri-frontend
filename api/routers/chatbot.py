"""
Chatbot API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from src.services.auth import get_current_active_user
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


class Message(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    media_type: str = "text"
    status: str = "read"
    conversation_id: str = "default"


class Conversation(BaseModel):
    id: str
    title: str
    updated_at: str
    message_count: int = 0
    messages: Optional[List[Message]] = None


@router.get("/conversations", response_model=List[Conversation])
async def list_conversations(
    current_user: User = Depends(get_current_active_user)
):
    """Liste les conversations du chatbot"""
    user_id = str(current_user.id)
    history = _chat_histories.get(user_id, [])
    if history:
        return [Conversation(
            id="default", 
            title="Analyse en cours", 
            updated_at=datetime.now(timezone.utc).isoformat(),
            message_count=len(history)
        )]
    return []


@router.post("/conversations", response_model=Conversation)
async def create_conversation(
    current_user: User = Depends(get_current_active_user)
):
    """Crée une nouvelle conversation"""
    return Conversation(
        id="default", 
        title="Nouvelle conversation", 
        updated_at=datetime.now(timezone.utc).isoformat(),
        message_count=0,
        messages=[]
    )


@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation_detail(
    conversation_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Récupère les détails et messages d'une conversation"""
    user_id = str(current_user.id)
    history = _chat_histories.get(user_id, [])
    messages = []
    for i, h in enumerate(history):
        messages.append(Message(
            id=f"msg-{i}",
            role=h["role"],
            content=h["content"],
            created_at=str(h.get("timestamp", datetime.now(timezone.utc).isoformat())),
            conversation_id=conversation_id,
            status="read",
            media_type="text",
        ))
    
    return Conversation(
        id=conversation_id,
        title="Analyse en cours" if messages else "Nouvelle conversation",
        updated_at=datetime.now(timezone.utc).isoformat(),
        message_count=len(messages),
        messages=messages
    )


class MessageInput(BaseModel):
    content: str
    provider: Optional[str] = "demo"


@router.post("/conversations/{conversation_id}/messages", response_model=ChatResponse)
async def send_conversation_message(
    conversation_id: str,
    body: MessageInput,
    current_user: User = Depends(get_current_active_user)
):
    """Envoie un message dans une conversation (JSON body)"""
    if conversation_id in ("null", "undefined", ""):
        conversation_id = "default"

    if body.provider:
        allowed = {"kimi", "deepseek", "openai", "demo"}
        if body.provider in allowed:
            _get_chatbot().switch_provider(body.provider, str(current_user.id))

    chat_message = ChatMessage(message=body.content)
    return await chat_with_agribot(chat_message, current_user)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_agribot(
    chat_message: ChatMessage,
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user)
):
    """Récupère les suggestions de questions"""
    return get_chat_suggestions()


@router.post("/clear-history")
async def clear_chat_history(
    current_user: User = Depends(get_current_active_user)
):
    """Efface l'historique de conversation"""
    _get_chatbot().clear_memory()
    return {"message": "Historique effacé avec succès"}


@router.post("/switch-provider")
async def switch_llm_provider(
    body: ProviderSwitch,
    current_user: User = Depends(get_current_active_user)
):
    """Bascule entre Kimi et DeepSeek"""
    allowed = {"kimi", "deepseek", "openai"}
    if body.provider not in allowed:
        raise HTTPException(status_code=400, detail=f"Provider invalide. Choisir parmi: {allowed}")
    _get_chatbot().switch_provider(body.provider)
    return {"message": f"Provider basculé vers: {body.provider}"}


@router.get("/status")
async def get_chatbot_status(
    current_user: User = Depends(get_current_active_user)
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


@router.post("/analyze-image")
async def analyze_image_chatbot(
    file: UploadFile = File(...),
    question: str = Form(default=""),
    current_user: User = Depends(get_current_active_user),
):
    """Analyse une image agricole via IA vision (chatbot endpoint)"""
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

            # Store in chat history
            user_id = str(current_user.id)
            if user_id not in _chat_histories:
                _chat_histories[user_id] = []
            ts = datetime.now(timezone.utc).isoformat()
            _chat_histories[user_id].append({
                "role": "user",
                "content": f"[Image: {file.filename}] {question}",
                "timestamp": ts,
            })
            _chat_histories[user_id].append({
                "role": "assistant",
                "content": analysis_text,
                "timestamp": ts,
            })
            _chat_histories[user_id] = _chat_histories[user_id][-50:]

            return {
                "status": "completed",
                "filename": file.filename,
                "analysis": analysis_text,
                "model": model,
                "ai_powered": True,
                "timestamp": ts,
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
            "status": "demo",
            "filename": file.filename,
            "analysis": (
                "Analyse visuelle (mode demo)\n\n"
                "Pour activer l'analyse IA complete, configurez OPENROUTER_API_KEY dans votre fichier .env.\n\n"
                "L'analyse visuelle peut detecter:\n"
                "- Maladies des cultures\n"
                "- Carences nutritionnelles\n"
                "- Etat du sol\n"
                "- Sante du betail\n"
                "- Qualite des recoltes"
            ),
            "ai_powered": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.post("/feedback")
async def submit_feedback(
    body: ChatFeedback,
    current_user: User = Depends(get_current_active_user),
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
    current_user: User = Depends(get_current_active_user),
):
    """Historique de conversation de l'utilisateur connecté"""
    user_id = str(current_user.id)
    history = _chat_histories.get(user_id, [])
    return {"history": history, "count": len(history)}
