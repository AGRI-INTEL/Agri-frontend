"""
AgriIntel360 - Agent IA Agricole Autonome
ReAct loop avec function calling, accès complet DB, analyse d'images, marché, météo
"""

import json
import re
import uuid
import base64
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import httpx
from lxml import html as lxml_html
from sqlalchemy import create_engine, inspect, text
from loguru import logger

from config.config import get_settings

settings = get_settings()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. OUTILS — Définitions & Exécuteurs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "Exécute une requête SQL SELECT sur la base de données agricole. Accès complet à toutes les tables.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "Requête SQL SELECT complète. Utilisez LIMIT pour limiter les résultats."
                    }
                },
                "required": ["sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_database_schema",
            "description": "Récupère le schéma complet de la base de données : toutes les tables, colonnes, types et contraintes.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Recherche dans la base de connaissances agricoles intégrée (cultures, élevage, pêche, forêts, conseils).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termes de recherche (ex: 'arachide Sénégal', 'élevage bovin', 'prix cacao')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Recherche des informations actualisées sur le web (actualités agricoles, prix, météo, politiques agricoles).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termes de recherche (ex: 'prix cacao Côte d\'Ivoire 2026', 'prévision pluie Sénégal juillet')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_dataset",
            "description": "Analyse statistique d'un jeu de données : moyenne, médiane, min, max, tendances, corrélations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Jeu de données à analyser"
                    },
                    "question": {
                        "type": "string",
                        "description": "Question spécifique à laquelle répondre avec l'analyse"
                    }
                },
                "required": ["data", "question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "format_table",
            "description": "Formate des données en tableau structuré pour l'affichage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Données à formater en tableau"
                    },
                    "title": {
                        "type": "string",
                        "description": "Titre du tableau"
                    }
                },
                "required": ["data", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Retourne la date et l'heure actuelles.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
]

TOOLS_WITHOUT_DB = [
    t for t in AVAILABLE_TOOLS
    if t["function"]["name"] not in ("query_database", "get_database_schema")
]


# Mots-clés SQL interdits (destructeurs uniquement)
FORBIDDEN_SQL = {
    'insert', 'update', 'delete', 'drop', 'truncate', 'alter',
    'create', 'exec', 'execute', '--', '/*', '*/', ';',
    'copy', 'pg_sleep', 'pg_read_file', 'vacuum', 'cluster',
    'reindex', 'load', 'do', 'declare', 'grant', 'revoke',
}


def _is_safe_select(sql: str) -> tuple[bool, str]:
    if not sql or not sql.strip():
        return False, "Requête vide"
    cleaned = re.sub(r"'.*?'", '', sql.lower())
    cleaned = re.sub(r'".*?"', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if not cleaned.startswith("select"):
        return False, "Seules les requêtes SELECT sont autorisées"
    for kw in FORBIDDEN_SQL:
        if re.search(r'\b' + re.escape(kw) + r'\b', cleaned):
            return False, f"Mot-clé interdit : {kw}"
    return True, "ok"


def _get_db_engine():
    try:
        sync_url = settings.DATABASE_URL
        if sync_url.startswith("postgresql+asyncpg://"):
            sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        elif sync_url.startswith("postgresql://"):
            sync_url = sync_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return create_engine(sync_url, pool_pre_ping=True)
    except Exception as e:
        logger.warning("DB engine creation failed: {}", e)
        return None


async def _execute_sql(sql: str) -> dict:
    safe, reason = _is_safe_select(sql)
    if not safe:
        return {"ok": False, "error": reason}
    engine = _get_db_engine()
    if not engine:
        return {"ok": False, "error": "Base de données non disponible"}
    try:
        with engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("SET TRANSACTION READ ONLY"))
            result = conn.execute(text(sql))
            cols = list(result.keys())
            rows = [dict(zip(cols, row)) for row in result.fetchmany(200)]
            return {"ok": True, "columns": cols, "rows": rows, "count": len(rows)}
    except Exception as exc:
        return {"ok": False, "error": f"Erreur SQL : {str(exc)[:200]}"}


async def _get_schema() -> dict:
    engine = _get_db_engine()
    if not engine:
        return {"ok": False, "error": "DB non disponible"}
    try:
        inspector = inspect(engine)
        tables = {}
        for table_name in inspector.get_table_names():
            cols = []
            for col in inspector.get_columns(table_name):
                cols.append({
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "default": str(col.get("default", "")),
                    "primary_key": col.get("primary_key", False),
                })
            fks = []
            for fk in inspector.get_foreign_keys(table_name):
                fks.append({
                    "from": fk["constrained_columns"],
                    "to": f"{fk['referred_table']}.{fk['referred_columns']}"
                })
            tables[table_name] = {"columns": cols, "foreign_keys": fks}
        return {"ok": True, "tables": tables}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _format_schema_for_prompt(schema: dict) -> str:
    if not schema.get("ok"):
        return "(schéma indisponible)"
    parts = []
    for tname, tinfo in schema["tables"].items():
        cols = ", ".join(
            f"{c['name']} {c['type']}{' PK' if c['primary_key'] else ''}"
            for c in tinfo["columns"]
        )
        fks = ""
        if tinfo["foreign_keys"]:
            fks = "  ↳ FK: " + "; ".join(
                f"{', '.join(f['from'])} → {f['to']}" for f in tinfo["foreign_keys"]
            )
        parts.append(f"📋 {tname}({cols}){fks}")
    return "\n".join(parts)


_KNOWLEDGE_BASE: Dict[str, str] = {
    'arachide': "🥜 **Arachide** — Culture commerciale clé au Sénégal. Variétés : 55-437, Fleur 11, GH 119-20. Semis fin mai-juin, densité 40 kg/ha, fertilisation 150 kg/ha NPK, cycle 90-120 j, rendement 1-1,5 t/ha gousses.",
    'mil|millet|sorgho|fonio': "🌾 **Céréales sèches** — Mil souna (75-90 j, 800-1200 kg/ha), Sorgho (100-120 j), Fonio (60-90 j). Techniques : labour superficiel, semis en poquets, démariage 2 plants, 2 sarclages.",
    'riz|riziculture': "🌾 **Riz** — Pluvial (Casamance, variétés NERICA 1-18, 2-5 t/ha) et irrigué (vallée du fleuve, 5-8 t/ha). Urée 150 kg/ha en 2 fractions. Appui : SAED, ANCAR.",
    'elevage|betail|bovin|ovin|caprin': "🐄 **Élevage** — 35% PIB agricole. Races : Gobra (zébu), Djakoré (métis), Mouton Peulh-Peulh, chèvre du Sahel. Vaccins : PPCC, fièvre aphteuse. Production lait : 1-3 L/j locales, 5-15 L/j croisées.",
    'peche|poisson|maritime|halieutique': "🐟 **Pêche** — ~400-500 kt/an. Sardinelles, thiof, carpe. Zones : Petite Côte (Mbour, Joal), Saint-Louis, Ziguinchor. Transformation : guedj, kéthiakh.",
    'foret|bois|reboisement|agroforesterie': "🌲 **Forêts** — 8M ha (41% territoire). Essences : vène, caïlcédrat, filao. PFNL : karité, néré/soumbala, baobab. Agroforesterie : Faidherbia albida +30% fertilité.",
    'maraicher|legume|tomate|oignon': "🥕 **Maraîchage** — Zones : Niayes, Thiès. Saison fraîche (oct-jan) : tomate, chou. Saison chaude (fév-mai) : oignon, gombo. Rendement tomate : 20-40 t/ha plein champ, 60-80 t/ha serre.",
    'prix|marche|vente|commercialisation': "💰 **Prix indicatifs** — Arachide décortiquée 325-375 F CFA/kg, Mil 180-220 F CFA/kg, Riz paddy 175-200 F CFA/kg, Tomate 100-300 F CFA/kg, Bovin 250-800k F CFA/tête.",
    'engrais|fertilisant|compost|sol|fertilité': "🌿 **Fertilisation** — Urée 46% 20-25k F CFA/sac 50 kg, NPK 15-15-15 18-22k F CFA/sac. Compost 5-10 t/ha. Associations légumineuse-céréale améliorantes.",
    'irrigation|eau|pompe|goutte-à-goutte': "💧 **Irrigation** — Goutte-à-goutte : économie 50-70% eau, +30% rendement. Forages solaires (PUDC). Coût goutte-à-goutte 1 ha : 800k-1,5M F CFA.",
    'togo|lome|kara': "🇹🇬 **Togo** — Zones : Maritime/Plateaux (manioc, maïs, cacao), Centrale (igname, coton), Kara/Savanes (mil, sorgho, soja). Cacao 10-15 kt/an, Café 5-8 kt/an, Coton 60-80 kt/an. Appui : ICAT, NSCT, ITRA.",
    'ghana|accra|cacao': "🇬🇭 **Ghana** — 2e producteur mondial cacao (700-900 kt/an). Maïs, riz au nord. COCOBOD, MOFA. Prix cacao GHS 800-1200/sac 64 kg.",
    'cote.ivoire|abidjan': "🇨🇮 **Côte d'Ivoire** — 1er producteur cacao (2 Mt/an). Anacarde 900k-1 Mt/an, Caoutchouc 800 kt/an. Vivrier : igname, manioc, riz. CCC fixe le prix cacao.",
    'nigeria|lagos|kano': "🇳🇬 **Nigeria** — 1er producteur manioc (~60 Mt/an), 70% igname mondiale. Sorgho, mil au nord. Cacao, huile de palme au sud. CBN Anchor Borrowers Programme. Pertes post-récolte 30-40%.",
    'sahel|mali|burkina|niger': "🌍 **Sahel** — Mil, sorgho, niébé, sésame, oignon de Galmi. Techniques : zaï, cordons pierreux, RNA. Défis : sécheresse, insécurité, baisse fertilité. Appui : CILSS, FAO, FIDA.",
}


def _search_knowledge(query: str) -> str:
    q = query.lower()
    results = []
    for pattern, content in _KNOWLEDGE_BASE.items():
        if any(kw in q for kw in pattern.split('|')):
            results.append(content)
    if results:
        return "\n\n".join(results)
    return "Aucune information spécifique trouvée dans la base de connaissances pour cette requête."


def _analyze_dataset(data: List[Dict], question: str) -> Dict:
    if not data:
        return {"error": "Jeu de données vide", "summary": "Aucune donnée à analyser."}
    keys = data[0].keys()
    numeric_keys = []
    for k in keys:
        vals = [r[k] for r in data if isinstance(r.get(k), (int, float))]
        if vals:
            numeric_keys.append(k)
    analysis = {}
    for k in numeric_keys:
        vals = [r[k] for r in data if isinstance(r.get(k), (int, float))]
        if vals:
            analysis[k] = {
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "avg": round(sum(vals) / len(vals), 2),
                "count": len(vals),
            }
    return {
        "total_rows": len(data),
        "numeric_columns": analysis,
        "columns": list(keys),
        "question": question,
    }


async def _web_search(query: str) -> dict:
    results = []
    api_keywords = ["definition", "what is", "qu'est-ce", "define", "meaning"]

    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36", "Accept-Language": "fr-FR,fr;q=0.9"}

        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            api_resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                headers=headers,
            )
            if api_resp.status_code == 200:
                data = api_resp.json()
                abstract = (data.get("AbstractText") or "").strip()
                source = (data.get("AbstractSource") or "").strip()
                if abstract:
                    results.append({"title": f"Résumé — {source}" if source else "Résumé", "snippet": abstract, "url": data.get("AbstractURL", "")})

                for topic in (data.get("RelatedTopics") or []):
                    if "Text" in topic:
                        results.append({"title": topic["Text"][:80], "snippet": topic["Text"], "url": topic.get("FirstURL", "")})
                    if "Topics" in topic:
                        for sub in (topic["Topics"] or [])[:3]:
                            if "Text" in sub:
                                results.append({"title": sub["Text"][:80], "snippet": sub["Text"], "url": sub.get("FirstURL", "")})

        if len(results) < 3:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                lite_resp = await client.get("https://lite.duckduckgo.com/lite/", params={"q": query}, headers=headers)
                if lite_resp.status_code == 200:
                    tree = lxml_html.fromstring(lite_resp.content)
                    for row in tree.xpath('//tr[.//td[@class="result-snippet"]]'):
                        cells = row.xpath('./td')
                        if len(cells) >= 2:
                            title = cells[0].text_content().strip()
                            snippet = cells[1].text_content().strip()
                            link_a = cells[0].xpath('.//a')
                            link = link_a[0].get("href", "") if link_a else ""
                            if title and title not in [r["title"] for r in results]:
                                results.append({"title": title, "snippet": snippet[:300], "url": link})

        count = len(results[:8])
        return {"ok": True if count > 0 else False, "results": results[:8], "count": count, "query": query}

    except Exception as e:
        logger.warning("Web search failed: {}", e)
        return {"ok": False, "results": results[:4] if results else [], "count": len(results[:4]), "error": str(e)[:100], "query": query}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. CLIENT LLM (OpenRouter / OpenAI / DeepSeek)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LLMClient:
    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.DEFAULT_LLM_PROVIDER
        self._configure()

    def _configure(self):
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
        elif self.provider == "free" and self.settings.OPENROUTER_API_KEY:
            self.api_key = self.settings.OPENROUTER_API_KEY
            self.base_url = self.settings.OPENROUTER_BASE_URL
            self.model = "google/gemma-4-26b-a4b-it:free"
            self.available = True
        else:
            self.available = False

    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.1,
    ) -> Dict:
        if not self.available:
            raise RuntimeError("LLM non disponible")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter.ai" in self.base_url:
            headers["HTTP-Referer"] = "https://agriintel360.lsgrouptogo.com"
            headers["X-Title"] = "AgriIntel360"

        max_tokens = 400 if "kimi" in self.model or "deepseek" in self.model or "gpt" in self.model else 2000
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]
        except httpx.TimeoutException:
            raise RuntimeError(f"Le modèle {self.model} a mis trop de temps à répondre")
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300]
            if e.response.status_code == 400:
                raise RuntimeError(f"Requête invalide (400) : {body}")
            raise RuntimeError(f"Erreur API ({e.response.status_code}) : {body}")

    def switch_provider(self, provider: str):
        self.provider = provider
        self._configure()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. AGENT — Orchestrateur avec ReAct Loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SYSTEM_PROMPT_BASE = """Tu es AgriBot, agent IA expert en agriculture africaine et analyse de donnees.

OUTILS: query_database(SQL SELECT), get_database_schema, search_knowledge(connaissances agricoles), web_search(actualites/web), analyze_dataset(statistiques), format_table(tableau), get_current_datetime.

REACT: Comprends -> Planifie quels outils et ordre -> Execute un par un -> Synthetise -> Recommande.

FORMAT: titres, sous-titres, tableaux, emojis pertinents, unites(t/ha,F CFA/kg,mm/an). Termine par recommandation actionnable. Si DB vide, propose alternative.

PAYS: Benin, Burkina Faso, Cote d'Ivoire, Ghana, Guinee, Mali, Niger, Nigeria, Senegal, Togo, Cameroun, Ethiopie, Kenya, Ouganda, Rwanda, Tanzanie, Afrique du Sud, RDC.

REGLES: SELECT uniquement. Prefere DB si disponible. Cite sources (DB, connaissance, web). Question complexe = decompose avec outils distincts. Reponds en FRANCAIS. LIMIT 100 sur SELECT non-filtre."""


class AgriBotAgent:
    def __init__(self):
        self.llm = LLMClient()
        self.max_iterations = 15
        self._histories: Dict[str, List[Dict]] = {}

    async def _execute_tool(self, name: str, args: dict) -> str:
        try:
            if name == "query_database":
                result = await _execute_sql(args["sql"])
                return json.dumps(result, default=str, ensure_ascii=False)

            if name == "get_database_schema":
                schema = await _get_schema()
                text = _format_schema_for_prompt(schema)
                return json.dumps({
                    "ok": schema.get("ok", False),
                    "schema_text": text,
                    "error": schema.get("error"),
                }, ensure_ascii=False)

            if name == "search_knowledge":
                result = _search_knowledge(args.get("query", ""))
                return json.dumps({"ok": True, "result": result}, ensure_ascii=False)

            if name == "web_search":
                result = await _web_search(args.get("query", ""))
                return json.dumps(result, ensure_ascii=False)

            if name == "analyze_dataset":
                result = _analyze_dataset(args.get("data", []), args.get("question", ""))
                return json.dumps({"ok": True, "analysis": result}, ensure_ascii=False)

            if name == "format_table":
                return json.dumps({
                    "ok": True,
                    "data": args.get("data", []),
                    "title": args.get("title", ""),
                }, ensure_ascii=False)

            if name == "get_current_datetime":
                now = datetime.now(timezone.utc)
                return json.dumps({
                    "ok": True,
                    "datetime": now.isoformat(),
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M:%S UTC"),
                }, ensure_ascii=False)

            return json.dumps({"ok": False, "error": f"Outil inconnu : {name}"})
        except Exception as e:
            logger.error("Tool {} failed: {}", name, e)
            return json.dumps({"ok": False, "error": str(e)[:200]}, ensure_ascii=False)

    async def _run_react_loop(self, question: str, user_id: str, schema_text: str, schema_ok: bool) -> Dict:
        table_count = schema_text.strip().count("\n- ") if schema_text.strip() else 0
        tables_summary = f"\n\n## 📋 Base de données : {table_count} tables\nUtilise `get_database_schema` pour le schéma complet.\n" if table_count > 0 else ""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT_BASE + tables_summary},
        ]
        history = self._get_history(user_id)
        messages.extend(history)
        messages.append({"role": "user", "content": question})

        for iteration in range(self.max_iterations):
            try:
                tools = AVAILABLE_TOOLS if schema_ok else TOOLS_WITHOUT_DB
                result = await self.llm.chat(messages, tools=tools)

                if "tool_calls" in result and result["tool_calls"]:
                    assistant_msg = {
                        "role": "assistant",
                        "content": result.get("content"),
                        "tool_calls": result["tool_calls"],
                    }
                    messages.append(assistant_msg)
                    for tc in result["tool_calls"]:
                        func = tc.get("function", {})
                        name = func.get("name", "")
                        try:
                            args = json.loads(func.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            args = {}
                        tool_result = await self._execute_tool(name, args)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": tool_result[:600],
                        })

                if len(messages) > 6:
                    keep = [messages[0]] + messages[-5:]
                    messages = keep

                if "content" in result and result["content"] and not result.get("tool_calls"):
                    response_text = result["content"]
                    self._save_to_history(user_id, question, response_text)
                    sql_query = self._extract_sql(response_text)
                    return {
                        "type": "sql_response" if sql_query else "general_response",
                        "message": response_text,
                        "sql_query": sql_query,
                        "data": None,
                        "provider": self.llm.model,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "error": False,
                    }

                if not result.get("content") and not result.get("tool_calls"):
                    return {
                        "type": "error",
                        "message": "❌ Le modèle n'a pas produit de réponse valide. Veuillez réessayer.",
                        "sql_query": None, "data": None,
                        "provider": self.llm.model,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "error": True,
                    }

            except RuntimeError as e:
                logger.warning("LLM iteration error (iteration={}): {}", iteration, e)
                raise

            except Exception as e:
                logger.error("Unexpected error (iteration={}): {}", iteration, e)
                if iteration == 0:
                    raise
                return {
                    "type": "error",
                    "message": f"❌ Erreur inattendue : {str(e)[:120]}",
                    "sql_query": None, "data": None,
                    "provider": self.llm.model,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": True,
                }

        return {
            "type": "general_response",
            "message": "⚠️ L'analyse a atteint la limite d'itérations. Voici les résultats partiels. Posez une question plus spécifique pour approfondir.",
            "sql_query": None, "data": None,
            "provider": self.llm.model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": False,
        }

    async def process(self, question: str, user_id: str = "anonymous", provider: str = None) -> Dict:
        provider_order = ["free", "kimi", "deepseek", "openai"]
        if provider and provider in provider_order:
            idx = provider_order.index(provider)
            provider_order = provider_order[idx:] + provider_order[:idx]
        else:
            provider_order = [self.llm.provider] + [p for p in provider_order if p != self.llm.provider]

        schema = await _get_schema()
        schema_text = _format_schema_for_prompt(schema)
        schema_ok = schema.get("ok", False)

        for prov in provider_order:
            has_key = (
                (prov == "free" and bool(self.llm.settings.OPENROUTER_API_KEY))
                or (prov == "kimi" and bool(self.llm.settings.OPENROUTER_API_KEY))
                or (prov == "deepseek" and bool(self.llm.settings.DEEPSEEK_API_KEY or self.llm.settings.OPENROUTER_API_KEY))
                or (prov == "openai" and bool(self.llm.settings.OPENAI_API_KEY))
            )
            if not has_key:
                continue

            self.llm.switch_provider(prov)
            if not self.llm.available:
                continue

            try:
                return await self._run_react_loop(question, user_id, schema_text, schema_ok)
            except RuntimeError as e:
                logger.warning("Provider {} failed, fallback to next: {}", prov, e)
                continue

        return await _demo_response(question)

    def _extract_sql(self, text: str) -> Optional[str]:
        match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        match = re.search(r'```\s*(SELECT.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _get_history(self, user_id: str) -> List[Dict]:
        if user_id not in self._histories:
            self._histories[user_id] = []
        return self._histories[user_id]

    def _save_to_history(self, user_id: str, question: str, response: str):
        history = self._get_history(user_id)
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": response})
        self._histories[user_id] = history[-20:]

    def switch_provider(self, provider: str, user_id: str = None):
        self.llm.switch_provider(provider)

    def clear_memory(self, user_id: str = None):
        if user_id:
            self._histories.pop(user_id, None)
        else:
            self._histories.clear()


_agent = None


def _get_agent() -> AgriBotAgent:
    global _agent
    if _agent is None:
        _agent = AgriBotAgent()
    return _agent


async def process_chat_message(message: str, user_id: str = "anonymous", provider: str = None) -> Dict:
    return await _get_agent().process(message, user_id, provider)


def get_chat_suggestions() -> List[str]:
    return [
        "Analyse la production agricole du Togo par culture",
        "Compare les prix du maïs au Ghana et au Nigeria",
        "Quelles sont les tendances météo actuelles au Sénégal ?",
        "Donne-moi un rapport complet sur le cacao en Côte d'Ivoire",
        "Quels pays ont la plus forte production de riz ?",
        "Analyse les corrélations entre pluviométrie et rendements",
    ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. MODE DÉMO (fallback sans API key)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _demo_response(question: str) -> Dict:
    q = question.lower()
    now = datetime.now(timezone.utc).isoformat()

    kn = _search_knowledge(q)
    if kn:
        return {"type": "knowledge_response", "message": kn, "version": "v2.20260706", "timestamp": now, "error": False}

    if re.search(r'combien|liste|quels?|affiche|nombre|count|tables?', q):
        try:
            schema = await _get_schema()
            tables = schema.get("tables", {}) or {}
            count = len(tables)
            if re.search(r'pays|country', q):
                try:
                    db = await _execute_sql("SELECT name, code FROM countries ORDER BY name LIMIT 50")
                    if db.get("ok") and db.get("rows"):
                        names = [r["name"] for r in db["rows"] if r]
                        msg = f"🌍 **{len(names)} pays dans la base :**\n" + ", ".join(names)
                        return {"type": "sql_response", "message": msg, "version": "v2.20260706", "timestamp": now, "error": False}
                except Exception:
                    pass
            msg = f"📋 **{count} tables disponibles** dans la base de donnees.\nUtilisez 'liste des tables' pour plus de details."
            return {"type": "sql_response", "message": msg, "version": "v2.20260706", "timestamp": now, "error": False}
        except Exception:
            return {
                "type": "general_response", "message": "ℹ️ Base de donnees accessible (plusieurs tables dont pays, cultures, productions).\nPosez une question plus specifique.", "version": "v2.20260706", "timestamp": now, "error": False,
            }

    responses = {
        'production|rendement|recolte': (
            "📊 **Analyse des donnees de production**\n\n"
            "Rendements moyens observes en Afrique de l'Ouest :\n\n"
            "| Culture | Rendement moyen | Meilleur potentiel |\n"
            "|---------|----------------|--------------------|\n"
            "| Mais | 1,5–2,5 t/ha | 6–8 t/ha |\n"
            "| Riz paddy | 2–4 t/ha | 7–9 t/ha |\n"
            "| Manioc | 8–15 t/ha | 25–40 t/ha |\n"
            "| Igname | 10–15 t/ha | 25–30 t/ha |\n"
            "| Arachide | 0,8–1,5 t/ha | 3–4 t/ha |\n"
            "| Coton fibre | 0,4–0,8 t/ha | 1,5 t/ha |\n"
            "| Cacao | 0,4–0,8 t/ha | 1,5–2 t/ha |\n\n"
            "Recommandation : le gap entre reel et potentiel se comble avec des intrants de qualite, des varietes ameliorees et l'irrigation."
        ),
        'prix|marche|commercialisation|tarif|couter': (
            "💰 **Analyse des marches agricoles**\n\n"
            "Prix indicatifs bord champ (F CFA/kg) :\n\n"
            "| Produit | Prix min | Prix max | Tendance |\n"
            "|---------|----------|----------|----------|\n"
            "| Arachide decortiquee | 325 | 375 | Stable |\n"
            "| Mil | 180 | 220 | Hausse |\n"
            "| Riz paddy | 175 | 200 | Stable |\n"
            "| Tomate fraiche | 100 | 300 | Saisonnier |\n"
            "| Cacao (Cote d'Ivoire) | 1 000 | 1 800 | Hausse |\n\n"
            "Conseil : Rejoignez une cooperative/GIE pour mutualiser la commercialisation et negocier de meilleurs prix."
        ),
        'meteo|pluie|temperature|climat|prevision': (
            "🌦️ **Analyse meteo et climat agricole**\n\n"
            "Zones pluviometriques au Senegal :\n"
            "- Sahelienne (nord) : 200–400 mm/an -> mil, sorgho\n"
            "- Soudanienne (centre) : 400–900 mm/an -> arachide, mais, coton\n"
            "- Soudano-guineenne (sud) : 900–1500 mm/an -> riz, tubercules\n\n"
            "Saison des pluies : juin a octobre (hivernage)\n"
            "Prevision 2026 : risque de demarrage tardif des pluies dans le nord du Senegal.\n\n"
            "Conseil : preparez vos semences et surveillez les bulletins de l'ANACIM."
        ),
        'cote.ivoire|cacao': (
            "🇨🇮 **Analyse filiere cacao en Cote d'Ivoire**\n\n"
            "Production : ~2 000 000 tonnes/an (1er mondial)\n"
            "Prix DPU 2025-2026 : 1 800 F CFA/kg (fixe par le CCC)\n\n"
            "Zones de production majeures :\n"
            "- Sud-Ouest (San Pedro, Soubre) : 45% production\n"
            "- Centre-Ouest (Daloa, Issia) : 30%\n"
            "- Est (Abengourou) : 15%\n\n"
            "Defis : vieillissement des vergers (60% > 15 ans), maladies (swollen shoot, mirides), deforestation et pression reglementaire EUDR.\n\n"
            "Recommandation : investir dans la regeneration des vergers et la certification durable (Rainforest Alliance, Fairtrade)."
        ),
    }
    for pattern, response in responses.items():
        if re.search(pattern, q):
            return {"type": "agricultural_response", "message": response, "version": "v2.20260706", "timestamp": now, "error": False}

    return {
        "type": "general_response",
        "message": (
            "🌾 **AgriBot v2 — Assistant Agricole Autonome**\n\n"
            "Je peux analyser vos donnees agricoles et vous conseiller sur :\n\n"
            "📊 Analyses de donnees - production, rendements, prix\n"
            "🌱 Cultures - arachide, mil, mais, riz, cacao, maraichage\n"
            "🐄 Elevage - bovins, ovins, caprins\n"
            "🐟 Peche - production, transformation\n"
            "🌲 Forets - agroforesterie, PFNL\n"
            "🌦️ Meteo - pluviometrie, calendriers culturaux\n"
            "💰 Marche - prix, commercialisation, tendances\n\n"
            "Posez votre question en francais"
        ),
        "version": "v2.20260706",
        "timestamp": now, "error": False,
    }
