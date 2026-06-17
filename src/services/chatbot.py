"""
AgriIntel360 - Chatbot IA avec OpenRouter (Kimi / DeepSeek)
Assistant conversationnel pour analyse de données agricoles africaines
"""

import re
import json
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy import create_engine, text

from config.config import get_settings

settings = get_settings()

# Tables autorisées pour les requêtes SQL
ALLOWED_TABLES = {
    'countries', 'crops', 'productions', 'weather_data',
    'price_data', 'predictions', 'alerts'
}

# Mots-clés SQL dangereux
FORBIDDEN_SQL_KEYWORDS = [
    'insert', 'update', 'delete', 'drop', 'truncate', 'alter',
    'create', 'exec', 'execute', 'sp_', 'xp_', '--', '/*', '*/', ';'
]


def _build_system_prompt() -> str:
    schema = """
- countries: Pays africains (id, name, iso_code, region, gdp, population, agricultural_land_percent)
- crops: Cultures (id, name, scientific_name, category, growth_period_days, water_requirement)
- productions: Production agricole (id, country_id, crop_id, year, season, area_harvested_ha, production_tonnes, yield_tonnes_per_ha, producer_price_usd)
- weather_data: Météo (id, country_id, date, temperature_celsius, humidity_percent, precipitation_mm, wind_speed_kmh)
- price_data: Prix marché (id, country_id, crop_id, date, price_usd_per_kg, market_name, supply_level, demand_level)
- predictions: Prédictions IA (id, country_id, crop_id, prediction_type, target_date, predicted_value, confidence_score)
- alerts: Alertes (id, title, message, alert_type, severity, country_id, crop_id)
"""
    return f"""Tu es AgriBot, un assistant IA expert en agriculture africaine et analyse de données.
Tu aides les utilisateurs à analyser leurs données agricoles.

SCHÉMA DE LA BASE DE DONNÉES:
{schema}

RÈGLES SQL:
1. Génère UNIQUEMENT des requêtes SELECT
2. Formate les requêtes SQL entre ```sql et ```
3. Utilise des JOINtures appropriées
4. Ajoute LIMIT 50 par défaut
5. Utilise des alias clairs pour les colonnes

PAYS: Togo (TG), Ghana (GH), Nigeria (NG), Côte d'Ivoire (CI), Burkina Faso (BF), Sénégal (SN)
CULTURES: Maïs, Riz, Manioc, Igname, Cacao, Café, Coton, Arachide

Réponds en français. Sois professionnel, précis et utilise des emoji pertinents (🌾📊🌍💰🌤️)."""


class OpenRouterLLM:
    """Client LLM via OpenRouter (compatible OpenAI API)"""

    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.DEFAULT_LLM_PROVIDER
        self._configure()

    def _configure(self):
        """Configure le provider LLM actif"""
        if self.provider == "kimi" and self.settings.OPENROUTER_API_KEY:
            self.api_key = self.settings.OPENROUTER_API_KEY
            self.base_url = self.settings.OPENROUTER_BASE_URL
            self.model = self.settings.KIMI_MODEL
            self.available = True
        elif self.provider == "deepseek" and (self.settings.DEEPSEEK_API_KEY or self.settings.OPENROUTER_API_KEY):
            self.api_key = self.settings.DEEPSEEK_API_KEY or self.settings.OPENROUTER_API_KEY
            self.base_url = self.settings.OPENROUTER_BASE_URL
            self.model = self.settings.DEEPSEEK_MODEL
            self.available = True
        elif self.provider == "openai" and self.settings.OPENAI_API_KEY:
            self.api_key = self.settings.OPENAI_API_KEY
            self.base_url = "https://api.openai.com/v1"
            self.model = "gpt-3.5-turbo"
            self.available = True
        else:
            self.available = False

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
        """Envoie une requête au LLM et retourne la réponse"""
        if not self.available:
            raise RuntimeError("LLM non disponible")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = "https://agriintel360.com"
            headers["X-Title"] = "AgriIntel360"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1500,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    def switch_provider(self, provider: str):
        """Bascule entre kimi, deepseek, openai"""
        self.provider = provider
        self._configure()


class AgriChatbot:
    """Chatbot IA spécialisé pour l'agriculture africaine"""

    def __init__(self):
        self.settings = get_settings()
        self.llm = OpenRouterLLM()
        self.system_prompt = _build_system_prompt()
        self.user_histories: Dict[str, List[Dict[str, str]]] = {}
        self.user_providers: Dict[str, str] = {}
        self.max_history = 10

        # DB engine (lazy)
        self._db_engine = None

    def _get_db_engine(self):
        if self._db_engine is None:
            try:
                sync_url = self.settings.DATABASE_URL
                self._db_engine = create_engine(sync_url, pool_pre_ping=True)
            except Exception:
                pass
        return self._db_engine

    def _get_history(self, user_id: str) -> List[Dict[str, str]]:
        user_id = user_id or "anonymous"
        if user_id not in self.user_histories:
            self.user_histories[user_id] = []
        return self.user_histories[user_id]

    def _get_provider(self, user_id: str) -> str:
        user_id = user_id or "anonymous"
        return self.user_providers.get(user_id, self.settings.DEFAULT_LLM_PROVIDER)

    def _is_safe_query(self, sql: str) -> bool:
        sql_lower = sql.lower().strip()
        if not sql_lower.startswith("select"): return False
        for kw in FORBIDDEN_SQL_KEYWORDS:
            if kw in sql_lower: return False
        return True

    def _extract_sql(self, text: str) -> Optional[str]:
        match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if not match:
            match = re.search(r'```\s*(SELECT.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else None

    async def _execute_sql(self, sql: str) -> Optional[List[Dict]]:
        if not self._is_safe_query(sql): return None
        engine = self._get_db_engine()
        if not engine: return None
        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                cols = list(result.keys())
                return [dict(zip(cols, row)) for row in result.fetchmany(100)]
        except Exception:
            return None

    def _classify_question(self, question: str) -> str:
        q = question.lower()
        data_keywords = ['combien', 'production', 'rendement', 'prix', 'météo', 'température', 'pluie', 'données', 'statistiques']
        return "sql" if any(kw in q for kw in data_keywords) else "general"

    async def process_question(self, question: str, user_id: str = "anonymous") -> Dict[str, Any]:
        """Traite une question utilisateur"""
        user_id = user_id or "anonymous"
        
        # Charger la config spécifique à l'utilisateur
        current_provider = self._get_provider(user_id)
        self.llm.switch_provider(current_provider)

        if not self.llm.available:
            return await self._demo_response(question)

        try:
            history = self._get_history(user_id)
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(history)
            messages.append({"role": "user", "content": question})

            response_text = await self.llm.chat(messages)

            # Mettre à jour l'historique
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": response_text})
            self.user_histories[user_id] = history[-self.max_history:]

            sql_query = self._extract_sql(response_text)
            data = await self._execute_sql(sql_query) if sql_query else None

            return {
                "type": "sql_response" if sql_query else "general_response",
                "message": response_text,
                "sql_query": sql_query,
                "data": data,
                "provider": self.llm.model,
                "timestamp": datetime.now().isoformat(),
                "error": False,
            }

        except Exception as e:
            return {
                "type": "error",
                "message": f"Erreur chatbot: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "error": True,
            }

    async def _demo_response(self, question: str) -> Dict[str, Any]:
        msg = f"🤖 **AgriBot - Mode Démo**\n\nQuestion: _{question}_\n\n⚙️ Configurez une clé OpenRouter dans `.env` pour activer l'IA."
        return {
            "type": "demo_response",
            "message": msg,
            "timestamp": datetime.now().isoformat(),
            "error": False,
        }

    def switch_provider(self, provider: str, user_id: str = "anonymous"):
        user_id = user_id or "anonymous"
        self.user_providers[user_id] = provider

    def clear_memory(self, user_id: str = None):
        if user_id:
            if user_id in self.user_histories: del self.user_histories[user_id]
        else:
            self.user_histories.clear()

    def get_suggested_questions(self) -> List[str]:
        return ["Quelle est la production de maïs au Togo ?", "Prix du cacao en Côte d'Ivoire", "Météo agricole au Ghana"]


_agri_chatbot = AgriChatbot()

def _get_chatbot() -> AgriChatbot:
    return _agri_chatbot

async def process_chat_message(message: str, user_id: str = "anonymous") -> Dict[str, Any]:
    return await _get_chatbot().process_question(message, user_id)

def get_chat_suggestions() -> List[str]:
    return _get_chatbot().get_suggested_questions()
