"""
Service de calculs d'indicateurs dérivés et d'analyses avancées
Implémentation des formules métier pour les 4 sous-secteurs
"""

import logging
import statistics
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Union

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from api.models.sql.actors import Actor, SousSecteursEnum, ActorRoleEnum
from api.models.sql.indicators import (
    IndicateurValeur, CategorieIndicateurEnum, TypeIndicateurEnum,
    UniteIndicateurEnum, PeriodeIndicateurEnum
)

logger = logging.getLogger(__name__)


class CalculationService:
    """
    Service principal pour les calculs d'indicateurs dérivés
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.seuil_pauvrete_senegal = Decimal("65000")  # FCFA par mois (exemple)
        self.salaire_minimum = Decimal("52500")  # SMIG Sénégal 2024
    
    
    # ================================================
    # CALCULS TRANSVERSAUX (TOUS SECTEURS)
    # ================================================
    
    def calculer_seuil_pauvrete(self, actor: Actor, periode: date) -> Decimal:
        """
        Calcul du seuil de pauvreté contextualisé par région et taille du ménage
        """
        try:
            # Seuil de base (ligne de pauvreté nationale)
            seuil_base = self.seuil_pauvrete_senegal
            
            # Ajustement selon la taille du ménage
            taille_menage = actor.taille_menage or 1
            facteur_menage = Decimal("0.3") * (taille_menage - 1)  # +30% par personne additionnelle
            
            # Ajustement selon la région (coût de la vie)
            facteur_regional = self._get_facteur_regional(actor.region)
            
            seuil_ajuste = seuil_base * (1 + facteur_menage) * facteur_regional
            
            logger.info(f"Seuil pauvreté calculé: {seuil_ajuste} pour actor {actor.id}")
            return seuil_ajuste
            
        except Exception as e:
            logger.error(f"Erreur calcul seuil pauvreté: {e}")
            return self.seuil_pauvrete_senegal
    
    
    def evaluer_vulnerabilite_saisonniere(self, actor: Actor, annee: int) -> Dict[str, Union[Decimal, str]]:
        """
        Évaluation de la vulnérabilité saisonnière basée sur les revenus mensuels
        """
        try:
            # Récupérer les revenus mensuels de l'année
            revenus_mensuels = self.db.query(IndicateurValeur).filter(
                and_(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.type_indicateur == TypeIndicateurEnum.REVENU_MENSUEL,
                    IndicateurValeur.annee == annee
                )
            ).all()
            
            if len(revenus_mensuels) < 6:  # Minimum 6 mois de données
                return {"score": Decimal("0"), "niveau": "données_insuffisantes"}
            
            # Calcul de la variabilité des revenus
            valeurs = [r.valeur_numerique for r in revenus_mensuels if r.valeur_numerique]
            if not valeurs:
                return {"score": Decimal("0"), "niveau": "aucune_donnee"}
            
            moyenne = statistics.mean(valeurs)
            ecart_type = statistics.stdev(valeurs) if len(valeurs) > 1 else 0
            coefficient_variation = ecart_type / moyenne if moyenne > 0 else 0
            
            # Classification de la vulnérabilité
            if coefficient_variation < 0.2:
                niveau = "faible"
                score = Decimal("1")
            elif coefficient_variation < 0.5:
                niveau = "modérée"
                score = Decimal("2")
            elif coefficient_variation < 0.8:
                niveau = "élevée"
                score = Decimal("3")
            else:
                niveau = "très_élevée"
                score = Decimal("4")
            
            # Identifier les mois critiques
            seuil_critique = moyenne * 0.5  # 50% de la moyenne
            mois_critiques = [
                r.mois for r in revenus_mensuels 
                if r.valeur_numerique and r.valeur_numerique < seuil_critique
            ]
            
            return {
                "score": score,
                "niveau": niveau,
                "coefficient_variation": Decimal(str(coefficient_variation)),
                "mois_critiques": mois_critiques,
                "revenu_moyen": Decimal(str(moyenne)),
                "ecart_type": Decimal(str(ecart_type))
            }
            
        except Exception as e:
            logger.error(f"Erreur évaluation vulnérabilité saisonnière: {e}")
            return {"score": Decimal("0"), "niveau": "erreur"}
    
    
    def calculer_diversite_alimentaire(self, actor: Actor, periode: date) -> Dict[str, Union[int, List[str]]]:
        """
        Calcul du score de diversité alimentaire selon les standards FAO
        """
        try:
            # Groupes alimentaires standards (Score de Diversité Alimentaire des Ménages - SDAM)
            groupes_alimentaires = [
                "cereales_tubercules",
                "legumineuses_noix",
                "produits_laitiers", 
                "viandes_poissons_oeufs",
                "legumes_feuilles_vertes",
                "autres_legumes",
                "fruits_riches_vitamine_a",
                "autres_fruits",
                "huiles_graisses",
                "sucres_miel"
            ]
            
            # Récupérer les données de consommation
            mois_debut = periode.replace(day=1)
            mois_fin = (mois_debut + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            consommation_data = self.db.query(IndicateurValeur).filter(
                and_(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.categorie == CategorieIndicateurEnum.NUTRITION,
                    IndicateurValeur.date_debut >= mois_debut,
                    IndicateurValeur.date_fin <= mois_fin
                )
            ).all()
            
            # Analyser les groupes consommés (via valeur_json)
            groupes_consommes = []
            for indicateur in consommation_data:
                if indicateur.valeur_json and "groupes_alimentaires" in indicateur.valeur_json:
                    groupes_consommes.extend(indicateur.valeur_json["groupes_alimentaires"])
            
            # Calculer le score (nombre de groupes différents consommés)
            groupes_uniques = list(set(groupes_consommes))
            score = len(groupes_uniques)
            
            # Classification selon standards FAO
            if score >= 8:
                niveau = "élevée"
            elif score >= 6:
                niveau = "moyenne"
            elif score >= 4:
                niveau = "faible"
            else:
                niveau = "très_faible"
            
            return {
                "score": score,
                "niveau": niveau,
                "groupes_consommes": groupes_uniques,
                "groupes_manquants": [g for g in groupes_alimentaires if g not in groupes_uniques]
            }
            
        except Exception as e:
            logger.error(f"Erreur calcul diversité alimentaire: {e}")
            return {"score": 0, "niveau": "erreur", "groupes_consommes": [], "groupes_manquants": []}
    
    
    # ================================================
    # CALCULS SPÉCIFIQUES - SECTEUR VÉGÉTAL
    # ================================================
    
    def calculer_marge_brute_vegetal(self, actor: Actor, periode: date) -> Optional[Decimal]:
        """
        Calcul de la marge brute pour un producteur végétal
        Marge Brute = Chiffre d'Affaires - Charges Variables
        """
        try:
            # Récupérer le chiffre d'affaires
            ca = self._get_indicateur_value(
                actor, TypeIndicateurEnum.CHIFFRE_AFFAIRES, periode
            )
            
            # Récupérer les charges d'exploitation
            charges = self._get_indicateur_value(
                actor, TypeIndicateurEnum.CHARGES_EXPLOITATION, periode
            )
            
            if ca is not None and charges is not None:
                marge_brute = ca - charges
                
                # Enregistrer le résultat
                self._save_calculated_indicator(
                    actor=actor,
                    type_indicateur=TypeIndicateurEnum.MARGE_BRUTE,
                    valeur=marge_brute,
                    periode=periode,
                    formule="chiffre_affaires - charges_exploitation",
                    indicateurs_source=[TypeIndicateurEnum.CHIFFRE_AFFAIRES, TypeIndicateurEnum.CHARGES_EXPLOITATION]
                )
                
                return marge_brute
            
            return None
            
        except Exception as e:
            logger.error(f"Erreur calcul marge brute végétal: {e}")
            return None
    
    
    def calculer_rendement_culture(self, actor: Actor, culture: str, campagne: str) -> Optional[Decimal]:
        """
        Calcul du rendement par hectare pour une culture donnée
        """
        try:
            # Récupérer les données de production et superficie
            production_data = self.db.query(IndicateurValeur).filter(
                and_(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.contexte.contains({"culture": culture, "campagne": campagne})
                )
            ).first()
            
            if (production_data and 
                production_data.valeur_json and 
                "production_kg" in production_data.valeur_json and
                "superficie_ha" in production_data.valeur_json):
                
                production_kg = Decimal(str(production_data.valeur_json["production_kg"]))
                superficie_ha = Decimal(str(production_data.valeur_json["superficie_ha"]))
                
                if superficie_ha > 0:
                    rendement = production_kg / superficie_ha
                    
                    # Sauvegarder le rendement calculé
                    self._save_calculated_indicator(
                        actor=actor,
                        type_indicateur=TypeIndicateurEnum.CHIFFRE_AFFAIRES,  # À adapter selon l'enum
                        valeur=rendement,
                        periode=datetime.now().date(),
                        contexte={"culture": culture, "campagne": campagne, "unite": "kg_per_ha"},
                        formule="production_kg / superficie_ha"
                    )
                    
                    return rendement
            
            return None
            
        except Exception as e:
            logger.error(f"Erreur calcul rendement culture: {e}")
            return None
    
    
    # ================================================
    # CALCULS SPÉCIFIQUES - SECTEUR ANIMAL
    # ================================================
    
    def calculer_benefice_elevage(self, actor: Actor, periode: date) -> Optional[Decimal]:
        """
        Calcul du bénéfice net de l'élevage
        """
        try:
            # Récupérer tous les revenus de l'élevage
            revenus_elevage = self.db.query(IndicateurValeur).filter(
                and_(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.sous_secteur == SousSecteursEnum.ANIMAL,
                    IndicateurValeur.date_debut >= periode,
                    IndicateurValeur.date_fin <= periode.replace(day=28) + timedelta(days=4),  # Fin du mois
                    IndicateurValeur.categorie == CategorieIndicateurEnum.REVENUS
                )
            ).all()
            
            # Récupérer toutes les charges
            charges_elevage = self.db.query(IndicateurValeur).filter(
                and_(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.sous_secteur == SousSecteursEnum.ANIMAL,
                    IndicateurValeur.type_indicateur == TypeIndicateurEnum.CHARGES_EXPLOITATION,
                    IndicateurValeur.date_debut >= periode
                )
            ).all()
            
            # Calculs
            total_revenus = sum(r.valeur_numerique for r in revenus_elevage if r.valeur_numerique)
            total_charges = sum(c.valeur_numerique for c in charges_elevage if c.valeur_numerique)
            
            benefice_net = Decimal(str(total_revenus)) - Decimal(str(total_charges))
            
            # Sauvegarder
            self._save_calculated_indicator(
                actor=actor,
                type_indicateur=TypeIndicateurEnum.BENEFICE_NET,
                valeur=benefice_net,
                periode=periode,
                formule="somme(revenus_elevage) - somme(charges_elevage)"
            )
            
            return benefice_net
            
        except Exception as e:
            logger.error(f"Erreur calcul bénéfice élevage: {e}")
            return None
    
    
    def calculer_productivite_laitiere(self, actor: Actor, periode: date) -> Dict[str, Decimal]:
        """
        Calcul de la productivité laitière par vache
        """
        try:
            # Récupérer les données de production laitière
            production_lait = self._get_indicateur_value(
                actor, TypeIndicateurEnum.CHIFFRE_AFFAIRES, periode,  # À adapter
                contexte_filter={"produit": "lait"}
            )
            
            # Récupérer le nombre de vaches laitières
            if actor.eleveur_animal_profile:
                nombre_vaches = actor.eleveur_animal_profile.nombre_bovins or 0
            else:
                nombre_vaches = 0
            
            if production_lait and nombre_vaches > 0:
                productivite_par_vache = production_lait / Decimal(str(nombre_vaches))
                
                # Comparaison avec standards régionaux
                standard_regional = Decimal("8")  # litres/jour/vache (exemple Sahel)
                ecart_standard = ((productivite_par_vache - standard_regional) / standard_regional) * 100
                
                return {
                    "productivite_par_vache": productivite_par_vache,
                    "standard_regional": standard_regional,
                    "ecart_standard_pct": ecart_standard,
                    "nombre_vaches": Decimal(str(nombre_vaches))
                }
            
            return {"productivite_par_vache": Decimal("0")}
            
        except Exception as e:
            logger.error(f"Erreur calcul productivité laitière: {e}")
            return {"productivite_par_vache": Decimal("0")}
    
    
    # ================================================
    # CALCULS SPÉCIFIQUES - SECTEUR HALIEUTIQUE
    # ================================================
    
    def calculer_benefice_par_sortie_peche(self, actor: Actor, periode: date) -> Optional[Decimal]:
        """
        Calcul du bénéfice net par sortie de pêche
        """
        try:
            # Récupérer les données de pêche du mois
            revenus_peche = self._get_indicateur_value(
                actor, TypeIndicateurEnum.CHIFFRE_AFFAIRES, periode
            )
            
            charges_peche = self._get_indicateur_value(
                actor, TypeIndicateurEnum.CHARGES_EXPLOITATION, periode
            )
            
            # Nombre de sorties dans le mois
            nombre_sorties = self._get_indicateur_context_value(
                actor, periode, "nombre_sorties_mois", default=20
            )
            
            if revenus_peche and charges_peche and nombre_sorties > 0:
                benefice_mensuel = revenus_peche - charges_peche
                benefice_par_sortie = benefice_mensuel / Decimal(str(nombre_sorties))
                
                return benefice_par_sortie
            
            return None
            
        except Exception as e:
            logger.error(f"Erreur calcul bénéfice par sortie pêche: {e}")
            return None
    
    
    def evaluer_dependance_ressource_halieutique(self, actor: Actor, espece: str, annee: int) -> Dict[str, Union[Decimal, str]]:
        """
        Évaluation de la dépendance à une ressource halieutique spécifique
        """
        try:
            # Récupérer toutes les captures de l'année
            captures_totales = self.db.query(IndicateurValeur).filter(
                and_(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.annee == annee,
                    IndicateurValeur.contexte.contains({"type": "capture"})
                )
            ).all()
            
            # Calculer la part de l'espèce dans les captures totales
            captures_espece = [
                c.valeur_numerique for c in captures_totales
                if c.valeur_json and c.valeur_json.get("espece") == espece
            ]
            
            total_captures = sum(c.valeur_numerique for c in captures_totales if c.valeur_numerique)
            captures_espece_total = sum(captures_espece)
            
            if total_captures > 0:
                dependance_pct = (captures_espece_total / total_captures) * 100
                
                # Classification du niveau de dépendance
                if dependance_pct > 70:
                    niveau = "très_élevée"
                    risque = "critique"
                elif dependance_pct > 50:
                    niveau = "élevée"
                    risque = "élevé"
                elif dependance_pct > 30:
                    niveau = "modérée"
                    risque = "moyen"
                else:
                    niveau = "faible"
                    risque = "faible"
                
                return {
                    "dependance_pct": Decimal(str(dependance_pct)),
                    "niveau": niveau,
                    "risque": risque,
                    "captures_espece": Decimal(str(captures_espece_total)),
                    "captures_totales": Decimal(str(total_captures))
                }
            
            return {"dependance_pct": Decimal("0"), "niveau": "indéterminée"}
            
        except Exception as e:
            logger.error(f"Erreur évaluation dépendance ressource: {e}")
            return {"dependance_pct": Decimal("0"), "niveau": "erreur"}
    
    
    # ================================================
    # CALCULS SPÉCIFIQUES - SECTEUR FORESTIER  
    # ================================================
    
    def calculer_valeur_ajoutee_transformation_pfnl(self, actor: Actor, produit: str, periode: date) -> Optional[Decimal]:
        """
        Calcul de la valeur ajoutée par la transformation des PFNL
        """
        try:
            # Prix de vente du produit brut vs transformé
            prix_brut = self._get_indicateur_context_value(
                actor, periode, f"prix_brut_{produit}", default=0
            )
            
            prix_transforme = self._get_indicateur_context_value(
                actor, periode, f"prix_transforme_{produit}", default=0
            )
            
            # Coûts de transformation
            couts_transformation = self._get_indicateur_context_value(
                actor, periode, f"couts_transformation_{produit}", default=0
            )
            
            if prix_brut > 0 and prix_transforme > 0:
                valeur_ajoutee_brute = Decimal(str(prix_transforme)) - Decimal(str(prix_brut))
                valeur_ajoutee_nette = valeur_ajoutee_brute - Decimal(str(couts_transformation))
                
                # Pourcentage de valeur ajoutée
                valeur_ajoutee_pct = (valeur_ajoutee_nette / Decimal(str(prix_brut))) * 100
                
                return valeur_ajoutee_pct
            
            return None
            
        except Exception as e:
            logger.error(f"Erreur calcul valeur ajoutée PFNL: {e}")
            return None
    
    
    # ================================================
    # MÉTHODES UTILITAIRES
    # ================================================
    
    def _get_indicateur_value(self, actor: Actor, type_indicateur: TypeIndicateurEnum, 
                             periode: date, contexte_filter: Dict = None) -> Optional[Decimal]:
        """Récupérer la valeur d'un indicateur pour un acteur et une période donnée"""
        query = self.db.query(IndicateurValeur).filter(
            and_(
                IndicateurValeur.actor_id == actor.id,
                IndicateurValeur.type_indicateur == type_indicateur,
                IndicateurValeur.date_debut <= periode,
                IndicateurValeur.date_fin >= periode
            )
        )
        
        if contexte_filter:
            for key, value in contexte_filter.items():
                query = query.filter(IndicateurValeur.contexte.contains({key: value}))
        
        indicateur = query.first()
        return indicateur.valeur_numerique if indicateur else None
    
    
    def _get_indicateur_context_value(self, actor: Actor, periode: date, 
                                     context_key: str, default: Union[int, float] = 0) -> Union[int, float]:
        """Récupérer une valeur depuis le contexte d'un indicateur"""
        indicateur = self.db.query(IndicateurValeur).filter(
            and_(
                IndicateurValeur.actor_id == actor.id,
                IndicateurValeur.date_debut <= periode,
                IndicateurValeur.valeur_json.contains({context_key: None})
            )
        ).first()
        
        if indicateur and indicateur.valeur_json and context_key in indicateur.valeur_json:
            return indicateur.valeur_json[context_key]
        
        return default
    
    
    def _save_calculated_indicator(self, actor: Actor, type_indicateur: TypeIndicateurEnum,
                                  valeur: Decimal, periode: date, formule: str = None,
                                  indicateurs_source: List[TypeIndicateurEnum] = None,
                                  contexte: Dict = None):
        """Sauvegarder un indicateur calculé"""
        try:
            nouveau_indicateur = IndicateurValeur(
                actor_id=actor.id,
                sous_secteur=actor.sous_secteur,
                type_indicateur=type_indicateur,
                categorie=self._get_categorie_from_type(type_indicateur),
                valeur_numerique=valeur,
                unite=UniteIndicateurEnum.XOF,  # Par défaut, à adapter
                periode=PeriodeIndicateurEnum.MENSUELLE,
                date_debut=periode,
                date_fin=periode,
                annee=periode.year,
                mois=periode.month,
                is_calculee=True,
                formule_calcul=formule,
                indicateurs_source=indicateurs_source,
                contexte=contexte,
                source="calcul_automatique"
            )
            
            self.db.add(nouveau_indicateur)
            self.db.commit()
            
            logger.info(f"Indicateur calculé sauvegardé: {type_indicateur.value} = {valeur}")
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde indicateur calculé: {e}")
            self.db.rollback()
    
    
    def _get_facteur_regional(self, region: str) -> Decimal:
        """Obtenir le facteur d'ajustement régional pour le coût de la vie"""
        facteurs_regionaux = {
            "Dakar": Decimal("1.3"),
            "Thiès": Decimal("1.1"),
            "Saint-Louis": Decimal("1.0"),
            "Diourbel": Decimal("0.9"),
            "Kaolack": Decimal("0.9"),
            "Tambacounda": Decimal("0.8"),
            "Kolda": Decimal("0.8"),
            "Ziguinchor": Decimal("0.95"),
            "Louga": Decimal("0.85"),
            "Fatick": Decimal("0.85"),
            "Kaffrine": Decimal("0.8"),
            "Kédougou": Decimal("0.9"),
            "Matam": Decimal("0.8"),
            "Sédhiou": Decimal("0.8")
        }
        
        return facteurs_regionaux.get(region, Decimal("1.0"))
    
    
    def _get_categorie_from_type(self, type_indicateur: TypeIndicateurEnum) -> CategorieIndicateurEnum:
        """Mapper un type d'indicateur vers sa catégorie"""
        mapping = {
            TypeIndicateurEnum.CHIFFRE_AFFAIRES: CategorieIndicateurEnum.COMPTES_EXPLOITATION,
            TypeIndicateurEnum.CHARGES_EXPLOITATION: CategorieIndicateurEnum.COMPTES_EXPLOITATION,
            TypeIndicateurEnum.MARGE_BRUTE: CategorieIndicateurEnum.COMPTES_EXPLOITATION,
            TypeIndicateurEnum.BENEFICE_NET: CategorieIndicateurEnum.COMPTES_EXPLOITATION,
            TypeIndicateurEnum.REVENU_MENSUEL: CategorieIndicateurEnum.REVENUS,
            TypeIndicateurEnum.REVENU_ANNUEL: CategorieIndicateurEnum.REVENUS,
            TypeIndicateurEnum.SEUIL_PAUVRETE: CategorieIndicateurEnum.PAUVRETE,
            TypeIndicateurEnum.DIVERSITE_ALIMENTAIRE: CategorieIndicateurEnum.NUTRITION,
            # ... continuer le mapping
        }
        
        return mapping.get(type_indicateur, CategorieIndicateurEnum.COMPTES_EXPLOITATION)


# ================================================
# SERVICE D'AGRÉGATION POUR ANALYSES
# ================================================

class AggregationService:
    """Service pour les agrégations et analyses cross-sectorielles"""
    
    def __init__(self, db: Session):
        self.db = db
    
    
    def aggreger_par_secteur_region(self, sous_secteur: SousSecteursEnum, 
                                   region: str, annee: int) -> Dict[str, Dict]:
        """
        Agrégation des indicateurs par secteur et région pour une année donnée
        """
        try:
            # Requête d'agrégation avec GROUP BY
            query = self.db.query(
                IndicateurValeur.type_indicateur,
                func.count(IndicateurValeur.id).label('count'),
                func.avg(IndicateurValeur.valeur_numerique).label('moyenne'),
                func.min(IndicateurValeur.valeur_numerique).label('minimum'),
                func.max(IndicateurValeur.valeur_numerique).label('maximum'),
                func.stddev(IndicateurValeur.valeur_numerique).label('ecart_type')
            ).join(Actor).filter(
                and_(
                    IndicateurValeur.sous_secteur == sous_secteur,
                    Actor.region == region,
                    IndicateurValeur.annee == annee
                )
            ).group_by(IndicateurValeur.type_indicateur)
            
            resultats = {}
            for row in query.all():
                resultats[row.type_indicateur.value] = {
                    "nombre_acteurs": row.count,
                    "moyenne": float(row.moyenne) if row.moyenne else 0,
                    "minimum": float(row.minimum) if row.minimum else 0,
                    "maximum": float(row.maximum) if row.maximum else 0,
                    "ecart_type": float(row.ecart_type) if row.ecart_type else 0
                }
            
            return resultats
            
        except Exception as e:
            logger.error(f"Erreur agrégation secteur-région: {e}")
            return {}
    
    
    def calculer_evolution_temporelle(self, type_indicateur: TypeIndicateurEnum,
                                     sous_secteur: SousSecteursEnum,
                                     periode_mois: int = 12) -> List[Dict]:
        """
        Calcul de l'évolution temporelle d'un indicateur
        """
        try:
            date_debut = datetime.now() - timedelta(days=30 * periode_mois)
            
            query = self.db.query(
                IndicateurValeur.annee,
                IndicateurValeur.mois,
                func.avg(IndicateurValeur.valeur_numerique).label('valeur_moyenne'),
                func.count(IndicateurValeur.id).label('nombre_mesures')
            ).filter(
                and_(
                    IndicateurValeur.type_indicateur == type_indicateur,
                    IndicateurValeur.sous_secteur == sous_secteur,
                    IndicateurValeur.created_at >= date_debut
                )
            ).group_by(
                IndicateurValeur.annee, IndicateurValeur.mois
            ).order_by(
                IndicateurValeur.annee, IndicateurValeur.mois
            )
            
            evolution = []
            for row in query.all():
                evolution.append({
                    "periode": f"{row.annee}-{row.mois:02d}",
                    "valeur_moyenne": float(row.valeur_moyenne) if row.valeur_moyenne else 0,
                    "nombre_mesures": row.nombre_mesures
                })
            
            return evolution
            
        except Exception as e:
            logger.error(f"Erreur calcul évolution temporelle: {e}")
            return []