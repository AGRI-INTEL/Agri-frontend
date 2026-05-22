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
            print(f"✅ LLM configuré: Kimi ({self.model}) via OpenRouter")
        elif self.provider == "deepseek" and (self.settings.DEEPSEEK_API_KEY or self.settings.OPENROUTER_API_KEY):
            self.api_key = self.settings.DEEPSEEK_API_KEY or self.settings.OPENROUTER_API_KEY
            self.base_url = self.settings.OPENROUTER_BASE_URL
            self.model = self.settings.DEEPSEEK_MODEL
            self.available = True
            print(f"✅ LLM configuré: DeepSeek ({self.model}) via OpenRouter")
        elif self.settings.OPENAI_API_KEY:
            self.api_key = self.settings.OPENAI_API_KEY
            self.base_url = "https://api.openai.com/v1"
            self.model = "gpt-3.5-turbo"
            self.available = True
            print("✅ LLM configuré: OpenAI GPT-3.5-turbo")
        else:
            self.available = False
            print("⚠️ Aucune clé LLM configurée - Mode démo activé")

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
        """Envoie une requête au LLM et retourne la réponse"""
        if not self.available:
            raise RuntimeError("LLM non disponible")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter requiert ces headers
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
        """Bascule entre kimi et deepseek"""
        self.provider = provider
        self._configure()


class AgriChatbot:
    """Chatbot IA spécialisé pour l'agriculture africaine"""

    def __init__(self):
        self.settings = get_settings()
        self.llm = OpenRouterLLM()
        self.system_prompt = _build_system_prompt()
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = 10  # 5 échanges (user + assistant)

        # DB engine (lazy - seulement si DB disponible)
        self._db_engine = None

    def _get_db_engine(self):
        """Retourne le moteur DB, en le créant si nécessaire"""
        if self._db_engine is None:
            try:
                sync_url = self.settings.DATABASE_URL
                self._db_engine = create_engine(sync_url, pool_pre_ping=True)
            except Exception as e:
                print(f"⚠️ DB engine non disponible: {e}")
        return self._db_engine

    def _is_safe_query(self, sql: str) -> bool:
        """Vérifie qu'une requête SQL est sécurisée (SELECT uniquement)"""
        sql_lower = sql.lower().strip()
        # Doit commencer par SELECT
        if not sql_lower.startswith("select"):
            return False
        # Pas de mots-clés dangereux
        for kw in FORBIDDEN_SQL_KEYWORDS:
            if kw in sql_lower:
                return False
        return True

    def _extract_sql(self, text: str) -> Optional[str]:
        """Extrait une requête SQL d'une réponse LLM"""
        match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if not match:
            match = re.search(r'```\s*(SELECT.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else None

    async def _execute_sql(self, sql: str) -> Optional[List[Dict]]:
        """Exécute une requête SQL sécurisée"""
        if not self._is_safe_query(sql):
            return None
        engine = self._get_db_engine()
        if not engine:
            return None
        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                cols = list(result.keys())
                rows = [dict(zip(cols, row)) for row in result.fetchmany(100)]
                return rows
        except Exception as e:
            print(f"⚠️ Erreur SQL: {e}")
            return None

    def _classify_question(self, question: str) -> str:
        """Détermine si la question nécessite des données SQL"""
        q = question.lower()
        data_keywords = [
            'combien', 'production', 'rendement', 'prix', 'météo', 'température',
            'pluie', 'données', 'statistiques', 'moyenne', 'total', 'comparaison',
            'évolution', 'tendance', 'analyse', 'rapport', 'liste', 'montre',
            'affiche', 'donne-moi', 'quelle est la', 'quel est le'
        ]
        return "sql" if any(kw in q for kw in data_keywords) else "general"

    async def process_question(self, question: str, user_id: str = None) -> Dict[str, Any]:
        """Traite une question utilisateur"""
        if not self.llm.available:
            return await self._demo_response(question)

        try:
            question_type = self._classify_question(question)

            # Construire les messages avec historique
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(self.conversation_history[-self.max_history:])
            messages.append({"role": "user", "content": question})

            # Appel LLM
            response_text = await self.llm.chat(messages)

            # Mettre à jour l'historique
            self.conversation_history.append({"role": "user", "content": question})
            self.conversation_history.append({"role": "assistant", "content": response_text})

            # Extraire et exécuter SQL si présent
            sql_query = self._extract_sql(response_text)
            data = None
            if sql_query:
                data = await self._execute_sql(sql_query)

            return {
                "type": "sql_response" if sql_query else "general_response",
                "message": response_text,
                "sql_query": sql_query,
                "data": data,
                "provider": self.llm.model,
                "timestamp": datetime.now().isoformat(),
                "error": False,
            }

        except httpx.HTTPStatusError as e:
            return {
                "type": "error",
                "message": f"Erreur API LLM ({e.response.status_code}): {e.response.text[:200]}",
                "timestamp": datetime.now().isoformat(),
                "error": True,
            }
        except Exception as e:
            return {
                "type": "error",
                "message": f"Désolé, une erreur s'est produite: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "error": True,
            }

    async def _demo_response(self, question: str) -> Dict[str, Any]:
        """Réponses de démonstration sans LLM"""
        q = question.lower()
        if any(w in q for w in ['production', 'rendement', 'maïs', 'riz']):
            msg = "🌾 **Analyse de Production** (mode démo)\n\n• Maïs au Togo: 2.1 t/ha\n• Riz au Ghana: 680 000 tonnes\n• Évolution: +15% vs 2022"
        elif any(w in q for w in ['prix', 'marché']):
            msg = "💰 **Prix du Marché** (mode démo)\n\n• Maïs: 380 USD/t (+5%)\n• Cacao: 2 450 USD/t (-2%)\n• Riz: 420 USD/t (stable)"
        elif any(w in q for w in ['météo', 'pluie', 'température']):
            msg = "🌤️ **Météo** (mode démo)\n\n• Température: 28°C\n• Précipitations: 45mm/semaine\n• Humidité: 75%"
        else:
            msg = (
                f"🤖 **AgriBot - Mode Démo**\n\n"
                f"Je peux analyser: production, prix, météo, prédictions.\n\n"
                f"Votre question: _{question}_\n\n"
                f"⚙️ Configurez une clé OpenRouter dans `.env` pour des réponses personnalisées."
            )
        return {
            "type": "demo_response",
            "message": msg,
            "timestamp": datetime.now().isoformat(),
            "error": False,
        }

    def get_suggested_questions(self) -> List[str]:
        return [
            "Quelle est la production de maïs au Togo cette année ?",
            "Compare les rendements de riz entre le Ghana et le Nigeria",
            "Montre l'évolution des prix du cacao ces 5 dernières années",
            "Quelles sont les prédictions pour la saison des pluies ?",
            "Analyse la corrélation entre précipitations et rendements",
            "Quels pays ont la meilleure productivité agricole ?",
            "Comment les prix du café ont-ils évolué ce mois-ci ?",
            "Donne-moi les alertes actives pour les cultures",
            "Quel est l'impact du changement climatique sur l'agriculture ?",
            "Recommande des stratégies pour optimiser les rendements",
        ]

    def clear_memory(self):
        """Efface l'historique de conversation"""
        self.conversation_history.clear()

    def switch_provider(self, provider: str):
        """Bascule entre kimi et deepseek"""
        self.llm.switch_provider(provider)


# Lazy singleton
_agri_chatbot: Optional[AgriChatbot] = None


def _get_chatbot() -> AgriChatbot:
    global _agri_chatbot
    if _agri_chatbot is None:
        _agri_chatbot = AgriChatbot()
    return _agri_chatbot


async def process_chat_message(message: str, user_id: str = None) -> Dict[str, Any]:
    """Point d'entrée pour traiter les messages du chat"""
    return await _get_chatbot().process_question(message, user_id)


def get_chat_suggestions() -> List[str]:
    """Récupère les questions suggérées"""
    return _get_chatbot().get_suggested_questions()
