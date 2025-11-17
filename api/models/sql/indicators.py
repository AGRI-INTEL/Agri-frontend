"""
Modèles SQLAlchemy pour tous les indicateurs identifiés dans le PDF
Système d'historisation des valeurs d'indicateurs par acteur et période
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Index, Integer,
                       Numeric, String, Text, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.models.sql.base import Base
from api.models.sql.actors import SousSecteursEnum


class CategorieIndicateurEnum(str, enum.Enum):
    """Catégories principales d'indicateurs"""
    COMPTES_EXPLOITATION = "comptes_exploitation"
    REVENUS = "revenus"
    PAUVRETE = "pauvrete"
    NUTRITION = "nutrition"
    SANTE = "sante"
    BIEN_ETRE = "bien_etre"


class TypeIndicateurEnum(str, enum.Enum):
    """Types spécifiques d'indicateurs par catégorie"""
    
    # Comptes d'exploitation
    CHIFFRE_AFFAIRES = "chiffre_affaires"
    CHARGES_EXPLOITATION = "charges_exploitation"
    MARGE_BRUTE = "marge_brute"
    VALEUR_AJOUTEE = "valeur_ajoutee"
    AMORTISSEMENT = "amortissement"
    BENEFICE_NET = "benefice_net"
    
    # Revenus
    REVENU_MENSUEL = "revenu_mensuel"
    REVENU_TRIMESTRIEL = "revenu_trimestriel"
    REVENU_SEMESTRIEL = "revenu_semestriel"
    REVENU_ANNUEL = "revenu_annuel"
    REVENU_TOTAL_MENAGE = "revenu_total_menage"
    PART_REVENU_AGRICOLE = "part_revenu_agricole"
    
    # Pauvreté
    SEUIL_PAUVRETE = "seuil_pauvrete"
    VULNERABILITE_SAISONNIERE = "vulnerabilite_saisonniere"
    PART_BETAIL_PATRIMOINE = "part_betail_patrimoine"
    RESILIENCE_CHOCS = "resilience_chocs"
    DEPENDANCE_CREDIT = "dependance_credit"
    ENDETTEMENT = "endettement"
    DEPENDANCE_RESSOURCES_NATURELLES = "dependance_ressources_naturelles"
    
    # Nutrition
    DIVERSITE_ALIMENTAIRE = "diversite_alimentaire"
    CONSOMMATION_PRODUITS_FRAIS = "consommation_produits_frais"
    TAUX_MALNUTRITION_LEGERE = "taux_malnutrition_legere"
    TAUX_MALNUTRITION_MODEREE = "taux_malnutrition_moderee"
    CONSOMMATION_PROTEINES_ANIMALES = "consommation_proteines_animales"
    CONSOMMATION_POISSON_MENAGE = "consommation_poisson_menage"
    APPORT_CALORIQUE_PFNL = "apport_calorique_pfnl"
    APPORT_PROTEIQUE_PFNL = "apport_proteique_pfnl"
    
    # Santé
    ACCES_SOINS = "acces_soins"
    FREQUENCE_MALADIES_TRAVAIL = "frequence_maladies_travail"
    ACCIDENTS_TRAVAIL = "accidents_travail"
    SANTE_REPRODUCTIVE_FEMMES = "sante_reproductive_femmes"
    ZOONOSES = "zoonoses"
    SECURITE_SANITAIRE_ALIMENTS = "securite_sanitaire_aliments"
    COUVERTURE_VETERINAIRE = "couverture_veterinaire"
    RISQUES_TRAVAIL_MER = "risques_travail_mer"
    HYGIENE_MANIPULATION_POISSON = "hygiene_manipulation_poisson"
    EXPOSITION_RISQUES_PHYSIQUES = "exposition_risques_physiques"
    MALADIES_RESPIRATOIRES = "maladies_respiratoires"
    
    # Bien-être
    SATISFACTION_PROFESSIONNELLE = "satisfaction_professionnelle"
    TEMPS_TRAVAIL = "temps_travail"
    SECURITE_SOCIALE = "securite_sociale"
    ACCES_ELECTRICITE = "acces_electricite"
    ACCES_EAU_POTABLE = "acces_eau_potable"
    SCOLARISATION_ENFANTS = "scolarisation_enfants"
    EMPLOI_RURAL = "emploi_rural"
    STATUT_SOCIAL = "statut_social"
    AUTONOMISATION_ECONOMIQUE = "autonomisation_economique"
    ACCES_SERVICES_PORTUAIRES = "acces_services_portuaires"
    QUALITE_LOGEMENT = "qualite_logement"
    EDUCATION_ENFANTS = "education_enfants"
    EMPLOI_FEMMES = "emploi_femmes"
    SECURITE_FONCIERE = "securite_fonciere"
    DURABILITE_ENVIRONNEMENTALE = "durabilite_environnementale"
    REBOISEMENT_COMMUNAUTAIRE = "reboisement_communautaire"


class UniteIndicateurEnum(str, enum.Enum):
    """Unités de mesure des indicateurs"""
    XOF = "XOF"  # Francs CFA
    EUR = "EUR"
    USD = "USD"
    POURCENTAGE = "pourcentage"
    SCORE_1_5 = "score_1_5"  # Échelle de 1 à 5
    SCORE_1_10 = "score_1_10"  # Échelle de 1 à 10
    BINAIRE = "binaire"  # 0/1 ou Oui/Non
    NOMBRE = "nombre"  # Valeur numérique simple
    JOURS_PAR_MOIS = "jours_par_mois"
    HEURES_PAR_SEMAINE = "heures_par_semaine"
    FREQUENCE_ANNUELLE = "frequence_annuelle"
    KG_PAR_PERSONNE_MOIS = "kg_par_personne_mois"
    NOMBRE_REPAS_PAR_SEMAINE = "nombre_repas_par_semaine"


class PeriodeIndicateurEnum(str, enum.Enum):
    """Périodes de mesure des indicateurs"""
    MENSUELLE = "mensuelle"
    TRIMESTRIELLE = "trimestrielle"
    SEMESTRIELLE = "semestrielle"
    ANNUELLE = "annuelle"
    SAISONNIERE = "saisonniere"  # hivernage, saison sèche
    PONCTUELLE = "ponctuelle"  # mesure unique


# =============================================
# MODÈLE PRINCIPAL DES VALEURS D'INDICATEURS
# =============================================

class IndicateurValeur(Base):
    """
    Table centrale pour stocker toutes les valeurs d'indicateurs
    avec historisation complète
    """
    __tablename__ = "indicateur_valeurs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Référence à l'acteur
    actor_id = Column(UUID(as_uuid=True), ForeignKey('actors.id'), nullable=False)
    
    # Type et classification de l'indicateur
    sous_secteur = Column(Enum(SousSecteursEnum), nullable=False, index=True)
    categorie = Column(Enum(CategorieIndicateurEnum), nullable=False, index=True)
    type_indicateur = Column(Enum(TypeIndicateurEnum), nullable=False, index=True)
    
    # Valeur de l'indicateur
    valeur_numerique = Column(Numeric(15, 4), nullable=True)  # Pour les valeurs numériques
    valeur_texte = Column(String(500), nullable=True)  # Pour les valeurs textuelles
    valeur_booleen = Column(Boolean, nullable=True)  # Pour les valeurs binaires
    valeur_json = Column(JSONB, nullable=True)  # Pour les structures complexes
    
    # Métadonnées de la valeur
    unite = Column(Enum(UniteIndicateurEnum), nullable=False)
    periode = Column(Enum(PeriodeIndicateurEnum), nullable=False)
    
    # Période de validité
    date_debut = Column(Date, nullable=False)
    date_fin = Column(Date, nullable=True)
    annee = Column(Integer, nullable=False, index=True)
    mois = Column(Integer, nullable=True, index=True)  # 1-12
    saison = Column(String(20), nullable=True)  # "hivernage", "saison_seche"
    
    # Contexte et métadonnées
    contexte = Column(JSONB, nullable=True)  # Informations contextuelles
    commentaire = Column(Text, nullable=True)
    source = Column(String(100), nullable=True)  # enquête, auto-déclaré, calculé, etc.
    
    # Qualité et validation
    qualite_donnee = Column(Float, default=1.0, nullable=False)  # 0.0 à 1.0
    is_valide = Column(Boolean, default=True, nullable=False)
    validee_par = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    date_validation = Column(DateTime(timezone=True), nullable=True)
    
    # Calculs automatiques
    is_calculee = Column(Boolean, default=False, nullable=False)
    formule_calcul = Column(Text, nullable=True)
    indicateurs_source = Column(JSONB, nullable=True)  # IDs des indicateurs utilisés pour le calcul
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    # Relations
    actor = relationship("Actor", back_populates="indicateurs")
    validateur = relationship("User", foreign_keys=[validee_par])
    createur = relationship("User", foreign_keys=[created_by])
    
    __table_args__ = (
        Index('ix_indicateur_actor_type_periode', 'actor_id', 'type_indicateur', 'date_debut'),
        Index('ix_indicateur_secteur_annee', 'sous_secteur', 'annee'),
        Index('ix_indicateur_categorie_annee', 'categorie', 'annee'),
        UniqueConstraint('actor_id', 'type_indicateur', 'date_debut', 'date_fin', 
                        name='uq_indicateur_actor_type_periode'),
        {'comment': 'Historisation complète des valeurs d\'indicateurs par acteur'}
    )

    def __repr__(self):
        return f"<IndicateurValeur {self.type_indicateur.value} - {self.valeur_numerique}>"


# =============================================
# MODÈLES SPÉCIALISÉS PAR SOUS-SECTEUR
# =============================================

class IndicateurVegetal(Base):
    """
    Indicateurs spécifiques au sous-secteur végétal
    avec informations détaillées sur les cultures
    """
    __tablename__ = "indicateurs_vegetal"
    
    id = Column(UUID(as_uuid=True), ForeignKey('indicateur_valeurs.id'), primary_key=True)
    
    # Détails spécifiques aux cultures
    culture_principale = Column(String(100), nullable=True)
    variete = Column(String(100), nullable=True)
    superficie_concernee_ha = Column(Numeric(10, 2), nullable=True)
    rendement_ha = Column(Numeric(10, 2), nullable=True)
    
    # Conditions météorologiques
    pluviometrie_mm = Column(Numeric(8, 2), nullable=True)
    temperature_moyenne = Column(Numeric(4, 1), nullable=True)
    
    # Techniques agricoles
    utilise_engrais = Column(Boolean, default=False)
    utilise_pesticides = Column(Boolean, default=False)
    pratique_biologique = Column(Boolean, default=False)
    
    # Relation avec l'indicateur principal
    indicateur = relationship("IndicateurValeur")


class IndicateurAnimal(Base):
    """
    Indicateurs spécifiques au sous-secteur animal
    avec informations sur le cheptel
    """
    __tablename__ = "indicateurs_animal"
    
    id = Column(UUID(as_uuid=True), ForeignKey('indicateur_valeurs.id'), primary_key=True)
    
    # Détails du cheptel
    type_animal = Column(String(50), nullable=True)  # bovin, ovin, caprin, etc.
    race = Column(String(100), nullable=True)
    age_moyen_cheptel = Column(Integer, nullable=True)
    
    # Production
    production_lait_litres_jour = Column(Numeric(8, 2), nullable=True)
    nombre_naissances = Column(Integer, nullable=True)
    taux_mortalite_pct = Column(Numeric(5, 2), nullable=True)
    
    # Santé animale
    vaccinations_effectuees = Column(Boolean, default=False)
    traitements_veterinaires = Column(JSONB, nullable=True)
    
    # Relation avec l'indicateur principal
    indicateur = relationship("IndicateurValeur")


class IndicateurHalieutique(Base):
    """
    Indicateurs spécifiques au sous-secteur halieutique
    avec informations sur la pêche
    """
    __tablename__ = "indicateurs_halieutique"
    
    id = Column(UUID(as_uuid=True), ForeignKey('indicateur_valeurs.id'), primary_key=True)
    
    # Détails de la pêche
    zone_peche = Column(String(100), nullable=True)
    espece_principale = Column(String(100), nullable=True)
    technique_peche = Column(String(100), nullable=True)
    
    # Production
    capture_kg_sortie = Column(Numeric(10, 2), nullable=True)
    nombre_sorties_mois = Column(Integer, nullable=True)
    duree_moyenne_sortie_heures = Column(Numeric(4, 1), nullable=True)
    
    # Conditions
    etat_mer = Column(String(20), nullable=True)  # calme, agitée, houleuse
    saison_peche = Column(String(20), nullable=True)
    
    # Transformation et conservation
    methode_conservation = Column(String(50), nullable=True)  # frais, fumé, séché, congelé
    perte_post_capture_pct = Column(Numeric(5, 2), nullable=True)
    
    # Relation avec l'indicateur principal
    indicateur = relationship("IndicateurValeur")


class IndicateurForestier(Base):
    """
    Indicateurs spécifiques au sous-secteur forestier
    avec informations sur les produits forestiers
    """
    __tablename__ = "indicateurs_forestier"
    
    id = Column(UUID(as_uuid=True), ForeignKey('indicateur_valeurs.id'), primary_key=True)
    
    # Type de produits forestiers
    type_produit = Column(String(50), nullable=True)  # PFNL, bois, charbon
    espece_arbre = Column(String(100), nullable=True)
    partie_utilisee = Column(String(50), nullable=True)  # fruit, feuille, écorce, bois
    
    # Récolte/extraction
    quantite_recoltee_kg = Column(Numeric(10, 2), nullable=True)
    periode_recolte = Column(String(50), nullable=True)
    methode_recolte = Column(String(100), nullable=True)
    
    # Durabilité
    pratique_durable = Column(Boolean, default=False)
    regeneration_naturelle = Column(Boolean, default=True)
    reboisement_effectue = Column(Boolean, default=False)
    
    # Transformation
    niveau_transformation = Column(String(50), nullable=True)  # brut, semi-transformé, transformé
    valeur_ajoutee_transformation_pct = Column(Numeric(5, 2), nullable=True)
    
    # Relation avec l'indicateur principal
    indicateur = relationship("IndicateurValeur")


# =============================================
# DÉFINITIONS ET FORMULES D'INDICATEURS
# =============================================

class DefinitionIndicateur(Base):
    """
    Définitions standardisées des indicateurs avec formules de calcul
    """
    __tablename__ = "definition_indicateurs"
    
    id = Column(Integer, primary_key=True)
    type_indicateur = Column(Enum(TypeIndicateurEnum), unique=True, nullable=False)
    
    # Définition
    nom_display = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    objectif = Column(Text, nullable=True)
    interpretation = Column(Text, nullable=True)
    
    # Classification
    categorie = Column(Enum(CategorieIndicateurEnum), nullable=False)
    sous_secteurs_applicables = Column(JSONB, nullable=False)  # ["vegetal", "animal"]
    
    # Spécifications techniques
    unite_defaut = Column(Enum(UniteIndicateurEnum), nullable=False)
    periode_defaut = Column(Enum(PeriodeIndicateurEnum), nullable=False)
    type_valeur = Column(String(20), nullable=False)  # numerique, texte, booleen, json
    
    # Formule de calcul (pour indicateurs calculés)
    formule = Column(Text, nullable=True)
    indicateurs_requis = Column(JSONB, nullable=True)  # Liste des indicateurs nécessaires
    
    # Validation
    valeur_min = Column(Numeric(15, 4), nullable=True)
    valeur_max = Column(Numeric(15, 4), nullable=True)
    valeurs_valides = Column(JSONB, nullable=True)  # Liste des valeurs autorisées
    
    # Métadonnées
    source_reference = Column(String(200), nullable=True)
    version = Column(String(10), default="1.0", nullable=False)
    date_creation = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    __table_args__ = (
        Index('ix_definition_categorie', 'categorie'),
        {'comment': 'Définitions standardisées des indicateurs avec métadonnées'}
    )


# =============================================
# SEUILS ET ALERTES
# =============================================

class SeuilIndicateur(Base):
    """
    Seuils d'alerte pour les indicateurs
    """
    __tablename__ = "seuils_indicateurs"
    
    id = Column(Integer, primary_key=True)
    type_indicateur = Column(Enum(TypeIndicateurEnum), nullable=False)
    sous_secteur = Column(Enum(SousSecteursEnum), nullable=True)
    
    # Contexte d'application
    pays = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    role_acteur = Column(String(50), nullable=True)
    
    # Seuils
    seuil_critique_min = Column(Numeric(15, 4), nullable=True)
    seuil_critique_max = Column(Numeric(15, 4), nullable=True)
    seuil_alerte_min = Column(Numeric(15, 4), nullable=True)
    seuil_alerte_max = Column(Numeric(15, 4), nullable=True)
    seuil_optimal_min = Column(Numeric(15, 4), nullable=True)
    seuil_optimal_max = Column(Numeric(15, 4), nullable=True)
    
    # Messages d'alerte
    message_critique = Column(Text, nullable=True)
    message_alerte = Column(Text, nullable=True)
    message_optimal = Column(Text, nullable=True)
    
    # Actions recommandées
    actions_critiques = Column(JSONB, nullable=True)
    actions_preventives = Column(JSONB, nullable=True)
    
    # Validité
    date_debut = Column(Date, nullable=False)
    date_fin = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    __table_args__ = (
        Index('ix_seuil_indicateur_secteur', 'type_indicateur', 'sous_secteur'),
        {'comment': 'Seuils d\'alerte configurables par indicateur et contexte'}
    )


# =============================================
# VUES MATÉRIALISÉES POUR AGRÉGATIONS
# =============================================

class VueIndicateursAgregees(Base):
    """
    Vue matérialisée pour les agrégations d'indicateurs
    Mise à jour par tâches planifiées
    """
    __tablename__ = "vue_indicateurs_agregees"
    
    id = Column(Integer, primary_key=True)
    
    # Dimensions d'agrégation
    sous_secteur = Column(Enum(SousSecteursEnum), nullable=False, index=True)
    type_indicateur = Column(Enum(TypeIndicateurEnum), nullable=False, index=True)
    categorie = Column(Enum(CategorieIndicateurEnum), nullable=False, index=True)
    
    # Contexte géographique
    pays = Column(String(100), nullable=False, index=True)
    region = Column(String(100), nullable=True, index=True)
    departement = Column(String(100), nullable=True)
    
    # Période
    annee = Column(Integer, nullable=False, index=True)
    mois = Column(Integer, nullable=True, index=True)
    
    # Statistiques agrégées
    nombre_acteurs = Column(Integer, nullable=False)
    valeur_moyenne = Column(Numeric(15, 4), nullable=True)
    valeur_mediane = Column(Numeric(15, 4), nullable=True)
    valeur_min = Column(Numeric(15, 4), nullable=True)
    valeur_max = Column(Numeric(15, 4), nullable=True)
    ecart_type = Column(Numeric(15, 4), nullable=True)
    
    # Répartition par déciles
    deciles = Column(JSONB, nullable=True)
    
    # Évolution
    evolution_mois_precedent_pct = Column(Numeric(8, 2), nullable=True)
    evolution_annee_precedente_pct = Column(Numeric(8, 2), nullable=True)
    
    # Métadonnées de l'agrégation
    date_calcul = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    qualite_moyenne = Column(Numeric(3, 2), nullable=False, default=1.0)
    
    __table_args__ = (
        Index('ix_agregees_secteur_type_periode', 'sous_secteur', 'type_indicateur', 'annee', 'mois'),
        UniqueConstraint('sous_secteur', 'type_indicateur', 'pays', 'region', 'annee', 'mois',
                        name='uq_agregees_unique'),
        {'comment': 'Vue matérialisée des indicateurs agrégés pour tableaux de bord'}
    )