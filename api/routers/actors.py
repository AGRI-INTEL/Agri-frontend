"""
API Router pour les acteurs agricoles — requêtes base de données
"""

from typing import Optional, Any, List as Lst
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, case
from sqlalchemy.orm import joinedload
from pydantic import BaseModel as PydanticModel
from typing import Optional as Opt

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
            "mortality_rate": None,
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
            "annual_catch_tonnes": None,
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
            "annual_production_tonnes": None,
            "fsc_certified": ef.certifie_durable or False,
            "legal_origin_verified": True,
        }

    status = _infer_status(a.is_active, a.is_verified)

    return {
        "id": str(a.id),
        "user_id": str(a.user_id) if a.user_id else None,
        "name": org or name,
        "first_name": a.prenom or name,
        "last_name": org or name,
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
        "is_featured": a.is_verified,
        "is_premium": False,
        "languages": ["fr"],
        "view_count": 0,
        "contact_count": 0,
        "rating_average": None,
        "rating_count": 0,
        "vegetal_data": vegetal_data,
        "animal_data": animal_data,
        "halieutique_data": halieutique_data,
        "forestier_data": forestier_data,
        "created_at": a.created_at.isoformat() if a.created_at else "",
        "updated_at": a.updated_at.isoformat() if a.updated_at else "",
        "latitude": a.latitude,
        "longitude": a.longitude,
    }


def _parse_sector_data(body: dict, sector: str) -> dict:
    """Extract flat fields from frontend nested sector data format."""
    data: dict = {}
    sector_key_map = {
        "vegetal": "vegetal_data",
        "animal": "animal_data",
        "halieutique": "halieutique_data",
        "forestier": "forestier_data",
    }
    key = sector_key_map.get(sector)
    if not key:
        return data

    sd = body.get(key, {}) or {}
    if sector == "vegetal":
        data["superficie_totale_ha"] = sd.get("total_area_ha")
        data["cultures_principales"] = sd.get("main_crops", [])
        data["acces_irrigation"] = sd.get("irrigation_access", False)
        data["nombre_parcelles"] = sd.get("plots_count", 1)
        data["possede_tracteur"] = sd.get("has_tractor", False)
    elif sector == "animal":
        data["nombre_bovins"] = sd.get("bovins_count", 0)
        data["nombre_ovins"] = sd.get("ovins_count", 0)
        data["nombre_caprins"] = sd.get("caprins_count", 0)
        data["nombre_volailles"] = sd.get("volailles_count", 0)
        data["nombre_porcins"] = sd.get("porcins_count", 0)
        data["type_elevage"] = sd.get("breeding_type")
        data["acces_veterinaire"] = sd.get("veterinary_access", False)
    elif sector == "halieutique":
        data["nombre_pirogues"] = sd.get("pirogues_count", 0)
        data["possede_moteur"] = sd.get("motor", False)
        data["type_peche"] = sd.get("fishing_type")
        data["zone_peche_principale"] = sd.get("main_fishing_zone")
    elif sector == "forestier":
        data["type_exploitation"] = sd.get("exploitation_type")
        data["produits_principaux"] = sd.get("main_products", [])
        data["superficie_concession_ha"] = sd.get("concession_area_ha")
        data["certifie_durable"] = sd.get("sustainable_certified", False)
    return data


class ActorCreateBody(PydanticModel):
    name: str = ""
    first_name: Opt[str] = None
    last_name: Opt[str] = None
    role: str = "producteur_individuel"
    sector: str = "vegetal"
    country: str = "Sénégal"
    region: Opt[str] = None
    city: Opt[str] = None
    email: Opt[str] = None
    phone: Opt[str] = None
    is_active: bool = True
    latitude: Opt[float] = None
    longitude: Opt[float] = None
    vegetal_data: Opt[dict] = None
    animal_data: Opt[dict] = None
    halieutique_data: Opt[dict] = None
    forestier_data: Opt[dict] = None


class ActorUpdateBody(PydanticModel):
    name: Opt[str] = None
    first_name: Opt[str] = None
    last_name: Opt[str] = None
    role: Opt[str] = None
    region: Opt[str] = None
    city: Opt[str] = None
    email: Opt[str] = None
    phone: Opt[str] = None
    is_active: Opt[bool] = None
    latitude: Opt[float] = None
    longitude: Opt[float] = None
    vegetal_data: Opt[dict] = None
    animal_data: Opt[dict] = None
    halieutique_data: Opt[dict] = None
    forestier_data: Opt[dict] = None


@router.get("/geojson")
async def actors_geojson(
    sector: Opt[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(Actor).where(
        Actor.latitude != None,
        Actor.longitude != None,
        Actor.is_active == True,
    )
    if sector:
        try:
            ss = SousSecteursEnum(sector.lower())
            q = q.where(Actor.sous_secteur == ss)
        except ValueError:
            pass

    result = await db.execute(q)
    actors = result.scalars().all()

    features = []
    for a in actors:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(a.longitude), float(a.latitude)],
            },
            "properties": {
                "id": str(a.id),
                "name": a.nom or "",
                "sector": _enum_val(a.sous_secteur),
                "role": _enum_val(a.role),
                "city": a.commune or "",
                "region": a.region or "",
                "country": a.pays or "",
            },
        })

    return {"type": "FeatureCollection", "features": features}


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

    role_rows = await db.execute(
        select(Actor.role, func.count(Actor.id).label("cnt"))
        .group_by(Actor.role)
        .order_by(func.count(Actor.id).desc())
        .limit(10)
    )
    by_role = [{"role": _enum_val(r).lower(), "count": c} for r, c in role_rows]

    country_rows = await db.execute(
        select(Actor.pays, func.count(Actor.id).label("cnt"))
        .group_by(Actor.pays)
        .order_by(func.count(Actor.id).desc())
    )
    by_country = [{"country": p, "count": c} for p, c in country_rows]

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
        {"type": "profile_view", "count": 0},
        {"type": "contact_click", "count": 0},
        {"type": "review_posted", "count": 0},
    ]
    return {
        "actor_id": actor_id,
        "activities": activities,
        "total_views": 0,
        "total_contacts": 0,
        "trend": "stable",
    }


@router.post("/")
async def create_actor(
    body: ActorCreateBody,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_country_map(db)
    try:
        role_enum = ActorRoleEnum(body.role.lower())
    except ValueError:
        role_enum = ActorRoleEnum.PRODUCTEUR_INDIVIDUEL
    try:
        sector_enum = SousSecteursEnum(body.sector.lower())
    except ValueError:
        sector_enum = SousSecteursEnum.VEGETAL

    effective_name = body.name or f"{body.first_name or ''} {body.last_name or ''}".strip()
    if not effective_name:
        effective_name = "Acteur sans nom"

    actor = Actor(
        nom=effective_name,
        prenom=body.first_name,
        sous_secteur=sector_enum,
        role=role_enum,
        pays=body.country,
        region=body.region,
        commune=body.city,
        email=body.email,
        telephone=body.phone,
        latitude=body.latitude,
        longitude=body.longitude,
        is_active=body.is_active,
        is_verified=False,
    )
    db.add(actor)
    await db.flush()

    sd = _parse_sector_data(body.model_dump(), body.sector)

    if sector_enum == SousSecteursEnum.VEGETAL:
        pv = ProducteurVegetal(
            id=actor.id,
            superficie_totale_ha=sd.get("superficie_totale_ha"),
            cultures_principales=sd.get("cultures_principales", []),
            acces_irrigation=sd.get("acces_irrigation", False),
            nombre_parcelles=sd.get("nombre_parcelles", 1),
            possede_tracteur=sd.get("possede_tracteur", False),
        )
        db.add(pv)
    elif sector_enum == SousSecteursEnum.ANIMAL:
        ea = EleveurAnimal(
            id=actor.id,
            nombre_bovins=sd.get("nombre_bovins", 0),
            nombre_ovins=sd.get("nombre_ovins", 0),
            nombre_caprins=sd.get("nombre_caprins", 0),
            nombre_volailles=sd.get("nombre_volailles", 0),
            nombre_porcins=sd.get("nombre_porcins", 0),
            type_elevage=sd.get("type_elevage"),
            acces_veterinaire=sd.get("acces_veterinaire", False),
        )
        db.add(ea)
    elif sector_enum == SousSecteursEnum.HALIEUTIQUE:
        ph = PecheurHalieutique(
            id=actor.id,
            nombre_pirogues=sd.get("nombre_pirogues", 0),
            possede_moteur=sd.get("possede_moteur", False),
            type_peche=sd.get("type_peche"),
            zone_peche_principale=sd.get("zone_peche_principale"),
        )
        db.add(ph)
    elif sector_enum == SousSecteursEnum.FORESTIER:
        ef = ExploitantForestier(
            id=actor.id,
            type_exploitation=sd.get("type_exploitation"),
            produits_principaux=sd.get("produits_principaux", []),
            superficie_concession_ha=sd.get("superficie_concession_ha"),
            certifie_durable=sd.get("certifie_durable", False),
        )
        db.add(ef)

    await db.commit()
    await db.refresh(actor)
    result = await db.execute(
        select(Actor).options(
            joinedload(Actor.producteur_vegetal_profile),
            joinedload(Actor.eleveur_animal_profile),
            joinedload(Actor.pecheur_halieutique_profile),
            joinedload(Actor.exploitant_forestier_profile),
        ).where(Actor.id == actor.id)
    )
    actor = result.unique().scalar_one()
    return _format_actor(actor, COUNTRY_NAME_TO_CODE)


@router.put("/{actor_id}")
async def update_actor(
    actor_id: str,
    body: ActorUpdateBody,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_country_map(db)
    import uuid as _uuid
    try:
        uid = _uuid.UUID(actor_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")

    result = await db.execute(
        select(Actor).options(
            joinedload(Actor.producteur_vegetal_profile),
            joinedload(Actor.eleveur_animal_profile),
            joinedload(Actor.pecheur_halieutique_profile),
            joinedload(Actor.exploitant_forestier_profile),
        ).where(Actor.id == uid)
    )
    actor = result.unique().scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")

    if body.name is not None: actor.nom = body.name
    if body.first_name is not None: actor.prenom = body.first_name
    if body.role is not None:
        try: actor.role = ActorRoleEnum(body.role.lower())
        except ValueError: pass
    if body.region is not None: actor.region = body.region
    if body.city is not None: actor.commune = body.city
    if body.email is not None: actor.email = body.email
    if body.phone is not None: actor.telephone = body.phone
    if body.is_active is not None: actor.is_active = body.is_active
    if body.latitude is not None: actor.latitude = body.latitude
    if body.longitude is not None: actor.longitude = body.longitude

    sector_str = _enum_val(actor.sous_secteur)
    sd = _parse_sector_data(body.model_dump(exclude_none=True), sector_str) if body.model_dump(exclude_none=True) else {}

    if actor.sous_secteur == SousSecteursEnum.VEGETAL and actor.producteur_vegetal_profile:
        pv = actor.producteur_vegetal_profile
        if "superficie_totale_ha" in sd and sd["superficie_totale_ha"] is not None: pv.superficie_totale_ha = sd["superficie_totale_ha"]
        if "cultures_principales" in sd and sd["cultures_principales"] is not None: pv.cultures_principales = sd["cultures_principales"]
        if "acces_irrigation" in sd and sd["acces_irrigation"] is not None: pv.acces_irrigation = sd["acces_irrigation"]
        if "nombre_parcelles" in sd and sd["nombre_parcelles"] is not None: pv.nombre_parcelles = sd["nombre_parcelles"]
        if "possede_tracteur" in sd and sd["possede_tracteur"] is not None: pv.possede_tracteur = sd["possede_tracteur"]
    elif actor.sous_secteur == SousSecteursEnum.ANIMAL and actor.eleveur_animal_profile:
        ea = actor.eleveur_animal_profile
        if "nombre_bovins" in sd: ea.nombre_bovins = sd["nombre_bovins"]
        if "nombre_ovins" in sd: ea.nombre_ovins = sd["nombre_ovins"]
        if "nombre_caprins" in sd: ea.nombre_caprins = sd["nombre_caprins"]
        if "nombre_volailles" in sd: ea.nombre_volailles = sd["nombre_volailles"]
        if "nombre_porcins" in sd: ea.nombre_porcins = sd["nombre_porcins"]
        if "type_elevage" in sd: ea.type_elevage = sd["type_elevage"]
        if "acces_veterinaire" in sd: ea.acces_veterinaire = sd["acces_veterinaire"]
    elif actor.sous_secteur == SousSecteursEnum.HALIEUTIQUE and actor.pecheur_halieutique_profile:
        ph = actor.pecheur_halieutique_profile
        if "nombre_pirogues" in sd: ph.nombre_pirogues = sd["nombre_pirogues"]
        if "possede_moteur" in sd: ph.possede_moteur = sd["possede_moteur"]
        if "type_peche" in sd: ph.type_peche = sd["type_peche"]
        if "zone_peche_principale" in sd: ph.zone_peche_principale = sd["zone_peche_principale"]
    elif actor.sous_secteur == SousSecteursEnum.FORESTIER and actor.exploitant_forestier_profile:
        ef = actor.exploitant_forestier_profile
        if "type_exploitation" in sd: ef.type_exploitation = sd["type_exploitation"]
        if "produits_principaux" in sd: ef.produits_principaux = sd["produits_principaux"]
        if "superficie_concession_ha" in sd: ef.superficie_concession_ha = sd["superficie_concession_ha"]
        if "certifie_durable" in sd: ef.certifie_durable = sd["certifie_durable"]

    await db.commit()
    result2 = await db.execute(
        select(Actor).options(
            joinedload(Actor.producteur_vegetal_profile),
            joinedload(Actor.eleveur_animal_profile),
            joinedload(Actor.pecheur_halieutique_profile),
            joinedload(Actor.exploitant_forestier_profile),
        ).where(Actor.id == uid)
    )
    actor = result2.unique().scalar_one()
    return _format_actor(actor, COUNTRY_NAME_TO_CODE)


@router.delete("/{actor_id}")
async def delete_actor(
    actor_id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    from sqlalchemy import text as _text
    try:
        uid = _uuid.UUID(actor_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")
    check = await db.execute(select(Actor.id).where(Actor.id == uid))
    if not check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Acteur non trouvé")
    uid_str = str(uid)
    await db.execute(_text("DELETE FROM producteurs_vegetal WHERE id = :id"), {"id": uid_str})
    await db.execute(_text("DELETE FROM eleveurs_animal WHERE id = :id"), {"id": uid_str})
    await db.execute(_text("DELETE FROM pecheurs_halieutique WHERE id = :id"), {"id": uid_str})
    await db.execute(_text("DELETE FROM exploitants_forestier WHERE id = :id"), {"id": uid_str})
    await db.execute(_text("DELETE FROM actors WHERE id = :id"), {"id": uid_str})
    await db.commit()
    return {"message": "Acteur supprimé", "id": actor_id}


@router.post("/upload-image")
async def upload_actor_image(file: UploadFile = File(...)):
    raise HTTPException(
        status_code=400,
        detail={
            "code": "IMAGE_NOT_SUPPORTED",
            "message": "Ce modèle ne supporte pas les images. Utilisez les données textuelles pour rechercher des acteurs.",
        },
    )
