"""
Modèles SQLAlchemy pour tous les acteurs identifiés dans les 4 sous-secteurs agricoles
avec support multi-tenant et système RBAC (Role-Based Access Control)
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (Boolean, Column, DateTime, Enum, Float, ForeignKey, Index, Integer,
                       Numeric, String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.models.sql.base import Base


class SousSecteursEnum(str, enum.Enum):
    """Types de sous-secteurs agricoles"""
    VEGETAL = "vegetal"
    ANIMAL = "animal"
    HALIEUTIQUE = "halieutique"
    FORESTIER = "forestier"


class ActorRoleEnum(str, enum.Enum):
    """Rôles des acteurs dans le système"""
    # Rôles du sous-secteur végétal
    PRODUCTEUR_INDIVIDUEL = "producteur_individuel"
    EXPLOITATION_FAMILIALE = "exploitation_familiale"
    COOPERATIVE_AGRICOLE = "cooperative_agricole"
    TRANSFORMATEUR_ARTISANAL = "transformateur_artisanal"
    TRANSFORMATEUR_SEMI_INDUSTRIEL = "transformateur_semi_industriel"
    COLLECTEUR = "collecteur"
    COMMERCANT = "commercant"
    TRAVAILLEUR_SAISONNIER = "travailleur_saisonnier"
    FEMME_TRANSFORMATRICE = "femme_transformatrice"
    JEUNE_ENTREPRENEUR = "jeune_entrepreneur"
    
    # Rôles du sous-secteur animal
    ELEVEUR_BOVINS = "eleveur_bovins"
    ELEVEUR_OVINS = "eleveur_ovins"
    ELEVEUR_CAPRINS = "eleveur_caprins"
    ELEVEUR_VOLAILLES = "eleveur_volailles"
    ELEVEUR_PORCINS = "eleveur_porcins"
    COOPERATIVE_ELEVEURS = "cooperative_eleveurs"
    TRANSFORMATEUR_LAITIER = "transformateur_laitier"
    ABATTOIR = "abattoir"
    COMMERCANT_BETAIL = "commercant_betail"
    BOUCHER = "boucher"
    TECHNICIEN_VETERINAIRE = "technicien_veterinaire"
    
    # Rôles du sous-secteur halieutique
    PECHEUR_ARTISANAL = "pecheur_artisanal"
    PECHEUR_INDUSTRIEL = "pecheur_industriel"
    MAREYEUR = "mareyeur"  # collecteur de poisson
    TRANSFORMATEUR_FUMEUR = "transformateur_fumeur"
    TRANSFORMATEUR_SECHEUR = "transformateur_secheur"
    CONSERVEUR = "conserveur"
    FEMME_COMMERCANTE_POISSON = "femme_commercante_poisson"
    COOPERATIVE_AQUACOLE = "cooperative_aquacole"
    
    # Rôles du sous-secteur forestier
    EXPLOITANT_FORESTIER = "exploitant_forestier"
    COLLECTEUR_PFNL = "collecteur_pfnl"  # Produits Forestiers Non Ligneux
    CHARBONNIER = "charbonnier"
    ARTISAN_BOIS = "artisan_bois"
    SCIEUR = "scieur"
    COOPERATIVE_AGROFORESTERIE = "cooperative_agroforesterie"
    TRANSFORMATEUR_PFNL = "transformateur_pfnl"


# ==========================
# MODÈLE ACTEUR GÉNÉRIQUE
# ==========================

class Actor(Base):
    """
    Modèle générique pour tous les acteurs du système agricole
    Chaque acteur appartient à un sous-secteur spécifique
    """
    __tablename__ = "actors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Identification de base
    nom = Column(String(255), nullable=False)
    prenom = Column(String(255), nullable=True)
    nom_organisation = Column(String(500), nullable=True)
    
    # Classification
    sous_secteur = Column(Enum(SousSecteursEnum), nullable=False, index=True)
    role = Column(Enum(ActorRoleEnum), nullable=False, index=True)
    
    # Informations de contact
    telephone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    adresse = Column(Text, nullable=True)
    
    # Localisation géographique
    pays = Column(String(100), nullable=False, default="Sénégal")
    region = Column(String(100), nullable=True)
    departement = Column(String(100), nullable=True)
    commune = Column(String(100), nullable=True)
    village = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Informations démographiques
    age = Column(Integer, nullable=True)
    genre = Column(String(10), nullable=True)  # M/F/Autre
    niveau_education = Column(String(50), nullable=True)
    taille_menage = Column(Integer, nullable=True)
    
    # Informations socio-économiques de base
    statut_matrimonial = Column(String(20), nullable=True)
    nombre_enfants = Column(Integer, nullable=True, default=0)
    acces_electricite = Column(Boolean, default=False)
    acces_eau_potable = Column(Boolean, default=False)
    type_logement = Column(String(50), nullable=True)
    
    # Métadonnées extensibles par sous-secteur
    metadonnees_specifiques = Column(JSONB, nullable=True)
    
    # Gestion d'état
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    date_verification = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relation avec l'utilisateur système (optionnel - certains acteurs peuvent ne pas avoir de compte)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True, unique=True)
    user = relationship("User", back_populates="actor_profile")
    
    # Relations avec les indicateurs
    indicateurs = relationship("IndicateurValeur", back_populates="actor", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_actor_secteur_role', 'sous_secteur', 'role'),
        Index('ix_actor_location', 'pays', 'region', 'commune'),
        {'comment': 'Table principale des acteurs agricoles multi-sectoriels'}
    )

    def __repr__(self):
        return f"<Actor {self.nom} - {self.role.value} ({self.sous_secteur.value})>"


# ==========================
# MODÈLES SPÉCIALISÉS PAR SOUS-SECTEUR
# ==========================

class ProducteurVegetal(Base):
    """
    Extension spécialisée pour les producteurs du secteur végétal
    """
    __tablename__ = "producteurs_vegetal"
    
    id = Column(UUID(as_uuid=True), ForeignKey('actors.id'), primary_key=True)
    
    # Caractéristiques de l'exploitation
    superficie_totale_ha = Column(Numeric(10, 2), nullable=True)
    superficie_cultivee_ha = Column(Numeric(10, 2), nullable=True)
    nombre_parcelles = Column(Integer, nullable=True, default=1)
    
    # Types de cultures (JSON array)
    cultures_principales = Column(JSONB, nullable=True)  # ["maïs", "mil", "arachide"]
    cultures_secondaires = Column(JSONB, nullable=True)
    
    # Équipements et ressources
    possede_tracteur = Column(Boolean, default=False)
    possede_motoculteur = Column(Boolean, default=False)
    acces_irrigation = Column(Boolean, default=False)
    type_irrigation = Column(String(50), nullable=True)  # goutte-à-goutte, aspersion, etc.
    
    # Organisation et coopératives
    membre_cooperative = Column(Boolean, default=False)
    nom_cooperative = Column(String(255), nullable=True)
    
    # Relation avec l'acteur principal
    actor = relationship("Actor", back_populates="producteur_vegetal_profile")


class EleveurAnimal(Base):
    """
    Extension spécialisée pour les éleveurs du secteur animal
    """
    __tablename__ = "eleveurs_animal"
    
    id = Column(UUID(as_uuid=True), ForeignKey('actors.id'), primary_key=True)
    
    # Cheptel
    nombre_bovins = Column(Integer, nullable=True, default=0)
    nombre_ovins = Column(Integer, nullable=True, default=0)
    nombre_caprins = Column(Integer, nullable=True, default=0)
    nombre_volailles = Column(Integer, nullable=True, default=0)
    nombre_porcins = Column(Integer, nullable=True, default=0)
    
    # Spécialisation
    type_elevage = Column(String(50), nullable=True)  # extensif, intensif, semi-intensif
    orientation_principale = Column(String(50), nullable=True)  # lait, viande, mixte
    
    # Infrastructure
    possede_etable = Column(Boolean, default=False)
    type_habitat_animaux = Column(String(50), nullable=True)
    superficie_paturage_ha = Column(Numeric(10, 2), nullable=True)
    
    # Services vétérinaires
    acces_veterinaire = Column(Boolean, default=False)
    frequence_suivi_veterinaire = Column(String(50), nullable=True)
    
    # Relation avec l'acteur principal
    actor = relationship("Actor", back_populates="eleveur_animal_profile")


class PecheurHalieutique(Base):
    """
    Extension spécialisée pour les pêcheurs du secteur halieutique
    """
    __tablename__ = "pecheurs_halieutique"
    
    id = Column(UUID(as_uuid=True), ForeignKey('actors.id'), primary_key=True)
    
    # Type de pêche
    type_peche = Column(String(50), nullable=True)  # artisanale, industrielle
    zone_peche_principale = Column(String(100), nullable=True)
    
    # Équipements
    nombre_pirogues = Column(Integer, nullable=True, default=0)
    nombre_filets = Column(Integer, nullable=True, default=0)
    possede_moteur = Column(Boolean, default=False)
    puissance_moteur_cv = Column(Integer, nullable=True)
    
    # Organisation
    membre_groupement_pecheurs = Column(Boolean, default=False)
    nom_groupement = Column(String(255), nullable=True)
    
    # Infrastructure portuaire
    acces_quai_amenage = Column(Boolean, default=False)
    acces_chambre_froide = Column(Boolean, default=False)
    
    # Relation avec l'acteur principal
    actor = relationship("Actor", back_populates="pecheur_halieutique_profile")


class ExploitantForestier(Base):
    """
    Extension spécialisée pour les exploitants du secteur forestier
    """
    __tablename__ = "exploitants_forestier"
    
    id = Column(UUID(as_uuid=True), ForeignKey('actors.id'), primary_key=True)
    
    # Type d'exploitation
    type_exploitation = Column(String(50), nullable=True)  # PFNL, bois, mixte
    produits_principaux = Column(JSONB, nullable=True)  # ["karité", "miel", "noix"]
    
    # Superficie et ressources
    superficie_concession_ha = Column(Numeric(10, 2), nullable=True)
    a_titre_foncier = Column(Boolean, default=False)
    type_titre_foncier = Column(String(50), nullable=True)
    
    # Pratiques durables
    pratique_reboisement = Column(Boolean, default=False)
    certifie_durable = Column(Boolean, default=False)
    type_certification = Column(String(100), nullable=True)
    
    # Relation avec l'acteur principal
    actor = relationship("Actor", back_populates="exploitant_forestier_profile")


# Ajouter les relations back_populates à Actor
Actor.producteur_vegetal_profile = relationship("ProducteurVegetal", back_populates="actor", uselist=False)
Actor.eleveur_animal_profile = relationship("EleveurAnimal", back_populates="actor", uselist=False)
Actor.pecheur_halieutique_profile = relationship("PecheurHalieutique", back_populates="actor", uselist=False)  
Actor.exploitant_forestier_profile = relationship("ExploitantForestier", back_populates="actor", uselist=False)


# ==========================
# SYSTÈME RBAC ÉTENDU
# ==========================

class Role(Base):
    """Rôles système avec hiérarchie"""
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Hiérarchie des rôles
    parent_role_id = Column(Integer, ForeignKey('roles.id'), nullable=True)
    level = Column(Integer, default=0, nullable=False)  # 0=super admin, 1=admin, 2=manager, etc.
    
    # Secteur de compétence (optionnel)
    secteur_competence = Column(Enum(SousSecteursEnum), nullable=True)
    
    # Relations
    parent = relationship("Role", remote_side=[id], back_populates="children")
    children = relationship("Role", back_populates="parent")
    permissions = relationship("Permission", secondary="role_permissions", back_populates="roles")
    user_roles = relationship("UserRole", back_populates="role")


class Permission(Base):
    """Permissions granulaires"""
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)  # ex: "vegetal:producteur:create"
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Catégorisation
    module = Column(String(50), nullable=False)  # vegetal, animal, analytics, etc.
    resource = Column(String(50), nullable=False)  # producteur, indicateur, rapport, etc.
    action = Column(String(20), nullable=False)  # create, read, update, delete, export
    
    # Relations
    roles = relationship("Role", secondary="role_permissions", back_populates="permissions")


# Tables d'association
role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id'), primary_key=True),
    UniqueConstraint('role_id', 'permission_id', name='uq_role_permission')
)


class UserRole(Base):
    """Rôles attribués aux utilisateurs avec contexte optionnel"""
    __tablename__ = "user_roles"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=False)
    
    # Contexte optionnel (ex: responsable d'une région spécifique)
    contexte_secteur = Column(Enum(SousSecteursEnum), nullable=True)
    contexte_region = Column(String(100), nullable=True)
    contexte_organisation = Column(String(255), nullable=True)
    
    # Période de validité
    date_debut = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    date_fin = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relations
    user = relationship("User")
    role = relationship("Role", back_populates="user_roles")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'role_id', 'contexte_secteur', 'contexte_region', 
                        name='uq_user_role_context'),
    )


# Mise à jour du modèle User pour les relations
def extend_user_model():
    """Fonction pour étendre le modèle User existant"""
    from api.models.sql.user import User
    
    # Ajout de nouvelles relations
    User.actor_profile = relationship("Actor", back_populates="user", uselist=False)
    User.user_roles = relationship("UserRole", back_populates="user")
    
    def has_permission(self, permission_name: str, contexte_secteur: Optional[str] = None) -> bool:
        """Vérifier si l'utilisateur a une permission spécifique"""
        # Logique de vérification des permissions
        # À implémenter avec les rôles hiérarchiques
        pass
    
    def get_secteurs_autorises(self) -> list[SousSecteursEnum]:
        """Retourner les secteurs auxquels l'utilisateur a accès"""
        secteurs = []
        for user_role in self.user_roles:
            if user_role.is_active and user_role.role.secteur_competence:
                secteurs.append(user_role.role.secteur_competence)
        return list(set(secteurs))
    
    User.has_permission = has_permission
    User.get_secteurs_autorises = get_secteurs_autorises

# Appel de la fonction d'extension
# extend_user_model()  # À décommenter après import des modèles