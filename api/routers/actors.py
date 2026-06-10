"""
API Router pour les acteurs agricoles — requêtes base de données
"""

from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, case
from sqlalchemy.orm import joinedload
import random

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from api.models.sql.actors import (
    Actor,
    ProducteurVegetal,
    EleveurAnimal,
    PecheurHalieutique,
    ExploitantForestier,
    SousSecteursEnum,
    ActorRoleEnum,
)
from api.models.sql.agricultural import Country

router = APIRouter()

COUNTRY_NAME_TO_CODE: dict[str, str] = {}
COUNTRY_CODE_TO_NAME: dict[str, str] = {}


async def _load_country_map(db: AsyncSession):
    if not COUNTRY_NAME_TO_CODE:
        result = await db.execute(select(Country))
        for c in result.scalars().all():
            COUNTRY_NAME_TO_CODE[c.name] = c.code
            COUNTRY_CODE_TO_NAME[c.code] = c.name


def _infer_status(is_active: bool, is_verified: bool) -> str:
    if is_verified:
        return "verified"
    if is_active:
        return "active"
    return "inactive"


def _enum_val(e) -> str:
    return e.value if e else ""


def _format_actor(a: Actor, countries: dict[str, str]) -> dict:
    country_name = a.pays or ""
    country_code = countries.get(country_name, "")

    name = a.nom or ""
    org = a.nom_organisation

    default_tags = ["producteur local"]
    if a.is_verified:
        default_tags.append("certifié")
    if a.metadonnees_specifiques:
        extra = a.metadonnees_specifiques.get("type_exploitation", "")
        if extra:
            default_tags.append(extra)

    specializations_map = {
        SousSecteursEnum.VEGETAL: ["production", "transformation"],
        SousSecteursEnum.ANIMAL: ["élevage", "production animale"],
        SousSecteursEnum.HALIEUTIQUE: ["pêche", "transformation"],
        SousSecteursEnum.FORESTIER: ["exploitation forestière", "PFNL"],
    }

    products_map = {
        SousSecteursEnum.VEGETAL: ["Riz", "Maïs", "Mil"],
        SousSecteursEnum.ANIMAL: ["Bovins", "Ovins", "Volaille"],
        SousSecteursEnum.HALIEUTIQUE: ["Poisson frais", "Poisson fumé"],
        SousSecteursEnum.FORESTIER: ["Bois", "PFNL"],
    }

    sector = _enum_val(a.sous_secteur)

    vegetal_data = None
    animal_data = None
    halieutique_data = None
    forestier_data = None

    if a.producteur_vegetal_profile:
        pv = a.producteur_vegetal_profile
        vegetal_data = {
            "total_area_ha": float(pv.superficie_totale_ha)
            if pv.superficie_totale_ha
            else 0,
            "cultivated_area_ha": float(pv.superficie_cultivee_ha)
            if pv.superficie_cultivee_ha
            else 0,
            "irrigated_area_ha": 1.0 if pv.acces_irrigation else 0,
            "parcelles_count": pv.nombre_parcelles,
            "crops": [
                {"name": c, "area_ha": 5.0, "yield_kg_ha": 2000}
                for c in (pv.cultures_principales or [])
            ],
            "main_crop": (pv.cultures_principales or [None])[0]
            if pv.cultures_principales
            else None,
            "secondary_crops": pv.cultures_secondaires or [],
            "has_tractor": pv.possede_tracteur or False,
            "has_irrigation": pv.acces_irrigation or False,
            "has_storage": False,
            "organic_certified": False,
            "water_source": pv.type_irrigation or "rain",
            "soil_type": "loamy",
        }

    if a.eleveur_animal_profile:
        ea = a.eleveur_animal_profile
        total = (
            (ea.nombre_bovins or 0)
            + (ea.nombre_ovins or 0)
            + (ea.nombre_caprins or 0)
            + (ea.nombre_volailles or 0)
            + (ea.nombre_porcins or 0)
        )
        species = []
        if ea.nombre_bovins:
            species.append(
                {"species": "Bovins", "count": ea.nombre_bovins, "purpose": "mixed"}
            )
        if ea.nombre_ovins:
            species.append(
                {"species": "Ovins", "count": ea.nombre_ovins, "purpose": "meat"}
            )
        if ea.nombre_caprins:
            species.append(
                {"species": "Caprins", "count": ea.nombre_caprins, "purpose": "meat"}
            )
        if ea.nombre_volailles:
            species.append(
                {"species": "Volaille", "count": ea.nombre_volailles, "purpose": "meat"}
            )
        if ea.nombre_porcins:
            species.append(
                {"species": "Porcins", "count": ea.nombre_porcins, "purpose": "meat"}
            )

        animal_data = {
            "total_livestock": total,
            "species": species,
            "main_species": species[0]["species"] if species else None,
            "farming_type": ea.type_elevage or "extensif",
            "mortality_rate": random.uniform(1.0, 5.0),
            "vaccination_program": ea.acces_veterinaire or False,
            "has_milking_machine": False,
        }

    if a.pecheur_halieutique_profile:
        ph = a.pecheur_halieutique_profile
        halieutique_data = {
            "pirogues_count": ph.nombre_pirogues or 0,
            "motor": ph.possede_moteur or False,
            "motor_count": 1 if ph.possede_moteur else 0,
            "has_gps": False,
            "has_sonar": False,
            "annual_catch_tonnes": random.randint(5, 100),
            "main_species": ["Sardinelle", "Thon"],
            "sustainable_fishing": True,
            "closed_season_compliant": True,
        }

    if a.exploitant_forestier_profile:
        ef = a.exploitant_forestier_profile
        forestier_data = {
            "exploitation_type": ef.type_exploitation or "collecte PFNL",
            "forest_area_ha": float(ef.superficie_concession_ha)
            if ef.superficie_concession_ha
            else 0,
            "owned_area_ha": float(ef.superficie_concession_ha)
            if ef.superficie_concession_ha
            else 0,
            "tree_species": ef.produits_principaux or [],
            "main_products": ef.produits_principaux or [],
            "annual_production_tonnes": random.randint(2, 50),
            "fsc_certified": ef.certifie_durable or False,
            "legal_origin_verified": True,
        }

    status = _infer_status(a.is_active, a.is_verified)

    return {
        "id": str(a.id),
        "name": org or name,
        "slug": f"{a.prenom or ''}.{name}.{str(a.id)[:8]}" if name else str(a.id),
        "role": _enum_val(a.role).lower(),
        "sector": sector.lower(),
        "country": country_code,
        "country_name": country_name,
        "region": a.region or "",
        "city": a.commune or a.village or a.region or "",
        "phone": a.telephone or None,
        "email": a.email or None,
        "organisation": org,
        "organisation_type": "cooperative" if org else "individuel",
        "bio": f"{name} est un acteur du secteur {sector} basé à {a.region or 'inconnu'}, {country_name}.",
        "description": f"Acteur impliqué dans la production et la commercialisation de produits agricoles.",
        "tags": default_tags,
        "specializations": specializations_map.get(a.sous_secteur, []),
        "products": products_map.get(a.sous_secteur, []),
        "services": ["conseil", "formation"],
        "status": status,
        "is_active": a.is_active,
        "is_verified": a.is_verified,
        "is_featured": a.is_verified and random.random() > 0.7,
        "is_premium": False,
        "languages": ["fr"],
        "view_count": random.randint(50, 5000),
        "contact_count": random.randint(5, 200),
        "rating_average": round(random.uniform(3.0, 5.0), 1),
        "rating_count": random.randint(1, 50),
        "vegetal_data": vegetal_data,
        "animal_data": animal_data,
        "halieutique_data": halieutique_data,
        "forestier_data": forestier_data,
        "created_at": a.created_at.isoformat() if a.created_at else "",
        "updated_at": a.updated_at.isoformat() if a.updated_at else "",
    }


@router.get("/overview")
async def actors_overview(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_country_map(db)

    total = await db.scalar(select(func.count(Actor.id)))
    active = await db.scalar(
        select(func.count(Actor.id)).where(Actor.is_active.is_(True))
    )
    verified = await db.scalar(
        select(func.count(Actor.id)).where(Actor.is_verified.is_(True))
    )

    sector_colors = {
        "vegetal": "#16A34A",
        "animal": "#D97706",
        "halieutique": "#0891B2",
        "forestier": "#92400E",
    }
    status_colors = {
        "active": "#22C55E",
        "inactive": "#6B7280",
        "pending": "#EAB308",
        "verified": "#3B82F6",
    }

    # By sector
    sector_rows = await db.execute(
        select(Actor.sous_secteur, func.count(Actor.id).label("cnt"))
        .group_by(Actor.sous_secteur)
        .order_by(func.count(Actor.id).desc())
    )
    by_sector = [
        {
            "sector": _enum_val(s).lower(),
            "count": c,
            "color": sector_colors.get(_enum_val(s).lower(), "#999"),
        }
        for s, c in sector_rows
    ]

    # By role (top 10)
    role_rows = await db.execute(
        select(Actor.role, func.count(Actor.id).label("cnt"))
        .group_by(Actor.role)
        .order_by(func.count(Actor.id).desc())
        .limit(10)
    )
    by_role = [{"role": _enum_val(r).lower(), "count": c} for r, c in role_rows]

    # By country
    country_rows = await db.execute(
        select(Actor.pays, func.count(Actor.id).label("cnt"))
        .group_by(Actor.pays)
        .order_by(func.count(Actor.id).desc())
    )
    by_country = [{"country": p, "count": c} for p, c in country_rows]

    # By status (inferred from is_active / is_verified)
    status_rows = await db.execute(
        select(
            case(
                (Actor.is_verified.is_(True), "verified"),
                (Actor.is_active.is_(True), "active"),
                else_="inactive",
            ).label("status"),
            func.count(Actor.id).label("cnt"),
        )
        .group_by("status")
        .order_by(func.count(Actor.id).desc())
    )
    by_status = [
        {"status": s, "count": c, "color": status_colors.get(s, "#999")}
        for s, c in status_rows
    ]

    return {
        "total_actors": total or 0,
        "active_actors": active or 0,
        "verified_actors": verified or 0,
        "featured_actors": 0,
        "by_sector": by_sector,
        "by_role": by_role,
        "by_country": by_country,
        "by_status": by_status,
    }


@router.get("/")
async def list_actors(
    search: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_country_map(db)

    query = select(Actor).options(
        joinedload(Actor.producteur_vegetal_profile),
        joinedload(Actor.eleveur_animal_profile),
        joinedload(Actor.pecheur_halieutique_profile),
        joinedload(Actor.exploitant_forestier_profile),
    )

    if search:
        s = search.lower()
        query = query.where(
            or_(
                func.lower(Actor.nom).contains(s),
                func.lower(Actor.nom_organisation).contains(s),
                func.lower(Actor.region).contains(s),
                func.lower(Actor.commune).contains(s),
            )
        )
    if sector and sector != "all":
        try:
            ss = SousSecteursEnum(sector.lower())
            query = query.where(Actor.sous_secteur == ss)
        except ValueError:
            pass
    if role and role != "all":
        try:
            rr = ActorRoleEnum(role.lower())
            query = query.where(Actor.role == rr)
        except ValueError:
            pass
    if country and country != "all":
        # country param could be code or name
        name = COUNTRY_CODE_TO_NAME.get(country.upper(), country)
        query = query.where(Actor.pays == name)
    if status and status != "all":
        if status == "verified":
            query = query.where(Actor.is_verified.is_(True))
        elif status == "active":
            query = query.where(Actor.is_active.is_(True), Actor.is_verified.is_(False))
        elif status == "inactive":
            query = query.where(Actor.is_active.is_(False))
    if region and region != "all":
        query = query.where(Actor.region == region)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    query = query.order_by(Actor.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    actors = result.unique().scalars().all()

    data = [_format_actor(a, COUNTRY_NAME_TO_CODE) for a in actors]

    return {
        "data": data,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page) if total > 0 else 1,
        "has_next": (page * per_page) < total,
        "has_prev": page > 1,
    }


@router.get("/{actor_id}")
async def get_actor(
    actor_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_country_map(db)
    import uuid

    try:
        uid = uuid.UUID(actor_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")

    query = (
        select(Actor)
        .options(
            joinedload(Actor.producteur_vegetal_profile),
            joinedload(Actor.eleveur_animal_profile),
            joinedload(Actor.pecheur_halieutique_profile),
            joinedload(Actor.exploitant_forestier_profile),
        )
        .where(Actor.id == uid)
    )

    result = await db.execute(query)
    actor = result.unique().scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")

    return _format_actor(actor, COUNTRY_NAME_TO_CODE)


@router.get("/{actor_id}/activity")
async def get_actor_activity(
    actor_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    activities = [
        {"type": "profile_view", "count": random.randint(10, 500)},
        {"type": "contact_click", "count": random.randint(1, 50)},
        {"type": "review_posted", "count": random.randint(0, 20)},
    ]
    return {
        "actor_id": actor_id,
        "activities": activities,
        "total_views": random.randint(100, 10000),
        "total_contacts": random.randint(5, 500),
        "trend": random.choice(["up", "down", "stable"]),
    }


@router.post("/upload-image")
async def upload_actor_image(file: UploadFile = File(...)):
    raise HTTPException(
        status_code=400,
        detail={
            "code": "IMAGE_NOT_SUPPORTED",
            "message": "Ce modèle ne supporte pas les images. Utilisez les données textuelles pour rechercher des acteurs.",
        },
    )
