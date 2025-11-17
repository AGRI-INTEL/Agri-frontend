"""
Routeur des secteurs agricoles - Gestion multi-tenant des 4 sous-secteurs
Organisation par acteurs avec CRUD complet et gestion des indicateurs
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from api.models.sql.actors import (
    Actor, SousSecteursEnum, ActorRoleEnum, ProducteurVegetal, 
    EleveurAnimal, PecheurHalieutique, ExploitantForestier
)
from api.models.sql.indicators import (
    IndicateurValeur, CategorieIndicateurEnum, TypeIndicateurEnum,
    UniteIndicateurEnum, PeriodeIndicateurEnum
)
from config.database import get_db
from services.calculations import CalculationService
from services.alerts import AlerteService
from middleware.auth import get_current_user
from api.models.sql.user import User

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()


# ==========================================
# MODÈLES PYDANTIC POUR L'API
# ==========================================

class ActorBase(BaseModel):
    """Modèle de base pour tous les acteurs"""
    nom: str = Field(..., min_length=2, max_length=255)
    prenom: Optional[str] = Field(None, max_length=255)
    nom_organisation: Optional[str] = Field(None, max_length=500)
    sous_secteur: SousSecteursEnum
    role: ActorRoleEnum
    
    # Informations de contact
    telephone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    adresse: Optional[str] = None
    
    # Localisation
    pays: str = Field(default="Sénégal", max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    departement: Optional[str] = Field(None, max_length=100)
    commune: Optional[str] = Field(None, max_length=100)
    village: Optional[str] = Field(None, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    
    # Informations démographiques
    age: Optional[int] = Field(None, ge=18, le=100)
    genre: Optional[str] = Field(None, regex="^[MFA]$")  # M/F/A (Autre)
    niveau_education: Optional[str] = None
    taille_menage: Optional[int] = Field(None, ge=1, le=20)
    
    # Informations socio-économiques
    statut_matrimonial: Optional[str] = None
    nombre_enfants: Optional[int] = Field(None, ge=0, le=15)
    acces_electricite: bool = False
    acces_eau_potable: bool = False
    type_logement: Optional[str] = None
    
    # Métadonnées extensibles
    metadonnees_specifiques: Optional[Dict] = None


class ActorCreate(ActorBase):
    """Modèle pour la création d'un acteur"""
    pass


class ActorUpdate(BaseModel):
    """Modèle pour la mise à jour d'un acteur"""
    nom: Optional[str] = Field(None, min_length=2, max_length=255)
    prenom: Optional[str] = Field(None, max_length=255)
    nom_organisation: Optional[str] = Field(None, max_length=500)
    
    # Tous les autres champs optionnels
    telephone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    adresse: Optional[str] = None
    region: Optional[str] = Field(None, max_length=100)
    departement: Optional[str] = Field(None, max_length=100)
    commune: Optional[str] = Field(None, max_length=100)
    village: Optional[str] = Field(None, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    age: Optional[int] = Field(None, ge=18, le=100)
    genre: Optional[str] = Field(None, regex="^[MFA]$")
    niveau_education: Optional[str] = None
    taille_menage: Optional[int] = Field(None, ge=1, le=20)
    statut_matrimonial: Optional[str] = None
    nombre_enfants: Optional[int] = Field(None, ge=0, le=15)
    acces_electricite: Optional[bool] = None
    acces_eau_potable: Optional[bool] = None
    type_logement: Optional[str] = None
    metadonnees_specifiques: Optional[Dict] = None


class ActorResponse(ActorBase):
    """Modèle de réponse pour un acteur"""
    id: UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    
    # Statistiques calculées
    nombre_indicateurs: Optional[int] = 0
    class Config:
        from_attributes = True


class IndicateurCreate(BaseModel):
    """Modèle pour la création d'un indicateur"""
    type_indicateur: TypeIndicateurEnum
    categorie: CategorieIndicateurEnum
    
    # Valeurs (une seule doit être fournie selon le type)
    valeur_numerique: Optional[float] = None
    valeur_texte: Optional[str] = Field(None, max_length=500)
    valeur_booleen: Optional[bool] = None
    valeur_json: Optional[Dict] = None
    
    # Métadonnées
    unite: UniteIndicateurEnum
    periode: PeriodeIndicateurEnum
    date_debut: date
    date_fin: Optional[date] = None
    saison: Optional[str] = Field(None, max_length=20)
    
    # Contexte
    contexte: Optional[Dict] = None
    commentaire: Optional[str] = None
    source: Optional[str] = Field(None, max_length=100)


class IndicateurResponse(BaseModel):
    """Modèle de réponse pour un indicateur"""
    id: UUID
    actor_id: UUID
    sous_secteur: SousSecteursEnum
    type_indicateur: TypeIndicateurEnum
    categorie: CategorieIndicateurEnum
    
    valeur_numerique: Optional[float]
    valeur_texte: Optional[str]
    valeur_booleen: Optional[bool]
    valeur_json: Optional[Dict]
    
    unite: UniteIndicateurEnum
    periode: PeriodeIndicateurEnum
    date_debut: date
    date_fin: Optional[date]
    annee: int
    mois: Optional[int]
    saison: Optional[str]
    
    contexte: Optional[Dict]
    commentaire: Optional[str]
    source: Optional[str]
    
    qualite_donnee: float
    is_valide: bool
    is_calculee: bool
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class StatsSecteurResponse(BaseModel):
    """Statistiques d'un secteur"""
    sous_secteur: SousSecteursEnum
    nombre_acteurs: int
    nombre_acteurs_actifs: int
    nombre_indicateurs: int
    derniere_activite: Optional[datetime]
    repartition_roles: Dict[str, int]
    repartition_regions: Dict[str, int]


# ==========================================
# MIDDLEWARE ET UTILITAIRES
# ==========================================

async def verify_sector_access(
    secteur: SousSecteursEnum,
    current_user: User = Depends(get_current_user)
) -> bool:
    """Vérifier l'accès au secteur selon les permissions utilisateur"""
    # TODO: Implémenter la logique RBAC
    # Pour l'instant, accès libre pour tous les utilisateurs authentifiés
    return True


async def get_calculation_service(db: Session = Depends(get_db)) -> CalculationService:
    """Obtenir le service de calculs"""
    return CalculationService(db)


# ==========================================
# ENDPOINTS GÉNÉRIQUES POUR TOUS SECTEURS
# ==========================================

@router.get("/", response_model=List[StatsSecteurResponse])
async def list_sectors_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Vue d'ensemble de tous les secteurs avec statistiques"""
    try:
        secteurs_stats = []
        
        for secteur in SousSecteursEnum:
            # Compter les acteurs
            nb_acteurs = db.query(Actor).filter(Actor.sous_secteur == secteur).count()
            nb_acteurs_actifs = db.query(Actor).filter(
                and_(Actor.sous_secteur == secteur, Actor.is_active == True)
            ).count()
            
            # Compter les indicateurs
            nb_indicateurs = db.query(IndicateurValeur).filter(
                IndicateurValeur.sous_secteur == secteur
            ).count()
            
            # Dernière activité
            derniere_activite = db.query(func.max(IndicateurValeur.created_at)).filter(
                IndicateurValeur.sous_secteur == secteur
            ).scalar()
            
            # Répartition par rôles
            repartition_roles = {}
            roles_query = db.query(
                Actor.role, func.count(Actor.id)
            ).filter(Actor.sous_secteur == secteur).group_by(Actor.role).all()
            
            for role, count in roles_query:
                repartition_roles[role.value] = count
            
            # Répartition par régions
            repartition_regions = {}
            regions_query = db.query(
                Actor.region, func.count(Actor.id)
            ).filter(
                and_(Actor.sous_secteur == secteur, Actor.region.isnot(None))
            ).group_by(Actor.region).all()
            
            for region, count in regions_query:
                repartition_regions[region] = count
            
            secteurs_stats.append(StatsSecteurResponse(
                sous_secteur=secteur,
                nombre_acteurs=nb_acteurs,
                nombre_acteurs_actifs=nb_acteurs_actifs,
                nombre_indicateurs=nb_indicateurs,
                derniere_activite=derniere_activite,
                repartition_roles=repartition_roles,
                repartition_regions=repartition_regions
            ))
        
        return secteurs_stats
        
    except Exception as e:
        logger.error(f"Erreur récupération vue secteurs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des statistiques sectorielles"
        )


# ==========================================
# ENDPOINTS SPÉCIFIQUES PAR SECTEUR
# ==========================================

@router.get("/{secteur}/actors", response_model=List[ActorResponse])
async def list_actors_by_sector(
    secteur: SousSecteursEnum,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sector_access: bool = Depends(verify_sector_access),
    role: Optional[ActorRoleEnum] = Query(None, description="Filtrer par rôle"),
    region: Optional[str] = Query(None, description="Filtrer par région"),
    is_active: Optional[bool] = Query(None, description="Filtrer par statut actif"),
    limit: int = Query(50, ge=1, le=100, description="Nombre max de résultats"),
    offset: int = Query(0, ge=0, description="Décalage pour pagination")
):
    """Lister les acteurs d'un secteur avec filtres"""
    try:
        query = db.query(Actor).filter(Actor.sous_secteur == secteur)
        
        # Appliquer les filtres
        if role:
            query = query.filter(Actor.role == role)
        if region:
            query = query.filter(Actor.region == region)
        if is_active is not None:
            query = query.filter(Actor.is_active == is_active)
        
        # Pagination
        actors = query.offset(offset).limit(limit).all()
        
        # Enrichir avec statistiques
        actors_response = []
        for actor in actors:
            # Compter les indicateurs
            nb_indicateurs = db.query(IndicateurValeur).filter(
                IndicateurValeur.actor_id == actor.id
            ).count()
            
            # Dernière saisie
            derniere_saisie = db.query(func.max(IndicateurValeur.created_at)).filter(
                IndicateurValeur.actor_id == actor.id
            ).scalar()
            
            actor_response = ActorResponse.from_orm(actor)
            actor_response.nombre_indicateurs = nb_indicateurs
            actor_response.derniere_saisie = derniere_saisie
            
            actors_response.append(actor_response)
        
        return actors_response
        
    except Exception as e:
        logger.error(f"Erreur récupération acteurs secteur {secteur}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des acteurs"
        )


@router.post("/{secteur}/actors", response_model=ActorResponse, status_code=status.HTTP_201_CREATED)
async def create_actor(
    secteur: SousSecteursEnum,
    actor_data: ActorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sector_access: bool = Depends(verify_sector_access)
):
    """Créer un nouvel acteur dans un secteur"""
    try:
        # Vérifier la cohérence secteur/rôle
        if actor_data.sous_secteur != secteur:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le secteur dans l'URL ne correspond pas à celui dans les données"
            )
        
        # Vérifier que le rôle est compatible avec le secteur
        roles_secteur = _get_roles_for_secteur(secteur)
        if actor_data.role not in roles_secteur:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Le rôle {actor_data.role} n'est pas valide pour le secteur {secteur}"
            )
        
        # Créer l'acteur principal
        actor = Actor(**actor_data.dict())
        db.add(actor)
        db.flush()  # Pour obtenir l'ID
        
        # Créer le profil spécialisé si nécessaire
        await _create_specialized_profile(actor, secteur, db)
        
        db.commit()
        db.refresh(actor)
        
        logger.info(f"Acteur créé: {actor.id} - {actor.nom} ({secteur})")
        
        # Retourner la réponse enrichie
        actor_response = ActorResponse.from_orm(actor)
        actor_response.nombre_indicateurs = 0
        actor_response.derniere_saisie = None
        
        return actor_response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur création acteur: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la création de l'acteur"
        )


@router.get("/{secteur}/actors/{actor_id}", response_model=ActorResponse)
async def get_actor_by_id(
    secteur: SousSecteursEnum,
    actor_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sector_access: bool = Depends(verify_sector_access)
):
    """Récupérer un acteur spécifique par son ID"""
    try:
        actor = db.query(Actor).filter(
            and_(Actor.id == actor_id, Actor.sous_secteur == secteur)
        ).first()
        
        if not actor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Acteur non trouvé"
            )
        
        # Statistiques
        nb_indicateurs = db.query(IndicateurValeur).filter(
            IndicateurValeur.actor_id == actor.id
        ).count()
        
        derniere_saisie = db.query(func.max(IndicateurValeur.created_at)).filter(
            IndicateurValeur.actor_id == actor.id
        ).scalar()
        
        actor_response = ActorResponse.from_orm(actor)
        actor_response.nombre_indicateurs = nb_indicateurs
        actor_response.derniere_saisie = derniere_saisie
        
        return actor_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération acteur {actor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération de l'acteur"
        )


@router.put("/{secteur}/actors/{actor_id}", response_model=ActorResponse)
async def update_actor(
    secteur: SousSecteursEnum,
    actor_id: UUID,
    actor_update: ActorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sector_access: bool = Depends(verify_sector_access)
):
    """Mettre à jour un acteur"""
    try:
        actor = db.query(Actor).filter(
            and_(Actor.id == actor_id, Actor.sous_secteur == secteur)
        ).first()
        
        if not actor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Acteur non trouvé"
            )
        
        # Mettre à jour les champs modifiés
        update_data = actor_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(actor, field, value)
        
        actor.updated_at = datetime.now()
        db.commit()
        db.refresh(actor)
        
        # Réponse enrichie
        nb_indicateurs = db.query(IndicateurValeur).filter(
            IndicateurValeur.actor_id == actor.id
        ).count()
        
        derniere_saisie = db.query(func.max(IndicateurValeur.created_at)).filter(
            IndicateurValeur.actor_id == actor.id
        ).scalar()
        
        actor_response = ActorResponse.from_orm(actor)
        actor_response.nombre_indicateurs = nb_indicateurs
        actor_response.derniere_saisie = derniere_saisie
        
        logger.info(f"Acteur mis à jour: {actor.id}")
        return actor_response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur mise à jour acteur {actor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la mise à jour de l'acteur"
        )


@router.delete("/{secteur}/actors/{actor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_actor(
    secteur: SousSecteursEnum,
    actor_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sector_access: bool = Depends(verify_sector_access)
):
    """Supprimer un acteur (soft delete)"""
    try:
        actor = db.query(Actor).filter(
            and_(Actor.id == actor_id, Actor.sous_secteur == secteur)
        ).first()
        
        if not actor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Acteur non trouvé"
            )
        
        # Soft delete
        actor.is_active = False
        actor.updated_at = datetime.now()
        db.commit()
        
        logger.info(f"Acteur supprimé (soft): {actor.id}")
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur suppression acteur {actor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la suppression de l'acteur"
        )


# ==========================================
# ENDPOINTS GESTION DES INDICATEURS
# ==========================================

@router.get("/{secteur}/actors/{actor_id}/indicators", response_model=List[IndicateurResponse])
async def list_actor_indicators(
    secteur: SousSecteursEnum,
    actor_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sector_access: bool = Depends(verify_sector_access),
    categorie: Optional[CategorieIndicateurEnum] = Query(None, description="Filtrer par catégorie"),
    annee: Optional[int] = Query(None, description="Filtrer par année"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Lister les indicateurs d'un acteur"""
    try:
        # Vérifier que l'acteur existe et appartient au bon secteur
        actor = db.query(Actor).filter(
            and_(Actor.id == actor_id, Actor.sous_secteur == secteur)
        ).first()
        
        if not actor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Acteur non trouvé"
            )
        
        query = db.query(IndicateurValeur).filter(
            IndicateurValeur.actor_id == actor_id
        )
        
        # Filtres
        if categorie:
            query = query.filter(IndicateurValeur.categorie == categorie)
        if annee:
            query = query.filter(IndicateurValeur.annee == annee)
        
        # Tri par date (plus récents en premier)
        query = query.order_by(desc(IndicateurValeur.date_debut))
        
        # Pagination
        indicateurs = query.offset(offset).limit(limit).all()
        
        return [IndicateurResponse.from_orm(ind) for ind in indicateurs]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération indicateurs acteur {actor_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération des indicateurs"
        )


@router.post("/{secteur}/actors/{actor_id}/indicators", response_model=IndicateurResponse, status_code=status.HTTP_201_CREATED)
async def create_actor_indicator(
    secteur: SousSecteursEnum,
    actor_id: UUID,
    indicator_data: IndicateurCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sector_access: bool = Depends(verify_sector_access),
    calculation_service: CalculationService = Depends(get_calculation_service)
):
    """Créer un nouvel indicateur pour un acteur"""
    try:
        # Vérifier que l'acteur existe
        actor = db.query(Actor).filter(
            and_(Actor.id == actor_id, Actor.sous_secteur == secteur)
        ).first()
        
        if not actor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Acteur non trouvé"
            )
        
        # Valider qu'une seule valeur est fournie
        valeurs_fournies = sum([
            indicator_data.valeur_numerique is not None,
            indicator_data.valeur_texte is not None,
            indicator_data.valeur_booleen is not None,
            indicator_data.valeur_json is not None
        ])
        
        if valeurs_fournies != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Exactement une valeur doit être fournie (numerique, texte, booleen ou json)"
            )
        
        # Créer l'indicateur
        indicateur = IndicateurValeur(
            actor_id=actor_id,
            sous_secteur=secteur,
            annee=indicator_data.date_debut.year,
            mois=indicator_data.date_debut.month,
            created_by=current_user.id,
            **indicator_data.dict()
        )
        
        db.add(indicateur)
        db.commit()
        db.refresh(indicateur)
        
        # Déclencher l'analyse d'alertes en arrière-plan
        try:
            # TODO: Implémenter l'analyse asynchrone des alertes
            # await alert_service.analyser_nouvel_indicateur(indicateur)
            pass
        except Exception as alert_error:
            logger.warning(f"Erreur analyse alerte: {alert_error}")
        
        logger.info(f"Indicateur créé: {indicateur.id} pour acteur {actor_id}")
        return IndicateurResponse.from_orm(indicateur)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erreur création indicateur: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la création de l'indicateur"
        )


@router.post("/{secteur}/actors/{actor_id}/indicators/calculate/{indicator_type}")
async def calculate_derived_indicator(
    secteur: SousSecteursEnum,
    actor_id: UUID,
    indicator_type: str,
    periode: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sector_access: bool = Depends(verify_sector_access),
    calculation_service: CalculationService = Depends(get_calculation_service)
):
    """Calculer un indicateur dérivé pour un acteur"""
    try:
        # Vérifier que l'acteur existe
        actor = db.query(Actor).filter(
            and_(Actor.id == actor_id, Actor.sous_secteur == secteur)
        ).first()
        
        if not actor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Acteur non trouvé"
            )
        
        # Dispatcher selon le type de calcul
        result = None
        
        if indicator_type == "seuil_pauvrete":
            result = calculation_service.calculer_seuil_pauvrete(actor, periode)
        elif indicator_type == "vulnerabilite_saisonniere":
            result = calculation_service.evaluer_vulnerabilite_saisonniere(actor, periode.year)
        elif indicator_type == "diversite_alimentaire":
            result = calculation_service.calculer_diversite_alimentaire(actor, periode)
        elif indicator_type == "marge_brute" and secteur == SousSecteursEnum.VEGETAL:
            result = calculation_service.calculer_marge_brute_vegetal(actor, periode)
        elif indicator_type == "benefice_elevage" and secteur == SousSecteursEnum.ANIMAL:
            result = calculation_service.calculer_benefice_elevage(actor, periode)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Type de calcul non supporté: {indicator_type} pour le secteur {secteur}"
            )
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossible de calculer l'indicateur avec les données disponibles"
            )
        
        return {
            "indicator_type": indicator_type,
            "actor_id": actor_id,
            "periode": periode,
            "result": result,
            "calculated_at": datetime.now()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur calcul indicateur {indicator_type}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors du calcul de l'indicateur"
        )


# ==========================================
# FONCTIONS UTILITAIRES
# ==========================================

def _get_roles_for_secteur(secteur: SousSecteursEnum) -> List[ActorRoleEnum]:
    """Obtenir la liste des rôles valides pour un secteur"""
    mapping = {
        SousSecteursEnum.VEGETAL: [
            ActorRoleEnum.PRODUCTEUR_INDIVIDUEL,
            ActorRoleEnum.EXPLOITATION_FAMILIALE,
            ActorRoleEnum.COOPERATIVE_AGRICOLE,
            ActorRoleEnum.TRANSFORMATEUR_ARTISANAL,
            ActorRoleEnum.TRANSFORMATEUR_SEMI_INDUSTRIEL,
            ActorRoleEnum.COLLECTEUR,
            ActorRoleEnum.COMMERCANT,
            ActorRoleEnum.TRAVAILLEUR_SAISONNIER,
            ActorRoleEnum.FEMME_TRANSFORMATRICE,
            ActorRoleEnum.JEUNE_ENTREPRENEUR
        ],
        SousSecteursEnum.ANIMAL: [
            ActorRoleEnum.ELEVEUR_BOVINS,
            ActorRoleEnum.ELEVEUR_OVINS,
            ActorRoleEnum.ELEVEUR_CAPRINS,
            ActorRoleEnum.ELEVEUR_VOLAILLES,
            ActorRoleEnum.ELEVEUR_PORCINS,
            ActorRoleEnum.COOPERATIVE_ELEVEURS,
            ActorRoleEnum.TRANSFORMATEUR_LAITIER,
            ActorRoleEnum.ABATTOIR,
            ActorRoleEnum.COMMERCANT_BETAIL,
            ActorRoleEnum.BOUCHER,
            ActorRoleEnum.TECHNICIEN_VETERINAIRE
        ],
        SousSecteursEnum.HALIEUTIQUE: [
            ActorRoleEnum.PECHEUR_ARTISANAL,
            ActorRoleEnum.PECHEUR_INDUSTRIEL,
            ActorRoleEnum.MAREYEUR,
            ActorRoleEnum.TRANSFORMATEUR_FUMEUR,
            ActorRoleEnum.TRANSFORMATEUR_SECHEUR,
            ActorRoleEnum.CONSERVEUR,
            ActorRoleEnum.FEMME_COMMERCANTE_POISSON,
            ActorRoleEnum.COOPERATIVE_AQUACOLE
        ],
        SousSecteursEnum.FORESTIER: [
            ActorRoleEnum.EXPLOITANT_FORESTIER,
            ActorRoleEnum.COLLECTEUR_PFNL,
            ActorRoleEnum.CHARBONNIER,
            ActorRoleEnum.ARTISAN_BOIS,
            ActorRoleEnum.SCIEUR,
            ActorRoleEnum.COOPERATIVE_AGROFORESTERIE,
            ActorRoleEnum.TRANSFORMATEUR_PFNL
        ]
    }
    
    return mapping.get(secteur, [])


async def _create_specialized_profile(actor: Actor, secteur: SousSecteursEnum, db: Session):
    """Créer un profil spécialisé selon le secteur"""
    try:
        if secteur == SousSecteursEnum.VEGETAL and actor.role in [
            ActorRoleEnum.PRODUCTEUR_INDIVIDUEL, ActorRoleEnum.EXPLOITATION_FAMILIALE
        ]:
            profil = ProducteurVegetal(id=actor.id)
            db.add(profil)
        
        elif secteur == SousSecteursEnum.ANIMAL and "ELEVEUR" in actor.role.value.upper():
            profil = EleveurAnimal(id=actor.id)
            db.add(profil)
        
        elif secteur == SousSecteursEnum.HALIEUTIQUE and "PECHEUR" in actor.role.value.upper():
            profil = PecheurHalieutique(id=actor.id)
            db.add(profil)
        
        elif secteur == SousSecteursEnum.FORESTIER:
            profil = ExploitantForestier(id=actor.id)
            db.add(profil)
        
    except Exception as e:
        logger.warning(f"Erreur création profil spécialisé: {e}")