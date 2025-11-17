"""
AgriIntel360 - Chatbot IA avec LangChain
Assistant conversationnel pour requêtes SQL automatiques et analyse de données agricoles
"""

import os
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from langchain_community.llms import OpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.schema import BaseOutputParser, OutputParserException
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferWindowMemory
from langchain.agents import AgentType, initialize_agent, Tool
from langchain.sql_database import SQLDatabase

# Make langchain_experimental import optional
try:
    from langchain_experimental.sql import SQLDatabaseChain
    LANGCHAIN_EXPERIMENTAL_AVAILABLE = True
except ImportError:
    LANGCHAIN_EXPERIMENTAL_AVAILABLE = False
    SQLDatabaseChain = None

import sqlalchemy
from sqlalchemy import create_engine, text

from config.config import get_settings
from config.database import get_db

settings = get_settings()


class SQLQueryParser(BaseOutputParser):
    """Parser pour extraire les requêtes SQL du texte généré"""
    
    def parse(self, text: str) -> Dict[str, Any]:
        """Parse la réponse du LLM pour extraire la requête SQL et l'explication"""
        
        # Extraction de la requête SQL
        sql_match = re.search(r'```sql\n(.*?)\n```', text, re.DOTALL | re.IGNORECASE)
        if not sql_match:
            sql_match = re.search(r'```\n(SELECT.*?)\n```', text, re.DOTALL | re.IGNORECASE)
        
        sql_query = sql_match.group(1).strip() if sql_match else None
        
        # Extraction de l'explication
        explanation_parts = text.split('```')
        explanation = explanation_parts[0].strip() if explanation_parts else text.strip()
        
        return {
            'sql_query': sql_query,
            'explanation': explanation,
            'full_response': text
        }


class AgriChatbot:
    """Chatbot IA spécialisé pour l'agriculture"""
    
    def __init__(self):
        self.settings = get_settings()
        
        # Configuration LLM
        if self.settings.OPENAI_API_KEY:
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=0.1,
                openai_api_key=self.settings.OPENAI_API_KEY,
                max_tokens=1000
            )
        else:
            # Mode démo sans OpenAI
            self.llm = None
            print("⚠️ Pas de clé OpenAI - Mode démo activé")
        
        # Base de données
        self.db_engine = create_engine(self.settings.database_url_async.replace('+asyncpg', ''))
        self.sql_database = SQLDatabase(self.db_engine)
        
        # Mémoire conversationnelle
        self.memory = ConversationBufferWindowMemory(
            k=5,  # Garder 5 derniers échanges
            return_messages=True,
            memory_key="chat_history"
        )
        
        # Schema de base de données pour le contexte
        self.db_schema = self._get_database_schema()
        
        # Prompt système
        self.system_prompt = self._create_system_prompt()
        
        # Parser de sortie
        self.output_parser = SQLQueryParser()
        
        # Initialisation des chaînes
        self._initialize_chains()
    
    def _get_database_schema(self) -> str:
        """Récupère le schéma de la base de données"""
        schema_info = []
        
        try:
            # Tables principales et leurs colonnes
            tables_info = {
                'countries': 'Pays avec informations géographiques et économiques (name, iso_code, region, gdp, population, agricultural_land_percent)',
                'crops': 'Types de cultures (name, scientific_name, category, growth_period_days, water_requirement)',
                'productions': 'Données de production agricole (country_id, crop_id, year, season, area_harvested_ha, production_tonnes, yield_tonnes_per_ha, producer_price_usd)',
                'weather_data': 'Données météorologiques (country_id, date, temperature_celsius, humidity_percent, precipitation_mm, wind_speed_kmh)',
                'price_data': 'Prix des cultures (country_id, crop_id, date, price_usd_per_kg, market_name, supply_level, demand_level)',
                'predictions': 'Prédictions IA (country_id, crop_id, prediction_type, target_date, predicted_value, confidence_score)',
                'alerts': 'Alertes système (title, message, alert_type, severity, country_id, crop_id)'
            }
            
            for table, description in tables_info.items():
                schema_info.append(f"- {table}: {description}")
            
            return "\n".join(schema_info)
            
        except Exception as e:
            return "Schéma de base de données non disponible"
    
    def _create_system_prompt(self) -> str:
        """Crée le prompt système pour le chatbot"""
        return f"""Tu es AgriBot, un assistant IA expert en agriculture africaine et en analyse de données. 
Tu aides les utilisateurs à analyser leurs données agricoles en générant des requêtes SQL et en fournissant des insights.

CONTEXTE DE LA BASE DE DONNÉES:
{self.db_schema}

RÈGLES IMPORTANTES:
1. Génère UNIQUEMENT des requêtes SELECT (pas d'INSERT, UPDATE, DELETE)
2. Utilise des JOINtures appropriées entre les tables
3. Formate toujours tes requêtes SQL entre ```sql et ```
4. Fournis une explication claire avant la requête
5. Limite les résultats avec LIMIT quand approprié
6. Utilise des alias pour les noms de colonnes complexes

EXEMPLES DE PAYS AFRICAINS: Togo (TG), Ghana (GH), Nigeria (NG), Côte d'Ivoire (CI), Burkina Faso (BF)
EXEMPLES DE CULTURES: Maïs, Riz, Manioc, Igname, Cacao, Café, Coton, Arachide

STYLE DE RÉPONSE:
- Sois professionnel mais accessible
- Explique le contexte agricole quand pertinent  
- Suggère des insights supplémentaires
- Utilise des emoji pertinents (🌾, 📊, 🌍, etc.)"""
    
    def _initialize_chains(self):
        """Initialise les chaînes LangChain"""
        if not self.llm or not LANGCHAIN_EXPERIMENTAL_AVAILABLE:
            return
        
        # Chaîne SQL
        self.sql_chain = SQLDatabaseChain.from_llm(
            llm=self.llm,
            db=self.sql_database,
            verbose=False,
            return_intermediate_steps=True
        )
        
        # Prompt pour requêtes générales
        self.chat_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(self.system_prompt),
            HumanMessagePromptTemplate.from_template("{question}")
        ])
        
        # Chaîne de conversation
        self.conversation_chain = LLMChain(
            llm=self.llm,
            prompt=self.chat_prompt,
            memory=self.memory,
            verbose=False
        )
    
    async def process_question(self, question: str, user_id: str = None) -> Dict[str, Any]:
        """Traite une question de l'utilisateur"""
        
        try:
            # Mode démo sans OpenAI
            if not self.llm:
                return await self._demo_response(question)
            
            # Détection du type de question
            question_type = self._classify_question(question)
            
            if question_type == "sql_query":
                return await self._handle_sql_question(question)
            elif question_type == "general":
                return await self._handle_general_question(question)
            else:
                return await self._handle_chat(question)
                
        except Exception as e:
            return {
                'type': 'error',
                'message': f"Désolé, j'ai rencontré une erreur: {str(e)}",
                'timestamp': datetime.now(),
                'error': True
            }
    
    def _classify_question(self, question: str) -> str:
        """Classifie le type de question"""
        question_lower = question.lower()
        
        # Mots-clés pour requêtes de données
        data_keywords = [
            'combien', 'production', 'rendement', 'prix', 'météo', 'température',
            'pluie', 'données', 'statistiques', 'moyenne', 'total', 'comparaison',
            'évolution', 'tendance', 'analyse', 'rapport'
        ]
        
        # Mots-clés pour questions générales
        general_keywords = [
            'qu\'est-ce que', 'comment', 'pourquoi', 'conseil', 'recommandation',
            'expliquer', 'définir', 'avantage', 'inconvénient'
        ]
        
        if any(keyword in question_lower for keyword in data_keywords):
            return "sql_query"
        elif any(keyword in question_lower for keyword in general_keywords):
            return "general"
        else:
            return "chat"
    
    async def _handle_sql_question(self, question: str) -> Dict[str, Any]:
        """Traite les questions nécessitant des requêtes SQL"""
        
        try:
            # Génération de la réponse avec requête SQL
            response = self.conversation_chain.run(question=question)
            parsed = self.output_parser.parse(response)
            
            # Exécution de la requête si elle existe
            data = None
            if parsed['sql_query']:
                data = await self._execute_sql_query(parsed['sql_query'])
            
            return {
                'type': 'sql_response',
                'message': parsed['explanation'],
                'sql_query': parsed['sql_query'],
                'data': data,
                'timestamp': datetime.now(),
                'error': False
            }
            
        except Exception as e:
            return {
                'type': 'error',
                'message': f"Erreur lors du traitement de la requête: {str(e)}",
                'timestamp': datetime.now(),
                'error': True
            }
    
    async def _handle_general_question(self, question: str) -> Dict[str, Any]:
        """Traite les questions générales sur l'agriculture"""
        
        try:
            response = self.conversation_chain.run(question=question)
            
            return {
                'type': 'general_response',
                'message': response,
                'timestamp': datetime.now(),
                'error': False
            }
            
        except Exception as e:
            return {
                'type': 'error',
                'message': f"Erreur lors du traitement: {str(e)}",
                'timestamp': datetime.now(),
                'error': True
            }
    
    async def _handle_chat(self, question: str) -> Dict[str, Any]:
        """Traite les questions de chat général"""
        
        try:
            response = self.conversation_chain.run(question=question)
            
            return {
                'type': 'chat_response',
                'message': response,
                'timestamp': datetime.now(),
                'error': False
            }
            
        except Exception as e:
            return {
                'type': 'error',
                'message': f"Erreur lors du chat: {str(e)}",
                'timestamp': datetime.now(),
                'error': True
            }
    
    async def _execute_sql_query(self, sql_query: str) -> Optional[List[Dict]]:
        """Exécute une requête SQL de manière sécurisée"""
        
        try:
            # Validation de sécurité basique
            if not self._is_safe_query(sql_query):
                raise Exception("Requête non autorisée")
            
            # Exécution de la requête
            with self.db_engine.connect() as connection:
                result = connection.execute(text(sql_query))
                
                # Conversion en liste de dictionnaires
                columns = result.keys()
                data = [dict(zip(columns, row)) for row in result.fetchall()]
                
                # Limitation du nombre de résultats
                return data[:100]  # Max 100 résultats
                
        except Exception as e:
            print(f"Erreur SQL: {e}")
            return None
    
    def _is_safe_query(self, sql_query: str) -> bool:
        """Vérifie si une requête SQL est sécurisée"""
        
        try:
            parser = Parser(sql_query)
        except Exception:
            return False # Invalid SQL

        # 1. Must be a SELECT statement
        if not parser.query_type == 'SELECT':
            return False

        # 2. No write operations or DDL
        if parser.is_ddl or parser.is_dml:
            return False

        # 3. Check for allowed tables
        if not set(parser.tables).issubset(ALLOWED_TABLES):
            return False

        # 4. Check for potentially harmful functions or keywords
        sql_lower = sql_query.lower()
        forbidden_keywords = [
            'exec', 'execute', 'sp_', 'xp_', '--', '/*', '*/', ';'
        ]
        for keyword in forbidden_keywords:
            if keyword in sql_lower:
                return False

        return True
    
    async def _demo_response(self, question: str) -> Dict[str, Any]:
        """Réponses de démonstration quand OpenAI n'est pas disponible"""
        
        question_lower = question.lower()
        
        # Réponses prédéfinies pour la démo
        if any(word in question_lower for word in ['production', 'rendement', 'mais', 'riz']):
            return {
                'type': 'demo_response',
                'message': "🌾 **Analyse de Production Agricole**\n\nSelon nos données, voici les tendances de production:\n\n• **Maïs au Togo**: Rendement moyen de 2.1 tonnes/ha\n• **Riz au Ghana**: Production de 680,000 tonnes en 2023\n• **Évolution**: +15% par rapport à 2022\n\n*Note: Ceci est une réponse de démonstration. Configurez votre clé OpenAI pour des analyses personnalisées.*",
                'demo_data': [
                    {'pays': 'Togo', 'culture': 'Maïs', 'rendement': 2.1, 'année': 2023},
                    {'pays': 'Ghana', 'culture': 'Riz', 'production': 680000, 'année': 2023}
                ],
                'timestamp': datetime.now(),
                'error': False
            }
        
        elif any(word in question_lower for word in ['prix', 'marché', 'coût']):
            return {
                'type': 'demo_response',
                'message': "💰 **Analyse des Prix**\n\nTendances des prix actuelles:\n\n• **Maïs**: 380 USD/tonne (+5% ce mois)\n• **Cacao**: 2,450 USD/tonne (-2% ce mois)\n• **Riz**: 420 USD/tonne (stable)\n\n*Données simulées pour la démonstration.*",
                'demo_data': [
                    {'culture': 'Maïs', 'prix': 380, 'évolution': '+5%'},
                    {'culture': 'Cacao', 'prix': 2450, 'évolution': '-2%'},
                    {'culture': 'Riz', 'prix': 420, 'évolution': 'stable'}
                ],
                'timestamp': datetime.now(),
                'error': False
            }
        
        elif any(word in question_lower for word in ['météo', 'climat', 'pluie', 'température']):
            return {
                'type': 'demo_response',
                'message': "🌤️ **Conditions Météorologiques**\n\nSituation climatique actuelle:\n\n• **Température moyenne**: 28°C\n• **Précipitations**: 45mm cette semaine\n• **Humidité**: 75%\n• **Prévision**: Conditions favorables pour les cultures\n\n*Données météo de démonstration.*",
                'demo_data': [
                    {'indicateur': 'Température', 'valeur': '28°C'},
                    {'indicateur': 'Précipitations', 'valeur': '45mm'},
                    {'indicateur': 'Humidité', 'valeur': '75%'}
                ],
                'timestamp': datetime.now(),
                'error': False
            }
        
        else:
            return {
                'type': 'demo_response',
                'message': f"🤖 **AgriBot - Mode Démonstration**\n\nJe suis votre assistant IA pour l'agriculture africaine. Je peux vous aider avec:\n\n• 📊 Analyses de production et rendements\n• 💰 Tendances des prix et marchés  \n• 🌤️ Données météorologiques\n• 🔮 Prédictions agricoles\n• 📈 Rapports personnalisés\n\n**Votre question**: {question}\n\n*Pour des analyses personnalisées avec vos données, configurez votre clé OpenAI dans les paramètres.*",
                'timestamp': datetime.now(),
                'error': False
            }
    
    def get_suggested_questions(self) -> List[str]:
        """Retourne une liste de questions suggérées"""
        return [
            "Quelle est la production de maïs au Togo cette année ?",
            "Compare les rendements de riz entre le Ghana et le Nigeria",
            "Montre-moi l'évolution des prix du cacao ces 5 dernières années",
            "Quelles sont les prédictions météo pour la saison des pluies ?",
            "Analyse la corrélation entre précipitations et rendements",
            "Quels pays ont la meilleure productivité agricole ?",
            "Comment les prix du café ont-ils évolué ce mois-ci ?",
            "Donne-moi les alertes actives pour les cultures",
            "Quel est l'impact du changement climatique sur l'agriculture ?",
            "Recommande des stratégies d'optimisation des rendements"
        ]
    
    def clear_memory(self):
        """Efface la mémoire conversationnelle"""
        self.memory.clear()


# Instance globale du chatbot
agri_chatbot = AgriChatbot()


async def process_chat_message(message: str, user_id: str = None) -> Dict[str, Any]:
    """Point d'entrée pour traiter les messages du chat"""
    return await agri_chatbot.process_question(message, user_id)


def get_chat_suggestions() -> List[str]:
    """Récupère les questions suggérées"""
    return agri_chatbot.get_suggested_questions()