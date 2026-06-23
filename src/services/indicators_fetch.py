"""
Service multi-source pour récupérer automatiquement les indicateurs agricoles
Sources actives:
  - World Bank Data API (gratuite, sans clé) → ~20 indicateurs, 15 pays, 4 secteurs, 6 catégories
Sources planifiées:
  - FAOSTAT (API v2, nécessite JWT — cf. https://www.fao.org/faostat/en/#developer-portal)
"""

import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import List, Dict, Any, Optional, NamedTuple

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.sql.indicators import (
    IndicateurValeur,
    CategorieIndicateurEnum,
    TypeIndicateurEnum,
    UniteIndicateurEnum,
    PeriodeIndicateurEnum,
    SousSecteursEnum,
)
from api.models.sql.actors import Actor, ActorRoleEnum

# ─── Sources de données ───────────────────────────────────────────────────────

WORLD_BANK_BASE = "https://api.worldbank.org/v2"
FAOSTAT_BASE = "https://fenixservices.fao.org/faostat/api/v1"

# ─── Pays suivis ──────────────────────────────────────────────────────────────

TRACKED_COUNTRIES = [
    "TG", "SN", "GH", "NG", "CI", "BF", "ML", "CM", "GN", "BJ",
    "GM", "GW", "LR", "SL", "NE",
]

COUNTRY_NAMES = {
    "TG": "Togo", "SN": "Sénégal", "GH": "Ghana", "NG": "Nigeria",
    "CI": "Côte d'Ivoire", "BF": "Burkina Faso", "ML": "Mali",
    "CM": "Cameroun", "GN": "Guinée", "BJ": "Bénin",
    "GM": "Gambie", "GW": "Guinée-Bissau", "LR": "Liberia",
    "SL": "Sierra Leone", "NE": "Niger",
}

# ─── Définition des indicateurs ───────────────────────────────────────────────
# Chaque entrée: code WB → (nom, secteur, catégorie, type, unité, source_label)

class IndicatorDef(NamedTuple):
    name: str
    sector: SousSecteursEnum
    category: CategorieIndicateurEnum
    indicator_type: TypeIndicateurEnum
    unit: UniteIndicateurEnum
    source_label: str

WB_INDICATORS: dict[str, IndicatorDef] = {
    # ─── Végétal — 10 indicateurs ──────────────────────────────────────────────
    "AG.LND.AGRI.ZS": IndicatorDef(
        "Terres agricoles (% superficie)", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.CHIFFRE_AFFAIRES,
        UniteIndicateurEnum.POURCENTAGE, "World Bank",
    ),
    "AG.YLD.CREL.KG": IndicatorDef(
        "Rendement céréales (kg/ha)", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.REVENUS, TypeIndicateurEnum.REVENU_ANNUEL,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),
    "AG.PRD.FOOD.XD": IndicatorDef(
        "Indice production alimentaire", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.NUTRITION, TypeIndicateurEnum.DIVERSITE_ALIMENTAIRE,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),
    "NV.AGR.TOTL.ZS": IndicatorDef(
        "Valeur ajoutée agriculture (% PIB)", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.VALEUR_AJOUTEE,
        UniteIndicateurEnum.POURCENTAGE, "World Bank",
    ),
    "SL.AGR.EMPL.ZS": IndicatorDef(
        "Emploi agricole (% total)", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.BIEN_ETRE, TypeIndicateurEnum.EMPLOI_RURAL,
        UniteIndicateurEnum.POURCENTAGE, "World Bank",
    ),
    "AG.LND.IRIG.AG.ZS": IndicatorDef(
        "Terres irriguées", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.CHIFFRE_AFFAIRES,
        UniteIndicateurEnum.POURCENTAGE, "World Bank",
    ),
    "AG.CON.FERT.ZS": IndicatorDef(
        "Consommation d'engrais (kg/ha)", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.CHARGES_EXPLOITATION,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),
    "AG.PRD.CREL.MT": IndicatorDef(
        "Production céréalière (tonnes)", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.REVENUS, TypeIndicateurEnum.CHIFFRE_AFFAIRES,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),
    "AG.PRD.CROP.XD": IndicatorDef(
        "Indice production végétale", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.REVENUS, TypeIndicateurEnum.REVENU_ANNUEL,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),
    "AG.LND.CROP.ZS": IndicatorDef(
        "Terres cultivées permanentes", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.CHIFFRE_AFFAIRES,
        UniteIndicateurEnum.POURCENTAGE, "World Bank",
    ),

    # ─── Animal — 2 indicateurs ────────────────────────────────────────────────
    "AG.PRD.LVSK.XD": IndicatorDef(
        "Indice production animale", SousSecteursEnum.ANIMAL,
        CategorieIndicateurEnum.REVENUS, TypeIndicateurEnum.REVENU_ANNUEL,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),
    "EN.GHG.CH4.AG.MT.CE.AR5": IndicatorDef(
        "Émissions CH4 agricoles (Mt CO2e)", SousSecteursEnum.ANIMAL,
        CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.VALEUR_AJOUTEE,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),

    # ─── Forestier — 2 indicateurs ─────────────────────────────────────────────
    "AG.LND.FRST.ZS": IndicatorDef(
        "Superficie forestière (% terre)", SousSecteursEnum.FORESTIER,
        CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.CHIFFRE_AFFAIRES,
        UniteIndicateurEnum.POURCENTAGE, "World Bank",
    ),
    "AG.LND.FRST.K2": IndicatorDef(
        "Superficie forestière (km²)", SousSecteursEnum.FORESTIER,
        CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.CHIFFRE_AFFAIRES,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),

    # ─── Nutrition / Santé — 2 indicateurs ─────────────────────────────────────
    "SN.ITK.DEFC.ZS": IndicatorDef(
        "Prévalence de la sous-alimentation", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.NUTRITION, TypeIndicateurEnum.TAUX_MALNUTRITION_LEGERE,
        UniteIndicateurEnum.POURCENTAGE, "World Bank",
    ),
    "SH.DYN.MORT": IndicatorDef(
        "Taux de mortalité des moins de 5 ans", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.SANTE, TypeIndicateurEnum.FREQUENCE_MALADIES_TRAVAIL,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),

    # ─── Bien-être — 1 indicateur ──────────────────────────────────────────────
    "SE.ADT.LITR.ZS": IndicatorDef(
        "Taux d'alphabétisation", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.BIEN_ETRE, TypeIndicateurEnum.SCOLARISATION_ENFANTS,
        UniteIndicateurEnum.POURCENTAGE, "World Bank",
    ),

    # ─── Climat / Environnement — 2 indicateurs ────────────────────────────────
    "AG.LND.PRCP.MM": IndicatorDef(
        "Précipitations annuelles (mm)", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.CHIFFRE_AFFAIRES,
        UniteIndicateurEnum.NOMBRE, "World Bank",
    ),
    "NY.GDP.MKTP.KD": IndicatorDef(
        "PIB (USD constants)", SousSecteursEnum.VEGETAL,
        CategorieIndicateurEnum.REVENUS, TypeIndicateurEnum.REVENU_ANNUEL,
        UniteIndicateurEnum.USD, "World Bank",
    ),
}

# Code → unité descriptive pour le champ contexte
WB_UNIT_LABELS: dict[str, str] = {
    "AG.LND.AGRI.ZS": "%",
    "AG.YLD.CREL.KG": "kg/ha",
    "AG.PRD.FOOD.XD": "indice",
    "NV.AGR.TOTL.ZS": "% PIB",
    "SL.AGR.EMPL.ZS": "%",
    "AG.LND.IRIG.AG.ZS": "%",
    "AG.CON.FERT.ZS": "kg/ha",
    "AG.PRD.CREL.MT": "tonnes",
    "AG.PRD.CROP.XD": "indice",
    "AG.LND.CROP.ZS": "%",
    "AG.PRD.LVSK.XD": "indice",
    "EN.GHG.CH4.AG.MT.CE.AR5": "Mt CO2e",
    "AG.LND.FRST.ZS": "%",
    "AG.LND.FRST.K2": "km²",
    "SN.ITK.DEFC.ZS": "%",
    "SH.DYN.MORT": "pour 1000",
    "SE.ADT.LITR.ZS": "%",
    "AG.LND.PRCP.MM": "mm",
    "NY.GDP.MKTP.KD": "USD",
}

# ─── Fonctions utilitaires ────────────────────────────────────────────────────


async def get_or_create_actor(
    db: AsyncSession, country_code: str, sector: SousSecteursEnum = SousSecteursEnum.VEGETAL
) -> Optional[Actor]:
    country_name = COUNTRY_NAMES.get(country_code, country_code)
    result = await db.execute(
        select(Actor).where(Actor.pays == country_name).limit(1)
    )
    actor = result.scalar_one_or_none()
    if not actor:
        actor = Actor(
            id=uuid.uuid4(),
            nom=f"Producteur {country_name}",
            prenom="",
            pays=country_name,
            sous_secteur=sector,
            role=ActorRoleEnum.PRODUCTEUR_INDIVIDUEL,
        )
        db.add(actor)
        await db.flush()
    return actor


# ─── Source: World Bank Data API ──────────────────────────────────────────────


async def fetch_wb_indicator(
    country: str, indicator: str, client: httpx.AsyncClient
) -> List[Dict]:
    url = f"{WORLD_BANK_BASE}/country/{country}/indicator/{indicator}"
    params = {"format": "json", "per_page": "5", "date": "2018:2024"}
    try:
        r = await client.get(url, params=params, timeout=15.0)
        r.raise_for_status()
        data = r.json()
        if len(data) < 2 or not data[1]:
            return []
        results = []
        for item in data[1]:
            if item.get("value") is not None:
                results.append({
                    "country_code": country,
                    "country_name": COUNTRY_NAMES.get(country, country),
                    "indicator_code": indicator,
                    "year": int(item["date"]),
                    "value": float(item["value"]),
                })
        return results
    except Exception:
        return []


async def fetch_all_wb_indicators() -> Dict[str, Any]:
    """Récupère tous les indicateurs World Bank pour tous les pays"""
    results = []
    errors = []

    async with httpx.AsyncClient() as client:
        tasks = []
        for country in TRACKED_COUNTRIES:
            for indicator in WB_INDICATORS:
                tasks.append(fetch_wb_indicator(country, indicator, client))

        batches = [tasks[i:i + 25] for i in range(0, len(tasks), 25)]
        for batch in batches:
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            for br in batch_results:
                if isinstance(br, list):
                    results.extend(br)
                elif isinstance(br, Exception):
                    errors.append(str(br)[:80])

    return {"results": results, "errors": errors, "count": len(results),
            "source": "World Bank Data API"}


# ─── Source: FAOSTAT API v2 (JWT Cognito) ─────────────────────────────────────
# URL: https://faostatservices.fao.org/api/v1/{lang}/data/{domain}?area=...&item=...&element=...&year=...
# Token: variable d'env FAOSTAT_JWT (Cognito AccessToken, expire 60min)
# Obtenir un token: https://www.fao.org/faostat/en/#developer-portal
#
# Codes FAO/M49 pour les pays ouest-africains (clé = ISO2):
FAO_COUNTRY_CODES: dict[str, str] = {
    "BJ": "204", "BF": "854", "CI": "384", "GH": "288", "ML": "466",
    "NE": "562", "NG": "566", "SN": "686", "TG": "768",
    "GM": "270", "GW": "624", "LR": "430", "SL": "694", "CM": "120", "GN": "324",
}

FAO_BASE = "https://faostatservices.fao.org/api/v1/en"
FAO_DOMAINS = {
    "QCL": "Cultures et élevage",
    "RFN": "Engrais",
    "PP": "Prix producteur",
}

# Elements FAO pertinents pour nos catégories
# 5510 = Production (Quantity)
# 5412 = Rendement (Yield)
# 5312 = Surface récoltée (Area harvested)

FAO_ELEMENTS = {
    "QCL": {
        "5510": ("Production", SousSecteursEnum.VEGETAL, CategorieIndicateurEnum.REVENUS, TypeIndicateurEnum.CHIFFRE_AFFAIRES, UniteIndicateurEnum.NOMBRE),
        "5412": ("Rendement", SousSecteursEnum.VEGETAL, CategorieIndicateurEnum.REVENUS, TypeIndicateurEnum.REVENU_ANNUEL, UniteIndicateurEnum.NOMBRE),
        "5312": ("Surface récoltée", SousSecteursEnum.VEGETAL, CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.CHIFFRE_AFFAIRES, UniteIndicateurEnum.NOMBRE),
    },
    "RFN": {
        "5510": ("Consommation engrais", SousSecteursEnum.VEGETAL, CategorieIndicateurEnum.COMPTES_EXPLOITATION, TypeIndicateurEnum.CHARGES_EXPLOITATION, UniteIndicateurEnum.NOMBRE),
    },
}

# Cultures FAO pertinentes par code Item
# Items clés : riz (27), maïs (56), mil (79), sorgho (83), igname (116),
# manioc (125), arachide (242), coton (328), café (656), cacao (661)
FAO_CROPS = {
    "27": "Riz", "56": "Maïs", "79": "Mil", "83": "Sorgho",
    "116": "Igname", "125": "Manioc", "242": "Arachide",
    "328": "Coton", "656": "Café", "661": "Cacao",
}


def _get_fao_token() -> Optional[str]:
    import os
    return os.environ.get("FAOSTAT_JWT")


async def fetch_fao_domain(
    domain: str, country_m49: str, items: list[str],
    elements: list[str], years: list[int],
) -> List[Dict]:
    token = _get_fao_token()
    if not token:
        return []

    results = []
    for item in items:
        for element in elements:
            for year in years:
                url = f"{FAO_BASE}/data/{domain}"
                params = {
                    "area": country_m49,
                    "item": item,
                    "element": element,
                    "year": str(year),
                }
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        r = await client.get(
                            url, params=params,
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        if r.status_code != 200:
                            continue
                        data = r.json()
                        records = data.get("data", [])
                        for rec in records:
                            val = rec.get("Value")
                            if val is not None:
                                results.append({
                                    "country_code": str(rec.get("Area Code", country_m49)),
                                    "indicator_code": f"FAO_{domain}_{element}_{item}",
                                    "year": int(rec.get("Year Code", year)),
                                    "value": float(val),
                                    "unit": rec.get("Unit", ""),
                                })
                except Exception:
                    continue
    return results


async def fetch_faostat_indicators() -> Dict[str, Any]:
    token = _get_fao_token()
    if not token:
        return {"results": [], "errors": ["FAOSTAT_JWT non configuré"],
                "count": 0, "source": "FAOSTAT"}

    results = []
    errors = []

    for country_iso2, m49 in FAO_COUNTRY_CODES.items():
        country_name = COUNTRY_NAMES.get(country_iso2, country_iso2)
        for domain, info in FAO_DOMAINS.items():
            domain_els = FAO_ELEMENTS.get(domain, {})
            if not domain_els:
                continue
            items = list(FAO_CROPS.keys())
            elements = list(domain_els.keys())
            years = [2020, 2021, 2022]
            try:
                data = await fetch_fao_domain(domain, m49, items, elements, years)
                for d in data:
                    d["country_name"] = country_name
                    d["source"] = f"FAOSTAT ({info})"
                results.extend(data)
            except Exception as e:
                errors.append(f"{domain}/{country_iso2}: {str(e)[:60]}")

    return {"results": results, "errors": errors[:20],
            "count": len(results), "source": "FAOSTAT"}


# ─── Sauvegarde en base de données ────────────────────────────────────────────


async def save_wb_indicator(db: AsyncSession, item: dict) -> int:
    """Sauvegarde un résultat World Bank. Retourne 1 si créé, 0 si existant."""
    code = item["indicator_code"]
    defn = WB_INDICATORS.get(code)
    if not defn:
        return 0

    actor = await get_or_create_actor(db, item["country_code"], defn.sector)
    if not actor:
        return 0

    annee = item["year"]
    try:
        date_debut = date(annee, 1, 1)
    except (ValueError, OverflowError):
        date_debut = date(2024, 1, 1)

    existing = await db.execute(
        select(IndicateurValeur).where(
            IndicateurValeur.actor_id == actor.id,
            IndicateurValeur.sous_secteur == defn.sector,
            IndicateurValeur.type_indicateur == defn.indicator_type,
            IndicateurValeur.annee == annee,
            IndicateurValeur.source == defn.source_label,
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        return 0

    record = IndicateurValeur(
        id=uuid.uuid4(),
        actor_id=actor.id,
        sous_secteur=defn.sector,
        categorie=defn.category,
        type_indicateur=defn.indicator_type,
        valeur_numerique=item["value"],
        unite=defn.unit,
        periode=PeriodeIndicateurEnum.ANNUELLE,
        date_debut=date_debut,
        annee=annee,
        source=defn.source_label,
        qualite_donnee=1.0,
        is_valide=True,
        contexte={
            "indicator_code": code,
            "country_code": item["country_code"],
            "unit_label": WB_UNIT_LABELS.get(code, ""),
        },
    )
    db.add(record)
    return 1


async def save_fao_indicator(db: AsyncSession, item: dict) -> int:
    """Sauvegarde un résultat FAOSTAT. Retourne 1 si créé, 0 si existant."""
    code = item["indicator_code"]
    parts = code.split("_")
    if len(parts) != 4:
        return 0
    _, domain, element, crop = parts
    el_def = FAO_ELEMENTS.get(domain, {}).get(element)
    if not el_def:
        return 0

    el_name, sector, category, itype, unit = el_def
    crop_name = FAO_CROPS.get(crop, f"Crop_{crop}")

    actor = await get_or_create_actor(db, item["country_code"], sector)
    if not actor:
        return 0

    annee = item["year"]
    try:
        date_debut = date(annee, 1, 1)
    except (ValueError, OverflowError):
        date_debut = date(2024, 1, 1)

    existing = await db.execute(
        select(IndicateurValeur).where(
            IndicateurValeur.actor_id == actor.id,
            IndicateurValeur.sous_secteur == sector,
            IndicateurValeur.type_indicateur == itype,
            IndicateurValeur.annee == annee,
            IndicateurValeur.source == item.get("source", "FAOSTAT"),
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        return 0

    record = IndicateurValeur(
        id=uuid.uuid4(),
        actor_id=actor.id,
        sous_secteur=sector,
        categorie=category,
        type_indicateur=itype,
        valeur_numerique=item["value"],
        unite=unit,
        periode=PeriodeIndicateurEnum.ANNUELLE,
        date_debut=date_debut,
        annee=annee,
        source=item.get("source", "FAOSTAT"),
        qualite_donnee=1.0,
        is_valide=True,
        contexte={
            "indicator_code": code,
            "country_code": item["country_code"],
            "domain": domain,
            "element": el_name,
            "crop": crop_name,
            "unit_label": item.get("unit", ""),
        },
    )
    db.add(record)
    return 1


# ─── Point d'entrée principal ─────────────────────────────────────────────────


async def fetch_all_external_indicators(db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """
    Point d'entrée principal : récupère depuis TOUTES les sources et sauvegarde en base.
    Architecture extensible : il suffit d'ajouter une nouvelle fonction de fetch
    et de l'appeler ici.
    """
    all_results = []
    all_errors = []
    total_fetched = 0
    total_saved = 0
    sources = []

    # ── Source 1 : World Bank ──
    wb = await fetch_all_wb_indicators()
    sources.append(wb["source"])
    total_fetched += wb["count"]
    all_results.extend(wb["results"])
    all_errors.extend(wb["errors"])

    # ── Source 2 : FAOSTAT (réservé) ──
    fao = await fetch_faostat_indicators()
    sources.append(fao["source"])
    total_fetched += fao["count"]
    all_results.extend(fao["results"])
    all_errors.extend(fao["errors"])

    # ── Sauvegarde ──
    if db is not None and all_results:
        for item in all_results:
            try:
                code = item.get("indicator_code", "")
                if code.startswith("FAO_"):
                    saved = await save_fao_indicator(db, item)
                else:
                    saved = await save_wb_indicator(db, item)
                total_saved += saved
            except Exception as e:
                all_errors.append(f"Save error for {item.get('indicator_code')}: {str(e)[:100]}")

        if total_saved:
            try:
                await db.flush()
                await db.commit()
            except Exception:
                pass

    return {
        "success": True,
        "count": total_fetched,
        "saved": total_saved,
        "errors": all_errors[:30],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
    }


# ─── Seed Demo ────────────────────────────────────────────────────────────────


async def seed_demo_indicators(db: AsyncSession) -> Dict[str, Any]:
    """Génère des données de démonstration pour tous les secteurs et catégories"""
    existing = await db.scalar(select(func.count(IndicateurValeur.id)))
    if existing and existing > 10:
        return {"message": "Données déjà présentes", "count": existing}

    sectors = [SousSecteursEnum.VEGETAL, SousSecteursEnum.ANIMAL,
               SousSecteursEnum.HALIEUTIQUE, SousSecteursEnum.FORESTIER]
    categories = list(CategorieIndicateurEnum)
    types = list(TypeIndicateurEnum)
    units = [UniteIndicateurEnum.XOF, UniteIndicateurEnum.POURCENTAGE,
             UniteIndicateurEnum.NOMBRE, UniteIndicateurEnum.SCORE_1_5,
             UniteIndicateurEnum.KG_PAR_PERSONNE_MOIS]
    countries = list(COUNTRY_NAMES.values())
    years = [2019, 2020, 2021, 2022, 2023, 2024]
    import random

    created = 0
    for country in countries:
        result = await db.execute(
            select(Actor).where(Actor.pays == country).limit(1)
        )
        actor = result.scalar_one_or_none()
        if not actor:
            actor = Actor(
                id=uuid.uuid4(), nom=f"Producteur {country}",
                prenom="", pays=country,
                sous_secteur=SousSecteursEnum.VEGETAL,
                role=ActorRoleEnum.PRODUCTEUR_INDIVIDUEL,
            )
            db.add(actor)
            await db.flush()

        for _ in range(12):
            t = random.choice(types)
            cat = random.choice(categories)
            sec = random.choice(sectors)
            u = random.choice(units)
            y = random.choice(years)
            val = round(random.uniform(10, 100000), 2)

            existing_rec = await db.execute(
                select(IndicateurValeur).where(
                    IndicateurValeur.actor_id == actor.id,
                    IndicateurValeur.type_indicateur == t,
                    IndicateurValeur.annee == y,
                ).limit(1)
            )
            if existing_rec.scalar_one_or_none():
                continue

            rec = IndicateurValeur(
                id=uuid.uuid4(),
                actor_id=actor.id,
                sous_secteur=sec,
                categorie=cat,
                type_indicateur=t,
                valeur_numerique=val,
                unite=u,
                periode=PeriodeIndicateurEnum.ANNUELLE,
                date_debut=date(y, 1, 1),
                annee=y,
                source="Seed data",
            )
            db.add(rec)
            created += 1

    await db.flush()
    await db.commit()
    return {"message": f"{created} indicateurs de démonstration créés", "count": created}
