"""
AgriIntel360 - Chatbot IA avec OpenRouter (Kimi / DeepSeek)
Assistant conversationnel pour analyse de données agricoles africaines
"""

import re
import json

import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import create_engine, text
from loguru import logger

from config.config import get_settings

settings = get_settings()

# Tables autorisées pour les requêtes SQL
ALLOWED_TABLES = {
    'countries', 'crops', 'productions', 'weather_data',
    'price_data', 'predictions', 'alerts'
}

ALLOWED_COLUMNS = {
    'countries': {'id', 'name', 'iso_code', 'region', 'gdp', 'population', 'agricultural_land_percent'},
    'crops': {'id', 'name', 'scientific_name', 'category', 'growth_period_days', 'water_requirement'},
    'productions': {'id', 'country_id', 'crop_id', 'year', 'season', 'area_harvested_ha', 'production_tonnes', 'yield_tonnes_per_ha', 'producer_price_usd'},
    'weather_data': {'id', 'country_id', 'date', 'temperature_celsius', 'humidity_percent', 'precipitation_mm', 'wind_speed_kmh'},
    'price_data': {'id', 'country_id', 'crop_id', 'date', 'price_usd_per_kg', 'market_name', 'supply_level', 'demand_level'},
    'predictions': {'id', 'country_id', 'crop_id', 'prediction_type', 'target_date', 'predicted_value', 'confidence_score'},
    'alerts': {'id', 'title', 'message', 'alert_type', 'severity', 'country_id', 'crop_id'},
}

# Mots-clés SQL dangereux — refus absolu
FORBIDDEN_SQL_KEYWORDS = {
    'insert', 'update', 'delete', 'drop', 'truncate', 'alter',
    'create', 'exec', 'execute', 'sp_', 'xp_', '--', '/*', '*/', ';',
    'select into', 'copy', 'pg_sleep', 'pg_read_file',
    'information_schema', 'pg_catalog', 'pg_class', 'pg_proc',
    'vacuum', 'cluster', 'reindex', 'listen', 'notify',
    'unlisten', 'load', 'do', 'declare',
}

ALLOWED_FUNCTIONS = {
    'count', 'sum', 'avg', 'min', 'max', 'coalesce',
    'round', 'floor', 'ceil', 'abs',
    'extract', 'date_trunc', 'cast',
    'concat', 'lower', 'upper', 'trim',
    'now', 'current_date', 'current_timestamp',
}


class SqlValidationError(Enum):
    OK = "ok"
    NOT_SELECT = "not_select"
    FORBIDDEN_KEYWORD = "forbidden_keyword"
    UNKNOWN_TABLE = "unknown_table"
    UNKNOWN_COLUMN = "unknown_column"
    FORBIDDEN_FUNCTION = "forbidden_function"
    SYNTAX_ERROR = "syntax_error"


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
            self.model = "gpt-4o-mini"
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
            "max_tokens": 800,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            raise RuntimeError(f"Le modèle {self.model} a mis trop de temps à répondre")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Erreur API ({e.response.status_code}): {e.response.text[:200]}")

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
                if sync_url.startswith("postgresql+asyncpg://"):
                    sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
                elif sync_url.startswith("postgresql://"):
                    sync_url = sync_url.replace("postgresql://", "postgresql+psycopg2://", 1)
                self._db_engine = create_engine(sync_url, pool_pre_ping=True)
            except Exception as e:
                logger.warning("DB engine creation failed: %s", e)
        return self._db_engine

    def _get_history(self, user_id: str) -> List[Dict[str, str]]:
        user_id = user_id or "anonymous"
        if user_id not in self.user_histories:
            self.user_histories[user_id] = []
        return self.user_histories[user_id]

    def _get_provider(self, user_id: str) -> str:
        user_id = user_id or "anonymous"
        return self.user_providers.get(user_id, self.settings.DEFAULT_LLM_PROVIDER)

    def _is_safe_query(self, sql: str) -> SqlValidationError:
        if not sql or not sql.strip():
            return SqlValidationError.SYNTAX_ERROR
        sql_lower = sql.lower().strip()
        if not sql_lower.startswith("select"):
            return SqlValidationError.NOT_SELECT

        for kw in FORBIDDEN_SQL_KEYWORDS:
            if kw in sql_lower:
                logger.warning("SQL blocked: forbidden keyword '%s' in: %.100s", kw, sql)
                return SqlValidationError.FORBIDDEN_KEYWORD

        from_tables = re.findall(r'\bfrom\s+["\']?(\w+)["\']?', sql_lower)
        join_tables = re.findall(r'\bjoin\s+["\']?(\w+)["\']?', sql_lower)
        all_refs = from_tables + join_tables
        for tbl in all_refs:
            if tbl not in ALLOWED_TABLES:
                logger.warning("SQL blocked: unknown table '%s' in: %.100s", tbl, sql)
                return SqlValidationError.UNKNOWN_TABLE

        func_calls = re.findall(r'(?<=\W)([a-z_]+)\s*\(', sql_lower)
        for func in func_calls:
            if func not in ALLOWED_FUNCTIONS and func not in from_tables and func not in join_tables:
                logger.warning("SQL blocked: forbidden function '%s' in: %.100s", func, sql)
                return SqlValidationError.FORBIDDEN_FUNCTION

        return SqlValidationError.OK

    def _extract_sql(self, text: str) -> Optional[str]:
        match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if not match:
            match = re.search(r'```\s*(SELECT.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else None

    async def _execute_sql(self, sql: str) -> Optional[List[Dict]]:
        validation = self._is_safe_query(sql)
        if validation != SqlValidationError.OK:
            logger.warning("SQL execution blocked (validation=%s)", validation.value)
            return None
        engine = self._get_db_engine()
        if not engine:
            return None
        try:
            with engine.connect() as conn:
                conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text("SET TRANSACTION READ ONLY"))
                result = conn.execute(text(sql))
                cols = list(result.keys())
                return [dict(zip(cols, row)) for row in result.fetchmany(100)]
        except Exception as exc:
            logger.warning("SQL execution failed: %s", exc)
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

        except RuntimeError as e:
            logger.warning(f"LLM unavailable: {e}")
            return await self._demo_response(question)

        except Exception as e:
            logger.warning(f"LLM error: {e}")
            return {
                "type": "error",
                "message": (
                    f"❌ **Erreur de connexion au modèle IA**\n\n"
                    f"Le fournisseur **{self.llm.provider}** ({self.llm.model}) n'a pas pu répondre.\n\n"
                    f"**Causes possibles :**\n"
                    f"- Clé API invalide ou expirée\n"
                    f"- Service temporairement indisponible\n"
                    f"- Quota de requêtes dépassé\n\n"
                    f"**Solutions :**\n"
                    f"- Vérifiez la configuration dans le fichier `.env`\n"
                    f"- Essayez un autre fournisseur (DeepSeek, OpenAI)\n"
                    f"- Réessayez dans quelques instants\n\n"
                    f"> Détail technique : `{str(e)[:120]}`"
                ),
                "sql_query": None,
                "data": None,
                "provider": self.llm.model,
                "timestamp": datetime.now().isoformat(),
                "error": True,
            }

    async def _demo_response(self, question: str) -> Dict[str, Any]:
        """Mode démo avec réponses agricoles intelligentes basées sur les mots-clés."""
        q = question.lower()

        # Topic detection
        responses: Dict[str, str] = {
            'meteo|pluie|pluviometrie|temperature|climat|saison|seche|humidite': (
                "🌦️ **Météo & Climat Agricole**\n\n"
                "La pluviométrie au Sénégal varie selon les zones :\n"
                "- **Zone Sahélienne (nord)** : 200–400 mm/an — cultures de mil, sorgho résistants\n"
                "- **Zone Soudanienne (centre)** : 400–900 mm/an — arachide, maïs, coton\n"
                "- **Zone Soudano-guinéenne (sud/Casamance)** : 900–1500 mm/an — riz, tubercules\n\n"
                "**Saison des pluies** : juin à octobre (hivernage)\n"
                "**Conseil** : Préparez vos semences avant les premières pluies. Consultez les prévisions de l'ANACIM pour planifier vos semis."
            ),
            'arachide|groundnut': (
                "🥜 **Culture de l'Arachide**\n\n"
                "L'arachide est la principale culture commerciale du Sénégal (bassin arachidier).\n\n"
                "**Variétés recommandées** : 55-437, Fleur 11, GH 119-20\n"
                "**Semis** : Fin mai à mi-juin (avec les premières pluies)\n"
                "**Densité** : 40 kg/ha de semences, espacement 40×15 cm\n"
                "**Fertilisation** : 150 kg/ha de 6-20-10 au semis\n"
                "**Récolte** : 90–120 jours après semis\n"
                "**Rendement moyen** : 1–1,5 t/ha (gousses)"
            ),
            'mil|millet|sorgho|fonio': (
                "🌾 **Céréales Sèches (Mil, Sorgho, Fonio)**\n\n"
                "Cultures de base pour la sécurité alimentaire en zones semi-arides.\n\n"
                "**Mil souna** : Semis juin–juillet, cycle 75–90 jours, rendement 800–1200 kg/ha\n"
                "**Sorgho** : Plus tardif, cycle 100–120 jours, meilleure tolérance à la sécheresse\n"
                "**Fonio** : Culture des zones dégradées, cycle 60–90 jours\n\n"
                "**Itinéraire technique** :\n"
                "1. Labour ou grattage superficiel avant les pluies\n"
                "2. Semis en poquets (3–5 graines/poquet, 80×80 cm)\n"
                "3. Démariage à 2–3 plants/poquet à 2 semaines\n"
                "4. Sarclage × 2 (J+15 et J+30)"
            ),
            'riz|riziculture|paddy': (
                "🌾 **Riziculture**\n\n"
                "Le riz est cultivé principalement en Casamance, vallée du fleuve Sénégal et Bassin du Sine-Saloum.\n\n"
                "**Systèmes de culture** :\n"
                "- Riz pluvial (upland) : Casamance — variétés CNA 1, DJ 11-509\n"
                "- Riz irrigué : vallée du fleuve — 2 campagnes/an possibles\n\n"
                "**Rendements** : 2–5 t/ha (pluvial) / 5–8 t/ha (irrigué)\n"
                "**Intrants** : Urée 150 kg/ha en 2 fractions (tallage + montaison)\n"
                "**Organismes d'appui** : SAED (vallée du fleuve), ANCAR"
            ),
            'elevage|betail|bovin|ovin|caprin|mouton|vache|chevre': (
                "🐄 **Élevage au Sénégal**\n\n"
                "L'élevage représente 35% du PIB agricole.\n\n"
                "**Races locales** :\n"
                "- Bovins : Gobra (zébu peulh), Djakoré (métissé)\n"
                "- Ovins : Mouton Peulh-Peulh (lait), Touabire (viande)\n"
                "- Caprins : chèvre du Sahel\n\n"
                "**Alimentation** : Résidus de récolte + paille + blocs minéraux\n"
                "**Vaccination** : PPCC, fièvre aphteuse, pasteurellose (DIREL)\n"
                "**Production laitière** : 1–3 L/j (vaches locales), 5–15 L/j (croisées)\n"
                "**Marchés** : Dakar, Thiès, Kaolack, Ziguinchor"
            ),
            'peche|poisson|pirogue|maritime|halieutique': (
                "🐟 **Pêche & Ressources Halieutiques**\n\n"
                "Le Sénégal est l'un des premiers pays africains en termes de production halieutique.\n\n"
                "**Production** : ~400 000–500 000 tonnes/an (artisanale + industrielle)\n"
                "**Espèces principales** : Sardinelles, thiof (mérou), carpe blanche, crevettes\n\n"
                "**Zones de pêche** :\n"
                "- Petite Côte (Mbour, Joal) : pêche artisanale intensive\n"
                "- Saint-Louis : pêche côtière et estuarienne\n"
                "- Ziguinchor : pêche en Casamance\n\n"
                "**Transformation** : Guedj (poisson fermenté), kéthiakh, yeet\n"
                "**Réglementation** : DPM — licences de pêche obligatoires"
            ),
            'foret|bois|timber|reboisement|agroforesterie': (
                "🌲 **Foresterie & Agroforesterie**\n\n"
                "Les forêts sénégalaises couvrent ~8 millions d'ha (41% du territoire).\n\n"
                "**Essences exploitées** :\n"
                "- Vène (Pterocarpus erinaceus) : bois précieux\n"
                "- Caïlcédrat : construction\n"
                "- Filao : reboisement côtier\n\n"
                "**PFNL (Produits Forestiers Non Ligneux)** :\n"
                "- Karité (beurre), néré (soumbala), baobab (pain de singe, huile)\n"
                "- Ditax, rônier, palmier\n\n"
                "**Agroforesterie** : Association cultures + Faidherbia albida (kad)\n"
                "Améliore la fertilité des sols de +30% (azote atmosphérique)\n"
                "**Gestion** : Eaux & Forêts — permis d'exploitation requis"
            ),
            'maraicher|legume|tomate|oignon|haricot|gombo|salade': (
                "🥕 **Maraîchage**\n\n"
                "Le maraîchage est en plein essor avec la demande urbaine croissante.\n\n"
                "**Zones principales** : Niayes (Dakar–Saint-Louis), Thiès, vallée du fleuve\n\n"
                "**Calendrier cultural** :\n"
                "- Saison fraîche (oct–jan) : tomate, chou, carotte, poivron\n"
                "- Saison chaude (fév–mai) : oignon, gombo, haricot vert\n\n"
                "**Contraintes** :\n"
                "- Eau : systèmes goutte-à-goutte recommandés (économie 40–60%)\n"
                "- Ravageurs : mouche blanche, thrips, noctuelle — IPM\n"
                "- Marchés : écoulement difficile en période d'abondance\n\n"
                "**Rendements tomate** : 20–40 t/ha (plein champ), 60–80 t/ha (serre)"
            ),
            'prix|marche|vente|commercialisation|export': (
                "💰 **Marchés & Commercialisation Agricole**\n\n"
                "**Prix indicatifs 2025–2026** :\n"
                "- Arachide décortiquée : 325–375 F CFA/kg (bord champ)\n"
                "- Mil : 180–220 F CFA/kg\n"
                "- Riz paddy irrigué : 175–200 F CFA/kg\n"
                "- Tomate fraîche : 100–300 F CFA/kg (saisonnière)\n"
                "- Bétail (bovin) : 250 000–800 000 F CFA/tête\n\n"
                "**Systèmes de commercialisation** :\n"
                "- GIE & coopératives : meilleur pouvoir de négociation\n"
                "- Marchés hebdomadaires (loumas)\n"
                "- Commerce transfrontalier (Gambie, Guinée, Mali)\n\n"
                "**Appui** : CNCAS (crédit agricole), FONGS, ASPRODEB"
            ),
            'engrais|fertilisant|compost|sol|fertilite': (
                "🌿 **Fertilisation & Gestion de la Fertilité des Sols**\n\n"
                "La fertilité des sols sénégalais est en baisse constante (surexploitation).\n\n"
                "**Types d'engrais disponibles** :\n"
                "- Urée 46% : 20 000–25 000 F CFA/sac 50 kg\n"
                "- NPK 15-15-15 : 18 000–22 000 F CFA/sac 50 kg\n"
                "- Phosphate naturel de Thiès : amendement basique\n\n"
                "**Pratiques améliorantes** :\n"
                "- Compostage (résidus + fumier) : 5–10 t/ha\n"
                "- Jachère améliorée (Crotalaria, Mucuna)\n"
                "- Association légumineuse-céréale (arachide + mil)\n\n"
                "**Programme PRACAS** : subvention engrais via ANCAR"
            ),
            'irrigation|eau|pompe|goutteur': (
                "💧 **Irrigation & Gestion de l'Eau**\n\n"
                "L'irrigation est cruciale pour la double campagne et la saison sèche.\n\n"
                "**Systèmes** :\n"
                "- Goutte-à-goutte : économie 50–70% eau, rendements +30%\n"
                "- Aspersion : maraîchage en plein champ\n"
                "- Gravitaire : riziculture irriguée (vallée fleuve)\n\n"
                "**Sources d'eau** :\n"
                "- Forages solaires (PUDC, PNUD)\n"
                "- Retenues collinaires (eaux pluviales)\n"
                "- Fleuve Volta (Ghana), Mono (Togo/Bénin), Niger, Sénégal\n\n"
                "**Coût moyen** : système goutte-à-goutte 1 ha ≈ 800 000–1 500 000 F CFA"
            ),
            'togo|lome|kara|sokode|atakpame|plateaux|savanes': (
                "🇹🇬 **Agriculture au Togo**\n\n"
                "Le Togo dispose de 5 zones agro-écologiques, du littoral (sud) aux savanes (nord).\n\n"
                "**Cultures principales par région** :\n"
                "- Maritime/Plateaux : manioc, maïs, palmier à huile, café, cacao\n"
                "- Centrale : igname, sorgho, coton\n"
                "- Kara/Savanes : mil, sorgho, soja, sésame\n\n"
                "**Principales filières** :\n"
                "- Cacao : 10 000–15 000 t/an (Kloto, Akebou)\n"
                "- Café robusta : 5 000–8 000 t/an (région des Plateaux)\n"
                "- Coton : 60 000–80 000 t/an (nord du pays — NSCT)\n"
                "- Soja : en forte croissance à l'export\n\n"
                "**Organismes d'appui** : ICAT (conseil agricole), NSCT (coton), ITRA (recherche)\n"
                "**Marchés** : Lomé (port), Kara, Sokodé, Atakpamé"
            ),
            'ghana|accra|kumasi|cacao|cocoa': (
                "🇬🇭 **Agriculture au Ghana**\n\n"
                "Le Ghana est le 2e producteur mondial de cacao.\n\n"
                "**Filières phares** :\n"
                "- Cacao : 700 000–900 000 t/an (Ashanti, Western, Brong-Ahafo)\n"
                "- Maïs : culture vivrière principale du nord\n"
                "- Riz : croissance forte (plaines inondables du nord)\n"
                "- Ananas, mangue, banane plantain : export\n\n"
                "**Organismes clés** : COCOBOD (cacao), MOFA, CSIR-SARI\n"
                "**Prix cacao bord champ** : GHS 800–1 200/sac 64 kg (LBC agréés)\n"
                "**Zones** : Brong-Ahafo, Eastern, Volta, Upper West/East"
            ),
            'nigeria|lagos|kano|abuja|north|nord': (
                "🇳🇬 **Agriculture au Nigeria**\n\n"
                "Le Nigeria est la 1ère économie agricole d'Afrique subsaharienne.\n\n"
                "**Cultures majeures** :\n"
                "- Manioc : 1er producteur mondial (~60 Mt/an)\n"
                "- Igname : 70% de la production mondiale\n"
                "- Sorgho, mil, maïs : ceinture nord (Kano, Katsina, Sokoto)\n"
                "- Cacao, huile de palme, caoutchouc : sud (Ondo, Cross River)\n\n"
                "**Défis** : importation de blé/riz, pertes post-récolte 30–40%\n"
                "**Politique** : Anchor Borrowers Programme (CBN), AFEX commodities exchange\n"
                "**Monnaie** : naira (NGN) — prix soumis à forte volatilité"
            ),
            'mali|burkina|niger|sahel|sec': (
                "🌍 **Sahel — Mali, Burkina Faso, Niger**\n\n"
                "Zone semi-aride à forte vulnérabilité climatique.\n\n"
                "**Cultures adaptées** :\n"
                "- Mil pénicillaire, sorgho, fonio (résistance sécheresse)\n"
                "- Niébé (cowpea) : protéines + fixation azote\n"
                "- Sésame : export en hausse (Burkina, Mali)\n"
                "- Oignon de Galmi (Niger) : export sous-régional\n\n"
                "**Défis majeurs** :\n"
                "- Sécheresses récurrentes et avancée du désert\n"
                "- Crises de sécurité (accès aux zones rurales)\n"
                "- Fertilité des sols en baisse\n\n"
                "**Techniques** : zaï (trous de plantation), cordons pierreux, RNA (régénération naturelle assistée)\n"
                "**Appui** : CILSS, FAO, FIDA, projets PASAL/PASAOP"
            ),
            "cote.?d.?ivoire|abidjan|ivoiri": (
                "🇨🇮 **Agriculture en Côte d'Ivoire**\n\n"
                "1er producteur mondial de cacao (2 Mt/an) et leader régional des cultures d'exportation.\n\n"
                "**Filières d'exportation** :\n"
                "- Cacao : 2 000 000 t/an (CCC — Conseil Café-Cacao)\n"
                "- Anacarde (cajou) : 900 000–1 000 000 t/an\n"
                "- Caoutchouc : 800 000 t/an\n"
                "- Palmier à huile, banane d'export\n\n"
                "**Cultures vivrières** : igname, manioc, plantain, riz, maïs\n"
                "**Zones** : Bas-Sassandra (hévéa), Yamoussoukro (centre), Man (café/cacao ouest)\n"
                "**Prix cacao (DPU)** : fixé par le CCC chaque campagne (oct–sept)"
            ),
            'production|rendement|hectare|tonne|recolte|campagne': (
                "📊 **Données de Production Agricole**\n\n"
                "Voici les rendements moyens pour les principales cultures africaines :\n\n"
                "| Culture | Rendement moyen | Meilleur potentiel |\n"
                "|---------|----------------|--------------------|\n"
                "| Maïs | 1,5–2,5 t/ha | 6–8 t/ha (irrigué) |\n"
                "| Riz paddy | 2–4 t/ha | 7–9 t/ha (irrigué) |\n"
                "| Manioc | 8–15 t/ha | 25–40 t/ha |\n"
                "| Igname | 10–15 t/ha | 25–30 t/ha |\n"
                "| Arachide | 0,8–1,5 t/ha | 3–4 t/ha |\n"
                "| Coton fibre | 0,4–0,8 t/ha | 1,5 t/ha |\n"
                "| Cacao | 0,4–0,8 t/ha | 1,5–2 t/ha |\n\n"
                "Le gap entre rendements réels et potentiels est comblable par :\n"
                "intrants de qualité, variétés améliorées, irrigation, et bonnes pratiques culturales."
            ),
            'semence|graine|variete|amelioree|certifiee': (
                "🌱 **Semences & Variétés Améliorées**\n\n"
                "L'accès aux semences certifiées est un levier majeur de productivité.\n\n"
                "**Variétés recommandées par culture** :\n"
                "- Maïs : EVDT-97, Pool 16 DT, Obatanpa, SWAN1 (tolérant sécheresse)\n"
                "- Riz : NERICA 1–18 (upland), IR64, Sahel 108 (irrigué)\n"
                "- Sorgho : IRAT 204, Seredo, CSM 63-E\n"
                "- Niébé : IT99K-573-1-1, Yacine, Mouride\n"
                "- Arachide : Fleur 11, 55-437, ICGV 86015\n\n"
                "**Sources** : ISRA (Sénégal), IITA (Nigeria/pan-africain), ADRAO/AfricaRice, ITRA (Togo)\n"
                "**Conseil** : Toujours utiliser des semences R1 ou R2 certifiées pour un bon taux de germination (>85%)"
            ),
        }

        for pattern, response in responses.items():
            if re.search(pattern, q):
                return {
                    "type": "agricultural_response",
                    "message": response,
                    "timestamp": datetime.now().isoformat(),
                    "error": False,
                }

        # Générale si aucun topic détecté
        general = (
            "🌾 **AgriBot — Assistant Agricole AgriIntel360**\n\n"
            "Je peux vous renseigner sur :\n\n"
            "🌱 **Cultures** : arachide, mil, sorgho, riz, maïs, maraîchage\n"
            "🐄 **Élevage** : bovins, ovins, caprins, volailles\n"
            "🐟 **Pêche** : zones, techniques, transformation\n"
            "🌲 **Forêts** : exploitation, PFNL, agroforesterie\n"
            "💧 **Irrigation** : systèmes, coûts, sources d'eau\n"
            "🌦️ **Météo** : calendriers culturaux, pluviométrie\n"
            "💰 **Marchés** : prix, commercialisation\n"
            "🌿 **Intrants** : engrais, semences, pesticides\n\n"
            f"Posez votre question en français ou en anglais.\n"
            f"> *Votre question : « {question} »*"
        )
        return {
            "type": "general_response",
            "message": general,
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
