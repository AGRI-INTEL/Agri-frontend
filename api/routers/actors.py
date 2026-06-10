"""
API Router pour les acteurs agricoles
"""

from typing import List, Optional, Any
import random
import string
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File

router = APIRouter()

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _pick(values: list) -> Any:
    return random.choice(values)

def _rand(min_v: float, max_v: float, decimals: int = 2) -> float:
    return round(random.uniform(min_v, max_v), decimals)

def _rand_int(min_v: int, max_v: int) -> int:
    return random.randint(min_v, max_v)

FIRST_NAMES = [
    "Amadou", "Fatou", "Mamadou", "Aïssatou", "Ousmane", "Kadiatou",
    "Souleymane", "Mariam", "Ibrahima", "Aminata", "Moussa", "Rokhaya",
    "Modou", "Ndèye", "Cheikh", "Khady", "Abdoulaye", "Adama",
    "Bakary", "Fanta", "Drissa", "Salimata", "Koffi", "Awa",
    "Yao", "Akissi", "Kwame", "Esi", "Tunde", "Chiamaka",
    "Emeka", "Ngozi", "Jean-Pierre", "Marie-Claire", "Hervé", "Bénédicte",
    "Guy", "Jeanne", "Patrice", "Odette",
]

LAST_NAMES = [
    "Diop", "Ndiaye", "Fall", "Koné", "Traoré", "Diallo", "Sow",
    "Ba", "Sy", "Gueye", "Cissé", "Mendy", "Faye", "Sarr",
    "Kane", "Ngom", "Thiam", "Dieng", "Ly", "Dione", "Camara",
    "Keita", "Touré", "Coulibaly", "Ouattara", "Bamba", "Kouassi",
    "Mensah", "Asante", "Boateng", "Okafor", "Okonkwo", "Eze",
    "Mbappé", "Tchamba", "Nkoudou", "Essomba", "Mvogo",
]

SECTORS = ["vegetal", "animal", "halieutique", "forestier", "minier", "industriel"]

ROLES = [
    "producteur", "eleveur", "pecheur", "exploitant_forestier",
    "cooperative", "groupement", "transformateur", "commercant",
    "exportateur", "importateur", "fournisseur_intrants", "veterinaire",
    "agronome", "technicien", "chercheur", "ong", "institution",
    "financier", "assureur", "transporteur", "stockeur", "semencier",
    "irrigant", "mecanisateur", "certifieur", "auditeur", "consultant",
    "formateur", "journaliste", "fonctionnaire", "elu", "autre",
]

COUNTRIES = [
    {"code": "SN", "name": "Sénégal"},
    {"code": "CI", "name": "Côte d'Ivoire"},
    {"code": "ML", "name": "Mali"},
    {"code": "BF", "name": "Burkina Faso"},
    {"code": "NE", "name": "Niger"},
    {"code": "BJ", "name": "Bénin"},
    {"code": "TG", "name": "Togo"},
    {"code": "GH", "name": "Ghana"},
    {"code": "NG", "name": "Nigéria"},
    {"code": "CM", "name": "Cameroun"},
]

REGIONS = {
    "SN": ["Dakar", "Thiès", "Saint-Louis", "Kaolack", "Ziguinchor", "Louga", "Diourbel", "Fatick", "Tambacounda", "Kolda", "Matam", "Kaffrine", "Kédougou", "Sédhiou"],
    "CI": ["Abidjan", "Bouaké", "Yamoussoukro", "San-Pédro", "Korhogo", "Daloa", "Man", "Gagnoa"],
    "ML": ["Bamako", "Sikasso", "Kayes", "Mopti", "Ségou", "Tombouctou", "Gao", "Kidal"],
    "BF": ["Ouagadougou", "Bobo-Dioulasso", "Koudougou", "Ouahigouya", "Banfora", "Fada N'Gourma"],
    "NE": ["Niamey", "Zinder", "Maradi", "Tahoua", "Agadez", "Dosso"],
    "BJ": ["Cotonou", "Porto-Novo", "Parakou", "Abomey-Calavi", "Ouidah", "Bohicon"],
    "TG": ["Lomé", "Kara", "Sokodé", "Tsévié", "Atakpamé"],
    "GH": ["Accra", "Kumasi", "Takoradi", "Tamale", "Cape Coast", "Tema"],
    "NG": ["Lagos", "Abuja", "Kano", "Ibadan", "Port Harcourt", "Kaduna"],
    "CM": ["Douala", "Yaoundé", "Garoua", "Bamenda", "Maroua", "Bafoussam"],
}

STATUSES = ["active", "inactive", "pending", "verified"]
CROPS = ["Riz", "Maïs", "Mil", "Sorgho", "Arachide", "Niébé", "Coton", "Manioc", "Igname", "Banane plantain", "Cacao", "Café", "Anacarde", "Palmier à huile", "Hévéa"]
SPECIES = ["Bovins", "Ovins", "Caprins", "Volaille", "Porcins", "Asins", "Camelins"]
FISH_TYPES = ["Sardinelle", "Thon", "Capitaine", "Sole", "Mérou", "Pagre", "Machoiran", "Carpe"]
FOREST_TYPES = ["Teck", "Acacia", "Eucalyptus", "Anacardier", "Fromager", "Samba", "Bété", "Iroko"]
MINERALS = ["Or", "Phosphate", "Fer", "Bauxite", "Diamant", "Calcaire", "Marbre", "Uranium"]
INDUSTRIES = ["Agroalimentaire", "Textile", "Bois", "Chimie", "Matériaux", "Énergie"]

def _generate_actor(actor_id: int) -> dict:
    country = _pick(COUNTRIES)
    country_code = country["code"]
    sector = _pick(SECTORS)
    first_name = _pick(FIRST_NAMES)
    last_name = _pick(LAST_NAMES)
    name = f"{first_name} {last_name}"
    region = _pick(REGIONS[country_code])
    city = f"{region}-ville" if random.random() > 0.5 else region
    role = _pick(ROLES)
    status = _pick(STATUSES)
    created_at = datetime.now() - timedelta(days=_rand_int(30, 730))

    org_types = ["cooperative", "groupement", "entreprise", "ong", "institution", "individuel"]
    tags = random.sample(["certifié bio", "labellisé", "jeune agriculteur", "femme rurale", "exportateur", "transformateur", "producteur local", "agroécologie", "irrigation", "semences locales"], k=_rand_int(1, 4))

    actor = {
        "id": str(actor_id),
        "name": name,
        "slug": f"{first_name.lower()}.{last_name.lower()}.{actor_id}",
        "role": role,
        "sector": sector,
        "country": country_code,
        "country_name": country["name"],
        "region": region,
        "city": city,
        "phone": f"+221 77 {_rand_int(100, 999)} {_rand_int(10, 99)} {_rand_int(10, 99)}" if random.random() > 0.2 else None,
        "email": f"{first_name.lower()}.{last_name.lower()}@example.com" if random.random() > 0.2 else None,
        "organisation": f"Coopérative {last_name}" if random.random() > 0.6 else None,
        "organisation_type": _pick(org_types),
        "bio": f"{first_name} {last_name} est un acteur clé du secteur {sector} basé à {city}, {country['name']}.",
        "description": f"Acteur impliqué dans la production et la commercialisation de produits agricoles. {'Certifié bio et engagé dans une agriculture durable.' if random.random() > 0.5 else 'Partenaire de confiance pour les marchés locaux et internationaux.'}",
        "tags": tags,
        "specializations": random.sample(["production", "transformation", "commercialisation", "exportation", "formation", "conseil"], k=_rand_int(1, 3)),
        "products": random.sample(CROPS + SPECIES + FISH_TYPES, k=_rand_int(2, 5)),
        "services": random.sample(["formation", "conseil", "transport", "stockage", "transformation", "financement"], k=_rand_int(1, 3)),
        "status": status,
        "is_active": status in ("active", "verified"),
        "is_verified": status == "verified",
        "is_featured": random.random() > 0.85,
        "is_premium": random.random() > 0.9,
        "languages": random.sample(["fr", "en", "wo", "ha", "bm", "dy"], k=_rand_int(1, 3)),
        "view_count": _rand_int(50, 5000),
        "contact_count": _rand_int(5, 200),
        "rating_average": _rand(2.5, 5.0, 1),
        "rating_count": _rand_int(1, 50),
        "created_at": created_at.isoformat(),
        "updated_at": (created_at + timedelta(days=_rand_int(1, 60))).isoformat(),
    }

    # Sector-specific data
    if sector == "vegetal":
        crops = random.sample(CROPS, k=_rand_int(1, 4))
        total_area = _rand_int(2, 200)
        actor["vegetal_data"] = {
            "total_area_ha": total_area,
            "cultivated_area_ha": _rand(1, total_area, 1),
            "irrigated_area_ha": _rand(0, 10, 1) if random.random() > 0.5 else 0,
            "crops": [{"name": c, "area_ha": _rand(0.5, 30, 1), "yield_kg_ha": _rand_int(500, 5000)} for c in crops[:3]],
            "main_crop": crops[0],
            "secondary_crops": crops[1:],
            "yield_kg_ha": _rand_int(800, 4000),
            "annual_production_tonnes": _rand_int(2, 100),
            "has_tractor": random.random() > 0.7,
            "has_irrigation": random.random() > 0.5,
            "has_storage": random.random() > 0.6,
            "organic_certified": random.random() > 0.8,
            "annual_revenue": _rand_int(1000000, 50000000),
            "water_source": _pick(["river", "well", "rain", "dam", "mixed"]),
            "soil_type": _pick(["sandy", "clay", "loamy", "laterite", "alluvial"]),
        }
    elif sector == "animal":
        species_list = random.sample(SPECIES, k=_rand_int(1, 3))
        total = _rand_int(5, 500)
        actor["animal_data"] = {
            "total_livestock": total,
            "species": [{"species": s, "count": _rand_int(2, total), "purpose": _pick(["meat", "milk", "mixed"])} for s in species_list],
            "main_species": species_list[0],
            "farming_type": _pick(["extensif", "intensif", "semi-intensif"]),
            "mortality_rate": _rand(0.5, 8.0, 1),
            "vaccination_program": random.random() > 0.4,
            "has_milking_machine": random.random() > 0.8,
            "annual_revenue": _rand_int(500000, 20000000),
        }
    elif sector == "halieutique":
        fish = random.sample(FISH_TYPES, k=_rand_int(1, 3))
        actor["halieutique_data"] = {
            "pirogues_count": _rand_int(1, 10),
            "motor": random.random() > 0.3,
            "motor_count": _rand_int(1, 3),
            "has_gps": random.random() > 0.5,
            "has_sonar": random.random() > 0.7,
            "annual_catch_tonnes": _rand_int(5, 200),
            "main_species": fish,
            "sustainable_fishing": random.random() > 0.4,
            "closed_season_compliant": random.random() > 0.3,
        }
    elif sector == "forestier":
        trees = random.sample(FOREST_TYPES, k=_rand_int(1, 3))
        actor["forestier_data"] = {
            "exploitation_type": _pick(["coupe", "écorçage", "collecte PFNL"]),
            "forest_area_ha": _rand_int(5, 500),
            "owned_area_ha": _rand_int(2, 100),
            "tree_species": trees,
            "main_products": trees,
            "annual_production_tonnes": _rand_int(2, 100),
            "fsc_certified": random.random() > 0.8,
            "legal_origin_verified": random.random() > 0.3,
            "annual_revenue": _rand_int(1000000, 30000000),
        }
    elif sector == "minier":
        actor["minier_data"] = {
            "site_type": _pick(["artisanal", "small_scale"]),
            "minerals": random.sample(MINERALS, k=_rand_int(1, 2)),
            "workers_count": _rand_int(5, 200),
            "annual_production_tonnes": _rand_int(1, 50),
            "environmental_impact": _pick(["low", "medium"]),
            "safety_certified": random.random() > 0.6,
        }
    elif sector == "industriel":
        actor["industriel_data"] = {
            "industry_type": random.sample(INDUSTRIES, k=_rand_int(1, 2)),
            "products": random.sample(["huile", "farine", "sucre", "conserve", "jus", "textile", "savon", "bière"], k=_rand_int(2, 4)),
            "processing_capacity_tonnes_day": _rand_int(1, 100),
            "employee_count": _rand_int(5, 500),
            "women_employee_percentage": _rand_int(10, 60),
            "export_markets": random.sample(["UEMOA", "CEDEAO", "UE", "USA", "Chine", "Japon"], k=_rand_int(1, 3)),
            "haccp_certified": random.random() > 0.6,
            "iso_certified": random.random() > 0.7,
            "annual_revenue": _rand_int(5000000, 100000000),
        }

    return actor

# Pre-generate a pool of actors
_actor_pool = [_generate_actor(i) for i in range(1, 61)]

# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/overview")
async def actors_overview():
    by_sector = {}
    by_role = {}
    by_country = {}
    by_status = {}

    for a in _actor_pool:
        s = a["sector"]
        by_sector[s] = by_sector.get(s, 0) + 1
        r = a["role"]
        by_role[r] = by_role.get(r, 0) + 1
        c = a["country_name"]
        by_country[c] = by_country.get(c, 0) + 1
        st = a["status"]
        by_status[st] = by_status.get(st, 0) + 1

    sector_colors = {
        "vegetal": "#16A34A", "animal": "#D97706", "halieutique": "#0891B2",
        "forestier": "#92400E", "minier": "#6B7280", "industriel": "#4F46E5",
    }
    status_colors = {"active": "#22C55E", "inactive": "#6B7280", "pending": "#EAB308", "verified": "#3B82F6"}

    return {
        "total_actors": len(_actor_pool),
        "active_actors": sum(1 for a in _actor_pool if a["is_active"]),
        "verified_actors": sum(1 for a in _actor_pool if a["is_verified"]),
        "featured_actors": sum(1 for a in _actor_pool if a["is_featured"]),
        "by_sector": [{"sector": k, "count": v, "color": sector_colors[k]} for k, v in sorted(by_sector.items(), key=lambda x: -x[1])],
        "by_role": [{"role": k, "count": v} for k, v in sorted(by_role.items(), key=lambda x: -x[1])[:10]],
        "by_country": [{"country": k, "count": v} for k, v in sorted(by_country.items(), key=lambda x: -x[1])],
        "by_status": [{"status": k, "count": v, "color": status_colors[k]} for k, v in sorted(by_status.items(), key=lambda x: -x[1])],
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
):
    items = _actor_pool

    if search:
        s = search.lower()
        items = [a for a in items if s in a["name"].lower() or s in a.get("organisation", "").lower() or s in a.get("city", "").lower()]
    if sector and sector != "all":
        items = [a for a in items if a["sector"] == sector]
    if role and role != "all":
        items = [a for a in items if a["role"] == role]
    if country and country != "all":
        items = [a for a in items if a["country"] == country]
    if status and status != "all":
        items = [a for a in items if a["status"] == status]
    if region and region != "all":
        items = [a for a in items if a.get("region") == region]

    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    data = items[start:end]

    return {
        "data": data,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page) if total > 0 else 1,
        "has_next": end < total,
        "has_prev": page > 1,
    }

@router.get("/{actor_id}")
async def get_actor(actor_id: str):
    actor = next((a for a in _actor_pool if a["id"] == actor_id), None)
    if not actor:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")
    return actor

@router.get("/{actor_id}/activity")
async def get_actor_activity(actor_id: str):
    activities = [
        {"type": "profile_view", "count": _rand_int(10, 500)},
        {"type": "contact_click", "count": _rand_int(1, 50)},
        {"type": "review_posted", "count": _rand_int(0, 20)},
    ]
    return {
        "actor_id": actor_id,
        "activities": activities,
        "total_views": _rand_int(100, 10000),
        "total_contacts": _rand_int(5, 500),
        "trend": _pick(["up", "down", "stable"]),
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
