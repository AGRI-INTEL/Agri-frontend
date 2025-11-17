"""
Chatbot API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from src.services.auth import get_current_verified_user
from src.services.chatbot import process_chat_message, get_chat_suggestions
from api.models.sql.user import User

router = APIRouter()


class ChatMessage(BaseModel):
    """Schema pour les messages du chat"""
    message: str
    context: Dict[str, Any] = {}


class ChatResponse(BaseModel):
    """Schema pour les réponses du chat"""
    type: str
    message: str
    sql_query: str = None
    data: List[Dict[str, Any]] = None
    demo_data: List[Dict[str, Any]] = None
    timestamp: str
    error: bool


@router.post("/chat", response_model=ChatResponse)
async def chat_with_agribot(
    chat_message: ChatMessage,
    current_user: User = Depends(get_current_verified_user)
):
    """Envoie un message au chatbot AgriBot"""
    
    try:
        response = await process_chat_message(
            chat_message.message, 
            str(current_user.id)
        )
        
        return ChatResponse(
            type=response['type'],
            message=response['message'],
            sql_query=response.get('sql_query'),
            data=response.get('data', []),
            demo_data=response.get('demo_data', []),
            timestamp=response['timestamp'].isoformat(),
            error=response['error']
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur chatbot: {str(e)}")


@router.get("/suggestions", response_model=List[str])
async def get_chat_question_suggestions(
    current_user: User = Depends(get_current_verified_user)
):
    """Récupère les suggestions de questions pour le chat"""
    
    try:
        return get_chat_suggestions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur suggestions: {str(e)}")


@router.post("/clear-history")
async def clear_chat_history(
    current_user: User = Depends(get_current_verified_user)
):
    """Efface l'historique de conversation du chatbot"""
    
    try:
        from src.services.chatbot import agri_chatbot
        agri_chatbot.clear_memory()
        
        return {"message": "Historique de conversation effacé avec succès"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur clear history: {str(e)}")


@router.get("/status")
async def get_chatbot_status(
    current_user: User = Depends(get_current_verified_user)
):
    """Récupère le statut du chatbot"""
    
    from src.services.chatbot import agri_chatbot
    from config.config import get_settings
    
    settings = get_settings()
    
    return {
        "status": "active",
        "ai_enabled": bool(settings.OPENAI_API_KEY),
        "database_connected": agri_chatbot.db_engine is not None,
        "features": [
            "Requêtes SQL automatiques",
            "Analyse de données agricoles",
            "Prédictions intelligentes",
            "Conseils personnalisés"
        ]
    }