"""
Service de gestion des alertes et notifications en temps réel
Analyse automatique des seuils et envoi de notifications multi-canal
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Union, Any
from uuid import UUID

import redis.asyncio as redis
from fastapi import WebSocket
from pydantic import BaseModel
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from api.models.sql.actors import Actor, SousSecteursEnum, ActorRoleEnum
from api.models.sql.indicators import (
    IndicateurValeur, SeuilIndicateur, TypeIndicateurEnum, 
    CategorieIndicateurEnum
)
from api.models.sql.user import User
from services.calculations import CalculationService

logger = logging.getLogger(__name__)


class SeveriteAlerte(str, Enum):
    """Niveaux de sévérité des alertes"""
    INFO = "info"
    ATTENTION = "attention"
    ALERTE = "alerte"
    CRITIQUE = "critique"
    URGENCE = "urgence"


class TypeAlerte(str, Enum):
    """Types d'alertes"""
    # Alertes économiques
    CHUTE_REVENUS = "chute_revenus"
    SEUIL_PAUVRETE_ATTEINT = "seuil_pauvrete_atteint"
    ENDETTEMENT_ELEVE = "endettement_eleve"
    
    # Alertes nutritionnelles
    MALNUTRITION_DETECTEE = "malnutrition_detectee"
    DIVERSITE_ALIMENTAIRE_FAIBLE = "diversite_alimentaire_faible"
    
    # Alertes sanitaires
    RISQUE_ZOONOSE = "risque_zoonose"
    ACCIDENT_TRAVAIL_FREQUENT = "accident_travail_frequent"
    
    # Alertes sectorielles
    RENDEMENT_FAIBLE = "rendement_faible"
    MORTALITE_CHEPTEL_ELEVEE = "mortalite_cheptel_elevee"
    CAPTURES_POISSON_BASSES = "captures_poisson_basses"
    DEGRADATION_RESSOURCE_FORESTIERE = "degradation_ressource_forestiere"
    
    # Alertes climatiques
    SECHERESSE = "secheresse"
    INONDATION = "inondation"
    TEMPERATURE_EXTREME = "temperature_extreme"
    
    # Alertes système
    DONNEES_MANQUANTES = "donnees_manquantes"
    QUALITE_DONNEES_DEGRADEE = "qualite_donnees_degradee"


class CanalNotification(str, Enum):
    """Canaux de notification"""
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    WEBSOCKET = "websocket"


class AlerteModel(BaseModel):
    """Modèle Pydantic pour les alertes"""
    id: str
    type_alerte: TypeAlerte
    severite: SeveriteAlerte
    titre: str
    message: str
    actor_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    sous_secteur: Optional[SousSecteursEnum] = None
    region: Optional[str] = None
    donnees_contexte: Dict[str, Any] = {}
    actions_recommandees: List[str] = []
    expires_at: Optional[datetime] = None
    created_at: datetime
    is_read: bool = False
    is_acknowledged: bool = False


class AlerteService:
    """Service principal de gestion des alertes"""
    
    def __init__(self, db: Session, redis_client: redis.Redis):
        self.db = db
        self.redis = redis_client
        self.calculation_service = CalculationService(db)
        
        # Canaux Redis pour les différents types d'alertes
        self.CHANNEL_ALERTES = "agri:alerts:all"
        self.CHANNEL_URGENCES = "agri:alerts:urgent"
        self.CHANNEL_WEBSOCKETS = "agri:websockets:broadcast"
        
        # Connexions WebSocket actives
        self.active_websockets: Dict[str, WebSocket] = {}
    
    
    # ================================================
    # ANALYSE ET DÉTECTION D'ALERTES
    # ================================================
    
    async def analyser_nouvel_indicateur(self, indicateur: IndicateurValeur):
        """
        Analyse automatique d'un nouvel indicateur pour déclencher des alertes
        """
        try:
            logger.info(f"Analyse indicateur {indicateur.type_indicateur} pour actor {indicateur.actor_id}")
            
            # Récupérer l'acteur et les seuils applicables
            actor = self.db.query(Actor).filter(Actor.id == indicateur.actor_id).first()
            if not actor:
                logger.warning(f"Acteur non trouvé: {indicateur.actor_id}")
                return
            
            # Chercher les seuils configurés pour cet indicateur
            seuils = self.db.query(SeuilIndicateur).filter(
                and_(
                    SeuilIndicateur.type_indicateur == indicateur.type_indicateur,
                    SeuilIndicateur.is_active == True,
                    SeuilIndicateur.date_debut <= datetime.now().date()
                )
            ).all()
            
            # Analyser chaque seuil applicable
            for seuil in seuils:
                if self._seuil_applicable(seuil, actor):
                    await self._evaluer_seuil(indicateur, seuil, actor)
            
            # Analyses sectorielles spécialisées
            await self._analyses_sectorielles(indicateur, actor)
            
            # Détection de patterns et tendances
            await self._detecter_tendances(indicateur, actor)
            
        except Exception as e:
            logger.error(f"Erreur analyse indicateur: {e}")
    
    
    async def _evaluer_seuil(self, indicateur: IndicateurValeur, seuil: SeuilIndicateur, actor: Actor):
        """Évaluer si un indicateur dépasse un seuil configuré"""
        try:
            valeur = indicateur.valeur_numerique
            if not valeur:
                return
            
            # Déterminer le niveau d'alerte
            alerte_info = None
            
            # Seuil critique dépassé
            if ((seuil.seuil_critique_min and valeur < seuil.seuil_critique_min) or
                (seuil.seuil_critique_max and valeur > seuil.seuil_critique_max)):
                
                alerte_info = {
                    "severite": SeveriteAlerte.CRITIQUE,
                    "message": seuil.message_critique or f"Seuil critique dépassé pour {indicateur.type_indicateur.value}",
                    "actions": seuil.actions_critiques or []
                }
            
            # Seuil d'alerte dépassé
            elif ((seuil.seuil_alerte_min and valeur < seuil.seuil_alerte_min) or
                  (seuil.seuil_alerte_max and valeur > seuil.seuil_alerte_max)):
                
                alerte_info = {
                    "severite": SeveriteAlerte.ALERTE,
                    "message": seuil.message_alerte or f"Seuil d'alerte dépassé pour {indicateur.type_indicateur.value}",
                    "actions": seuil.actions_preventives or []
                }
            
            # Créer l'alerte si nécessaire
            if alerte_info:
                await self._creer_alerte(
                    type_alerte=self._map_indicateur_to_alerte_type(indicateur.type_indicateur),
                    severite=alerte_info["severite"],
                    titre=f"Alerte {indicateur.type_indicateur.value}",
                    message=alerte_info["message"],
                    actor=actor,
                    donnees_contexte={
                        "valeur_actuelle": str(valeur),
                        "seuil_min": str(seuil.seuil_alerte_min) if seuil.seuil_alerte_min else None,
                        "seuil_max": str(seuil.seuil_alerte_max) if seuil.seuil_alerte_max else None,
                        "type_indicateur": indicateur.type_indicateur.value,
                        "periode": indicateur.date_debut.isoformat()
                    },
                    actions_recommandees=alerte_info["actions"]
                )
                
        except Exception as e:
            logger.error(f"Erreur évaluation seuil: {e}")
    
    
    async def _analyses_sectorielles(self, indicateur: IndicateurValeur, actor: Actor):
        """Analyses spécialisées par sous-secteur"""
        try:
            if actor.sous_secteur == SousSecteursEnum.VEGETAL:
                await self._analyser_secteur_vegetal(indicateur, actor)
            elif actor.sous_secteur == SousSecteursEnum.ANIMAL:
                await self._analyser_secteur_animal(indicateur, actor)
            elif actor.sous_secteur == SousSecteursEnum.HALIEUTIQUE:
                await self._analyser_secteur_halieutique(indicateur, actor)
            elif actor.sous_secteur == SousSecteursEnum.FORESTIER:
                await self._analyser_secteur_forestier(indicateur, actor)
                
        except Exception as e:
            logger.error(f"Erreur analyses sectorielles: {e}")
    
    
    async def _analyser_secteur_vegetal(self, indicateur: IndicateurValeur, actor: Actor):
        """Analyses spécifiques au secteur végétal"""
        # Alerte rendement faible
        if indicateur.type_indicateur == TypeIndicateurEnum.CHIFFRE_AFFAIRES:
            # Calculer le rendement moyen régional pour comparaison
            rendement_regional_moyen = await self._calculer_rendement_regional_moyen(
                actor.region, actor.sous_secteur, indicateur.annee
            )
            
            if (rendement_regional_moyen and 
                indicateur.valeur_numerique and 
                indicateur.valeur_numerique < rendement_regional_moyen * Decimal("0.7")):
                
                await self._creer_alerte(
                    type_alerte=TypeAlerte.RENDEMENT_FAIBLE,
                    severite=SeveriteAlerte.ATTENTION,
                    titre="Rendement inférieur à la moyenne régionale",
                    message=f"Le rendement est 30% inférieur à la moyenne régionale ({rendement_regional_moyen} FCFA/ha)",
                    actor=actor,
                    donnees_contexte={
                        "rendement_actuel": str(indicateur.valeur_numerique),
                        "rendement_regional": str(rendement_regional_moyen),
                        "ecart_pct": str(((indicateur.valeur_numerique - rendement_regional_moyen) / rendement_regional_moyen) * 100)
                    },
                    actions_recommandees=[
                        "Contacter un technicien agricole",
                        "Vérifier la qualité des semences", 
                        "Analyser les pratiques culturales",
                        "Évaluer l'état du sol"
                    ]
                )
    
    
    async def _analyser_secteur_animal(self, indicateur: IndicateurValeur, actor: Actor):
        """Analyses spécifiques au secteur animal"""
        # Surveillance mortalité du cheptel
        if (indicateur.valeur_json and 
            "taux_mortalite_pct" in indicateur.valeur_json):
            
            taux_mortalite = Decimal(str(indicateur.valeur_json["taux_mortalite_pct"]))
            
            if taux_mortalite > Decimal("10"):  # Plus de 10% de mortalité
                severite = SeveriteAlerte.CRITIQUE if taux_mortalite > 20 else SeveriteAlerte.ALERTE
                
                await self._creer_alerte(
                    type_alerte=TypeAlerte.MORTALITE_CHEPTEL_ELEVEE,
                    severite=severite,
                    titre="Mortalité élevée du cheptel",
                    message=f"Taux de mortalité de {taux_mortalite}% détecté",
                    actor=actor,
                    donnees_contexte={
                        "taux_mortalite": str(taux_mortalite),
                        "type_animal": indicateur.valeur_json.get("type_animal", "non_specifie")
                    },
                    actions_recommandees=[
                        "Consulter un vétérinaire d'urgence",
                        "Isoler les animaux malades",
                        "Vérifier l'alimentation et l'eau",
                        "Désinfecter les installations"
                    ]
                )
    
    
    async def _analyser_secteur_halieutique(self, indicateur: IndicateurValeur, actor: Actor):
        """Analyses spécifiques au secteur halieutique"""
        # Surveillance des captures
        if (indicateur.type_indicateur == TypeIndicateurEnum.CHIFFRE_AFFAIRES and
            indicateur.valeur_json and "capture_kg_sortie" in indicateur.valeur_json):
            
            capture_actuelle = Decimal(str(indicateur.valeur_json["capture_kg_sortie"]))
            
            # Comparer avec la moyenne des 3 derniers mois
            captures_historiques = await self._obtenir_captures_historiques(actor, 3)
            if captures_historiques:
                moyenne_historique = sum(captures_historiques) / len(captures_historiques)
                
                if capture_actuelle < moyenne_historique * Decimal("0.5"):  # 50% de baisse
                    await self._creer_alerte(
                        type_alerte=TypeAlerte.CAPTURES_POISSON_BASSES,
                        severite=SeveriteAlerte.ATTENTION,
                        titre="Captures de poisson en baisse",
                        message=f"Captures actuelles ({capture_actuelle} kg) inférieures de 50% à la moyenne",
                        actor=actor,
                        donnees_contexte={
                            "capture_actuelle": str(capture_actuelle),
                            "moyenne_historique": str(moyenne_historique),
                            "baisse_pct": str(((capture_actuelle - moyenne_historique) / moyenne_historique) * 100)
                        },
                        actions_recommandees=[
                            "Changer de zone de pêche",
                            "Vérifier l'état des filets",
                            "Consulter les prévisions météo",
                            "Contacter d'autres pêcheurs pour information"
                        ]
                    )
    
    
    async def _analyser_secteur_forestier(self, indicateur: IndicateurValeur, actor: Actor):
        """Analyses spécifiques au secteur forestier"""
        # Surveillance durabilité des prélèvements
        if (indicateur.type_indicateur == TypeIndicateurEnum.CHIFFRE_AFFAIRES and
            indicateur.valeur_json and "quantite_recoltee_kg" in indicateur.valeur_json):
            
            quantite_actuelle = Decimal(str(indicateur.valeur_json["quantite_recoltee_kg"]))
            
            # Calculer le taux d'extraction annuel
            extraction_annuelle = await self._calculer_extraction_annuelle(actor)
            
            if extraction_annuelle and extraction_annuelle > Decimal("1000"):  # Seuil d'exemple
                await self._creer_alerte(
                    type_alerte=TypeAlerte.DEGRADATION_RESSOURCE_FORESTIERE,
                    severite=SeveriteAlerte.ALERTE,
                    titre="Risque de surexploitation forestière",
                    message=f"Extraction annuelle de {extraction_annuelle} kg dépasse les seuils durables",
                    actor=actor,
                    donnees_contexte={
                        "extraction_annuelle": str(extraction_annuelle),
                        "produit": indicateur.valeur_json.get("type_produit", "non_specifie")
                    },
                    actions_recommandees=[
                        "Réduire temporairement les prélèvements",
                        "Mettre en place un plan de régénération",
                        "Diversifier les produits forestiers",
                        "Contacter un agent forestier"
                    ]
                )
    
    
    async def _detecter_tendances(self, indicateur: IndicateurValeur, actor: Actor):
        """Détection de tendances et patterns dans les données"""
        try:
            # Récupérer les 6 dernières valeurs de cet indicateur
            historique = self.db.query(IndicateurValeur).filter(
                and_(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.type_indicateur == indicateur.type_indicateur,
                    IndicateurValeur.valeur_numerique.isnot(None)
                )
            ).order_by(desc(IndicateurValeur.date_debut)).limit(6).all()
            
            if len(historique) >= 4:  # Minimum 4 points pour détecter une tendance
                valeurs = [h.valeur_numerique for h in historique]
                valeurs.reverse()  # Ordre chronologique
                
                # Détection de tendance baissière continue
                if all(valeurs[i] > valeurs[i+1] for i in range(len(valeurs)-1)):
                    baisse_totale_pct = ((valeurs[-1] - valeurs[0]) / valeurs[0]) * 100
                    
                    if baisse_totale_pct < -20:  # Plus de 20% de baisse
                        await self._creer_alerte(
                            type_alerte=TypeAlerte.CHUTE_REVENUS,
                            severite=SeveriteAlerte.ALERTE,
                            titre="Tendance baissière détectée",
                            message=f"Baisse continue de {abs(baisse_totale_pct):.1f}% sur les dernières mesures",
                            actor=actor,
                            donnees_contexte={
                                "baisse_pct": str(baisse_totale_pct),
                                "nb_periodes": len(valeurs),
                                "valeur_initiale": str(valeurs[0]),
                                "valeur_finale": str(valeurs[-1]),
                                "type_indicateur": indicateur.type_indicateur.value
                            },
                            actions_recommandees=[
                                "Analyser les causes de la baisse",
                                "Réviser la stratégie d'exploitation",
                                "Chercher des sources de revenus complémentaires",
                                "Contacter un conseiller technique"
                            ]
                        )
                        
        except Exception as e:
            logger.error(f"Erreur détection tendances: {e}")
    
    
    # ================================================
    # CRÉATION ET GESTION DES ALERTES
    # ================================================
    
    async def _creer_alerte(self, type_alerte: TypeAlerte, severite: SeveriteAlerte,
                           titre: str, message: str, actor: Actor = None,
                           user_id: UUID = None, donnees_contexte: Dict = None,
                           actions_recommandees: List[str] = None):
        """Créer et diffuser une nouvelle alerte"""
        try:
            # Éviter les alertes en double (même type pour même acteur dans les 24h)
            if await self._alerte_deja_existante(type_alerte, actor, user_id):
                logger.info(f"Alerte {type_alerte} déjà existante pour actor/user")
                return
            
            # Créer l'objet alerte
            alerte = AlerteModel(
                id=f"{type_alerte.value}_{actor.id if actor else user_id}_{int(datetime.now().timestamp())}",
                type_alerte=type_alerte,
                severite=severite,
                titre=titre,
                message=message,
                actor_id=actor.id if actor else None,
                user_id=user_id,
                sous_secteur=actor.sous_secteur if actor else None,
                region=actor.region if actor else None,
                donnees_contexte=donnees_contexte or {},
                actions_recommandees=actions_recommandees or [],
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(days=7)  # Expire après 7 jours
            )
            
            # Sauvegarder en Redis
            await self._sauvegarder_alerte_redis(alerte)
            
            # Diffuser l'alerte
            await self._diffuser_alerte(alerte)
            
            # Sauvegarder en BDD pour historique
            await self._sauvegarder_alerte_bdd(alerte)
            
            logger.info(f"Alerte créée: {type_alerte.value} - {severite.value}")
            
        except Exception as e:
            logger.error(f"Erreur création alerte: {e}")
    
    
    async def _sauvegarder_alerte_redis(self, alerte: AlerteModel):
        """Sauvegarder l'alerte en Redis avec TTL"""
        try:
            # Clé Redis pour cette alerte
            key = f"alerte:{alerte.id}"
            
            # Sérialiser l'alerte
            alerte_json = alerte.json()
            
            # Sauvegarder avec TTL de 7 jours
            await self.redis.setex(key, 604800, alerte_json)
            
            # Ajouter aux index par utilisateur/acteur
            if alerte.user_id:
                await self.redis.sadd(f"user_alertes:{alerte.user_id}", alerte.id)
            if alerte.actor_id:
                await self.redis.sadd(f"actor_alertes:{alerte.actor_id}", alerte.id)
            
            # Index par sévérité
            await self.redis.sadd(f"alertes_severite:{alerte.severite.value}", alerte.id)
            
            # Index par région si applicable
            if alerte.region:
                await self.redis.sadd(f"alertes_region:{alerte.region}", alerte.id)
                
        except Exception as e:
            logger.error(f"Erreur sauvegarde Redis: {e}")
    
    
    async def _diffuser_alerte(self, alerte: AlerteModel):
        """Diffuser l'alerte sur tous les canaux appropriés"""
        try:
            # Publier sur le canal général
            await self.redis.publish(self.CHANNEL_ALERTES, alerte.json())
            
            # Publier sur le canal urgences si critique
            if alerte.severite in [SeveriteAlerte.CRITIQUE, SeveriteAlerte.URGENCE]:
                await self.redis.publish(self.CHANNEL_URGENCES, alerte.json())
            
            # Notifier via WebSocket les utilisateurs connectés
            await self._notifier_websockets(alerte)
            
            # Envoyer les notifications selon les préférences utilisateur
            await self._envoyer_notifications(alerte)
            
        except Exception as e:
            logger.error(f"Erreur diffusion alerte: {e}")
    
    
    async def _notifier_websockets(self, alerte: AlerteModel):
        """Notifier les connexions WebSocket actives"""
        try:
            # Identifier les utilisateurs à notifier
            users_to_notify = set()
            
            # Si c'est pour un acteur spécifique, notifier son utilisateur
            if alerte.actor_id and alerte.user_id:
                users_to_notify.add(str(alerte.user_id))
            
            # Notifier les administrateurs pour les alertes critiques
            if alerte.severite in [SeveriteAlerte.CRITIQUE, SeveriteAlerte.URGENCE]:
                # Récupérer les admin/analysts de la région
                admins = self.db.query(User).join(UserRole).join(Role).filter(
                    and_(
                        Role.name.in_(["admin", "analyst"]),
                        UserRole.is_active == True
                    )
                ).all()
                
                for admin in admins:
                    users_to_notify.add(str(admin.id))
            
            # Envoyer via WebSocket
            message = {
                "type": "alerte",
                "data": json.loads(alerte.json())
            }
            
            for user_id in users_to_notify:
                if user_id in self.active_websockets:
                    try:
                        await self.active_websockets[user_id].send_text(json.dumps(message))
                    except Exception as ws_error:
                        logger.warning(f"Erreur envoi WebSocket à {user_id}: {ws_error}")
                        # Nettoyer la connexion fermée
                        del self.active_websockets[user_id]
                        
        except Exception as e:
            logger.error(f"Erreur notification WebSocket: {e}")
    
    
    # ================================================
    # MÉTHODES UTILITAIRES
    # ================================================
    
    def _seuil_applicable(self, seuil: SeuilIndicateur, actor: Actor) -> bool:
        """Vérifier si un seuil est applicable à un acteur"""
        # Vérifier la concordance de secteur
        if seuil.sous_secteur and seuil.sous_secteur != actor.sous_secteur:
            return False
        
        # Vérifier la région
        if seuil.region and seuil.region != actor.region:
            return False
        
        # Vérifier le pays
        if seuil.pays and seuil.pays != actor.pays:
            return False
        
        # Vérifier le rôle
        if seuil.role_acteur and seuil.role_acteur != actor.role.value:
            return False
        
        return True
    
    
    def _map_indicateur_to_alerte_type(self, type_indicateur: TypeIndicateurEnum) -> TypeAlerte:
        """Mapper un type d'indicateur vers un type d'alerte"""
        mapping = {
            TypeIndicateurEnum.REVENU_MENSUEL: TypeAlerte.CHUTE_REVENUS,
            TypeIndicateurEnum.SEUIL_PAUVRETE: TypeAlerte.SEUIL_PAUVRETE_ATTEINT,
            TypeIndicateurEnum.ENDETTEMENT: TypeAlerte.ENDETTEMENT_ELEVE,
            TypeIndicateurEnum.DIVERSITE_ALIMENTAIRE: TypeAlerte.DIVERSITE_ALIMENTAIRE_FAIBLE,
            # ... continuer le mapping
        }
        
        return mapping.get(type_indicateur, TypeAlerte.DONNEES_MANQUANTES)
    
    
    async def _alerte_deja_existante(self, type_alerte: TypeAlerte, actor: Actor = None, 
                                    user_id: UUID = None) -> bool:
        """Vérifier si une alerte similaire existe déjà (dernières 24h)"""
        try:
            # Chercher dans Redis les alertes des dernières 24h
            if actor:
                alertes_ids = await self.redis.smembers(f"actor_alertes:{actor.id}")
            elif user_id:
                alertes_ids = await self.redis.smembers(f"user_alertes:{user_id}")
            else:
                return False
            
            # Vérifier chaque alerte
            for alerte_id in alertes_ids:
                alerte_data = await self.redis.get(f"alerte:{alerte_id.decode()}")
                if alerte_data:
                    alerte = AlerteModel.parse_raw(alerte_data)
                    if (alerte.type_alerte == type_alerte and
                        alerte.created_at > datetime.now() - timedelta(hours=24)):
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erreur vérification alerte existante: {e}")
            return False
    
    
    async def _calculer_rendement_regional_moyen(self, region: str, sous_secteur: SousSecteursEnum, 
                                               annee: int) -> Optional[Decimal]:
        """Calculer le rendement moyen régional"""
        try:
            query = self.db.query(func.avg(IndicateurValeur.valeur_numerique)).join(Actor).filter(
                and_(
                    Actor.region == region,
                    IndicateurValeur.sous_secteur == sous_secteur,
                    IndicateurValeur.type_indicateur == TypeIndicateurEnum.CHIFFRE_AFFAIRES,
                    IndicateurValeur.annee == annee
                )
            )
            
            result = query.scalar()
            return Decimal(str(result)) if result else None
            
        except Exception as e:
            logger.error(f"Erreur calcul rendement régional: {e}")
            return None
    
    
    async def _obtenir_captures_historiques(self, actor: Actor, nb_mois: int) -> List[Decimal]:
        """Obtenir l'historique des captures pour un pêcheur"""
        try:
            date_limite = datetime.now() - timedelta(days=30 * nb_mois)
            
            captures = self.db.query(IndicateurValeur).filter(
                and_(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.type_indicateur == TypeIndicateurEnum.CHIFFRE_AFFAIRES,
                    IndicateurValeur.created_at >= date_limite,
                    IndicateurValeur.valeur_json.contains({"capture_kg_sortie": None})
                )
            ).all()
            
            return [
                Decimal(str(c.valeur_json["capture_kg_sortie"])) 
                for c in captures 
                if c.valeur_json and "capture_kg_sortie" in c.valeur_json
            ]
            
        except Exception as e:
            logger.error(f"Erreur obtention captures historiques: {e}")
            return []
    
    
    async def _calculer_extraction_annuelle(self, actor: Actor) -> Optional[Decimal]:
        """Calculer l'extraction forestière annuelle"""
        try:
            annee_courante = datetime.now().year
            
            extractions = self.db.query(IndicateurValeur).filter(
                and_(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.annee == annee_courante,
                    IndicateurValeur.valeur_json.contains({"quantite_recoltee_kg": None})
                )
            ).all()
            
            total = sum(
                Decimal(str(e.valeur_json["quantite_recoltee_kg"]))
                for e in extractions
                if e.valeur_json and "quantite_recoltee_kg" in e.valeur_json
            )
            
            return total if total > 0 else None
            
        except Exception as e:
            logger.error(f"Erreur calcul extraction annuelle: {e}")
            return None
    
    
    async def _sauvegarder_alerte_bdd(self, alerte: AlerteModel):
        """Sauvegarder l'alerte en BDD pour l'historique"""
        try:
            from api.models.sql.agricultural import Alert
            
            alert_db = Alert(
                title=alerte.titre,
                message=alerte.message,
                alert_type=alerte.type_alerte.value,
                severity=alerte.severite.value,
                user_id=alerte.user_id,
                country_id=None,  # À adapter selon le modèle
                crop_id=None      # À adapter selon le modèle
            )
            
            self.db.add(alert_db)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde BDD: {e}")
            self.db.rollback()
    
    
    async def _envoyer_notifications(self, alerte: AlerteModel):
        """Envoyer les notifications selon les préférences utilisateur"""
        # Implementation des notifications email, SMS, webhook
        # À développer selon les besoins
        pass
    
    
    # ================================================
    # GESTION DES WEBSOCKETS
    # ================================================
    
    async def add_websocket_connection(self, user_id: str, websocket: WebSocket):
        """Ajouter une connexion WebSocket"""
        self.active_websockets[user_id] = websocket
        logger.info(f"WebSocket connection added for user {user_id}")
    
    
    async def remove_websocket_connection(self, user_id: str):
        """Supprimer une connexion WebSocket"""
        if user_id in self.active_websockets:
            del self.active_websockets[user_id]
            logger.info(f"WebSocket connection removed for user {user_id}")
    
    
    # ================================================
    # API PUBLIQUES POUR LA CONSULTATION DES ALERTES
    # ================================================
    
    async def obtenir_alertes_utilisateur(self, user_id: UUID, limit: int = 50) -> List[AlerteModel]:
        """Obtenir les alertes d'un utilisateur"""
        try:
            alertes_ids = await self.redis.smembers(f"user_alertes:{user_id}")
            alertes = []
            
            for alerte_id in alertes_ids:
                alerte_data = await self.redis.get(f"alerte:{alerte_id.decode()}")
                if alerte_data:
                    alerte = AlerteModel.parse_raw(alerte_data)
                    alertes.append(alerte)
            
            # Trier par date de création (plus récentes en premier)
            alertes.sort(key=lambda x: x.created_at, reverse=True)
            
            return alertes[:limit]
            
        except Exception as e:
            logger.error(f"Erreur obtention alertes utilisateur: {e}")
            return []
    
    
    async def marquer_alerte_lue(self, alerte_id: str, user_id: UUID):
        """Marquer une alerte comme lue"""
        try:
            alerte_data = await self.redis.get(f"alerte:{alerte_id}")
            if alerte_data:
                alerte = AlerteModel.parse_raw(alerte_data)
                if alerte.user_id == user_id or alerte.actor_id:  # Vérification des permissions
                    alerte.is_read = True
                    await self.redis.setex(f"alerte:{alerte_id}", 604800, alerte.json())
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erreur marquage alerte lue: {e}")
            return False
    
    
    async def acquitter_alerte(self, alerte_id: str, user_id: UUID):
        """Acquitter une alerte"""
        try:
            alerte_data = await self.redis.get(f"alerte:{alerte_id}")
            if alerte_data:
                alerte = AlerteModel.parse_raw(alerte_data)
                # Vérifications de permissions...
                alerte.is_acknowledged = True
                await self.redis.setex(f"alerte:{alerte_id}", 604800, alerte.json())
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erreur acquittement alerte: {e}")
            return False