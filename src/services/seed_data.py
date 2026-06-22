"""
Seed script to populate all tables with realistic agricultural data for West Africa.
Run with: python -m src.services.seed_data
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta, date, timezone
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import async_session_maker
from config.config import get_settings
from src.services.auth import AuthService
from api.models.sql.actors import (
    Actor,
    ProducteurVegetal,
    EleveurAnimal,
    PecheurHalieutique,
    ExploitantForestier,
    SousSecteursEnum,
    ActorRoleEnum,
)
from api.models.sql.indicators import (
    IndicateurValeur,
    IndicateurVegetal,
    IndicateurAnimal,
    IndicateurHalieutique,
    IndicateurForestier,
    CategorieIndicateurEnum,
    TypeIndicateurEnum,
    UniteIndicateurEnum,
    PeriodeIndicateurEnum,
)
from api.models.sql.agricultural import (
    Alert,
    Country,
    Crop,
    Production,
    StagingProduction,
    StagingWeather,
    StagingEconomic,
    MalaboYieldIndicator,
)
from api.models.sql.user import User

settings = get_settings()

COUNTRIES = [
    {"name": "Sénégal", "code": "SN"},
    {"name": "Côte d'Ivoire", "code": "CI"},
    {"name": "Mali", "code": "ML"},
    {"name": "Burkina Faso", "code": "BF"},
    {"name": "Niger", "code": "NE"},
    {"name": "Bénin", "code": "BJ"},
    {"name": "Togo", "code": "TG"},
    {"name": "Ghana", "code": "GH"},
    {"name": "Nigéria", "code": "NG"},
    {"name": "Cameroun", "code": "CM"},
]

CROPS = [
    {"name": "Riz", "code": 1},
    {"name": "Maïs", "code": 2},
    {"name": "Mil", "code": 3},
    {"name": "Sorgho", "code": 4},
    {"name": "Arachide", "code": 5},
    {"name": "Niébé", "code": 6},
    {"name": "Coton", "code": 7},
    {"name": "Manioc", "code": 8},
    {"name": "Igname", "code": 9},
    {"name": "Banane plantain", "code": 10},
    {"name": "Cacao", "code": 11},
    {"name": "Café", "code": 12},
    {"name": "Anacarde", "code": 13},
    {"name": "Palmier à huile", "code": 14},
    {"name": "Hévéa", "code": 15},
]

REGIONS = {
    "SN": [
        "Dakar",
        "Thiès",
        "Saint-Louis",
        "Kaolack",
        "Ziguinchor",
        "Louga",
        "Diourbel",
        "Fatick",
        "Kolda",
        "Tambacounda",
    ],
    "CI": ["Abidjan", "Bouaké", "Yamoussoukro", "San-Pédro", "Korhogo", "Daloa", "Man"],
    "ML": [
        "Bamako",
        "Sikasso",
        "Kayes",
        "Mopti",
        "Ségou",
        "Tombouctou",
        "Gao",
        "Kidal",
    ],
    "BF": ["Ouagadougou", "Bobo-Dioulasso", "Koudougou", "Ouahigouya", "Banfora"],
    "NE": ["Niamey", "Zinder", "Maradi", "Tahoua", "Agadez", "Dosso"],
    "BJ": ["Cotonou", "Porto-Novo", "Parakou", "Abomey-Calavi", "Ouidah"],
    "TG": ["Lomé", "Kara", "Sokodé", "Tsévié", "Atakpamé"],
    "GH": ["Accra", "Kumasi", "Takoradi", "Tamale", "Cape Coast"],
    "NG": ["Lagos", "Abuja", "Kano", "Ibadan", "Port Harcourt", "Kaduna"],
    "CM": ["Douala", "Yaoundé", "Garoua", "Bamenda", "Maroua"],
}

FIRST_NAMES_MALE = [
    "Amadou",
    "Mamadou",
    "Ousmane",
    "Souleymane",
    "Ibrahima",
    "Moussa",
    "Modou",
    "Cheikh",
    "Abdoulaye",
    "Bakary",
    "Drissa",
    "Koffi",
    "Yao",
    "Kwame",
    "Tunde",
    "Emeka",
    "Jean-Pierre",
    "Hervé",
    "Guy",
    "Patrice",
]
FIRST_NAMES_FEMALE = [
    "Fatou",
    "Aïssatou",
    "Kadiatou",
    "Mariam",
    "Aminata",
    "Rokhaya",
    "Ndèye",
    "Khady",
    "Fanta",
    "Adama",
    "Salimata",
    "Awa",
    "Akissi",
    "Esi",
    "Chiamaka",
    "Ngozi",
    "Marie-Claire",
    "Bénédicte",
    "Jeanne",
    "Odette",
]
LAST_NAMES = [
    "Diop",
    "Ndiaye",
    "Fall",
    "Koné",
    "Traoré",
    "Diallo",
    "Sow",
    "Ba",
    "Sy",
    "Gueye",
    "Cissé",
    "Mendy",
    "Faye",
    "Sarr",
    "Kane",
    "Ngom",
    "Thiam",
    "Dieng",
    "Dione",
    "Camara",
    "Keita",
    "Touré",
    "Coulibaly",
    "Ouattara",
    "Bamba",
    "Kouassi",
    "Mensah",
    "Asante",
    "Okonkwo",
]

ACTOR_ROLES_BY_SECTOR = {
    "vegetal": [
        "producteur_individuel",
        "exploitation_familiale",
        "cooperative_agricole",
        "transformateur_artisanal",
        "commercant",
    ],
    "animal": [
        "eleveur_bovins",
        "eleveur_ovins",
        "eleveur_caprins",
        "eleveur_volailles",
        "transformateur_laitier",
        "commercant_betail",
    ],
    "halieutique": [
        "pecheur_artisanal",
        "pecheur_industriel",
        "mareyeur",
        "transformateur_fumeur",
        "femme_commercante_poisson",
    ],
    "forestier": [
        "exploitant_forestier",
        "collecteur_pfnl",
        "charbonnier",
        "artisan_bois",
        "cooperative_agroforesterie",
    ],
}


def _rand(min_v, max_v, decimals=2):
    return round(random.uniform(min_v, max_v), decimals)


def _rand_int(min_v, max_v):
    return random.randint(min_v, max_v)


async def seed_countries(db: AsyncSession):
    for c in COUNTRIES:
        existing = await db.execute(select(Country).where(Country.code == c["code"]))
        if not existing.scalar_one_or_none():
            db.add(Country(name=c["name"], code=c["code"]))
    await db.commit()
    print("✅ Countries seeded")


async def seed_crops(db: AsyncSession):
    for c in CROPS:
        existing = await db.execute(select(Crop).where(Crop.code == c["code"]))
        if not existing.scalar_one_or_none():
            db.add(Crop(name=c["name"], code=c["code"]))
    await db.commit()
    print("✅ Crops seeded")


async def seed_actors(db: AsyncSession, count: int = 60):
    existing = await db.execute(select(Actor).limit(1))
    if existing.scalar_one_or_none():
        print("⚠️  Actors already exist, skipping")
        return

    countries_db = {
        c.code: c for c in (await db.execute(select(Country))).scalars().all()
    }

    actors_created = 0
    for i in range(count):
        country_code = random.choice(list(COUNTRIES))
        country = countries_db[country_code["code"]]
        sector = random.choice(list(ACTOR_ROLES_BY_SECTOR.keys()))
        role = random.choice(ACTOR_ROLES_BY_SECTOR[sector])
        gender = "M" if random.random() > 0.4 else "F"
        first_names = FIRST_NAMES_MALE if gender == "M" else FIRST_NAMES_FEMALE
        first_name = random.choice(first_names)
        last_name = random.choice(LAST_NAMES)
        region = random.choice(REGIONS[country_code["code"]])
        commune = f"{region}-ville" if random.random() > 0.4 else region

        actor = Actor(
            nom=f"{first_name} {last_name}",
            prenom=first_name,
            nom_organisation=f"Coopérative {last_name}"
            if random.random() > 0.6
            else None,
            sous_secteur=sector,
            role=role,
            telephone=f"+221 77 {_rand_int(100, 999)} {_rand_int(10, 99)} {_rand_int(10, 99)}"
            if random.random() > 0.2
            else None,
            email=f"{first_name.lower()}.{last_name.lower()}.{i}@example.com"
            if random.random() > 0.2
            else None,
            pays=country.name,
            region=region,
            commune=commune,
            village=f"Village {last_name}" if random.random() > 0.5 else None,
            latitude=_rand(12.0, 16.0),
            longitude=_rand(-17.0, -12.0),
            age=_rand_int(25, 70),
            genre=gender,
            niveau_education=random.choice(
                ["aucun", "primaire", "secondaire", "supérieur"]
            ),
            taille_menage=_rand_int(3, 15),
            nombre_enfants=_rand_int(0, 8),
            acces_electricite=random.random() > 0.3,
            acces_eau_potable=random.random() > 0.4,
            is_active=random.random() > 0.2,
            is_verified=random.random() > 0.6,
            metadonnees_specifiques={
                "experience_ans": _rand_int(2, 40),
                "type_exploitation": "familiale"
                if random.random() > 0.3
                else "commerciale",
            },
        )
        db.add(actor)
        await db.flush()

        # Sector-specific data
        if sector == "vegetal":
            crops = random.sample(CROPS, k=min(_rand_int(1, 4), len(CROPS)))
            db.add(
                ProducteurVegetal(
                    id=actor.id,
                    superficie_totale_ha=Decimal(str(_rand(1, 50, 2))),
                    superficie_cultivee_ha=Decimal(str(_rand(0.5, 30, 2))),
                    nombre_parcelles=_rand_int(1, 6),
                    cultures_principales=[c["name"] for c in crops[:2]],
                    cultures_secondaires=[c["name"] for c in crops[2:]],
                    possede_tracteur=random.random() > 0.7,
                    possede_motoculteur=random.random() > 0.6,
                    acces_irrigation=random.random() > 0.4,
                    type_irrigation=random.choice(
                        ["goutte-à-goutte", "aspersion", "gravitaire", "californien"]
                    )
                    if random.random() > 0.4
                    else None,
                    membre_cooperative=random.random() > 0.5,
                )
            )
        elif sector == "animal":
            db.add(
                EleveurAnimal(
                    id=actor.id,
                    nombre_bovins=_rand_int(0, 50),
                    nombre_ovins=_rand_int(0, 80),
                    nombre_caprins=_rand_int(0, 40),
                    nombre_volailles=_rand_int(0, 100),
                    nombre_porcins=_rand_int(0, 20),
                    type_elevage=random.choice(
                        ["extensif", "semi-intensif", "intensif"]
                    ),
                    orientation_principale=random.choice(
                        ["viande", "lait", "mixte", "œufs"]
                    ),
                    possede_etable=random.random() > 0.5,
                    superficie_paturage_ha=Decimal(str(_rand(0, 20, 2)))
                    if random.random() > 0.3
                    else None,
                    acces_veterinaire=random.random() > 0.4,
                )
            )
        elif sector == "halieutique":
            db.add(
                PecheurHalieutique(
                    id=actor.id,
                    type_peche=random.choice(
                        ["artisanale", "industrielle", "lagunaire", "continentale"]
                    ),
                    zone_peche_principale=random.choice(
                        ["côtière", "haute mer", "fleuve", "lac"]
                    ),
                    nombre_pirogues=_rand_int(1, 5),
                    nombre_filets=_rand_int(1, 20),
                    possede_moteur=random.random() > 0.3,
                    puissance_moteur_cv=_rand_int(8, 60)
                    if random.random() > 0.3
                    else None,
                    membre_groupement_pecheurs=random.random() > 0.5,
                    acces_chambre_froide=random.random() > 0.6,
                )
            )
        elif sector == "forestier":
            db.add(
                ExploitantForestier(
                    id=actor.id,
                    type_exploitation=random.choice(
                        ["coupe", "collecte PFNL", "écorçage", "reboisement"]
                    ),
                    produits_principaux=random.sample(
                        [
                            "bois d'œuvre",
                            "bois de chauffe",
                            "charbon",
                            "miel",
                            "gomme arabique",
                            "karité",
                            "feuilles",
                        ],
                        k=_rand_int(1, 3),
                    ),
                    superficie_concession_ha=Decimal(str(_rand(1, 100, 2))),
                    a_titre_foncier=random.random() > 0.6,
                    pratique_reboisement=random.random() > 0.5,
                    certifie_durable=random.random() > 0.8,
                )
            )

        actors_created += 1
        if actors_created % 20 == 0:
            await db.flush()
            print(f"  → {actors_created}/{count} actors created")

    await db.commit()
    print(f"✅ {actors_created} actors seeded")


async def seed_production_data(db: AsyncSession):
    """Seed staging_production and main production table"""
    existing = await db.execute(select(StagingProduction).limit(1))
    if existing.scalar_one_or_none():
        print("⚠️  Production data already exists, skipping")
        return

    countries_db = {
        c.code: c for c in (await db.execute(select(Country))).scalars().all()
    }
    crops_db = {c.code: c for c in (await db.execute(select(Crop))).scalars().all()}

    base_yields = {
        "Riz": (2.5, 5.0),
        "Maïs": (1.5, 3.5),
        "Mil": (0.8, 1.8),
        "Sorgho": (1.0, 2.5),
        "Arachide": (0.8, 2.0),
        "Niébé": (0.5, 1.2),
        "Coton": (1.0, 2.5),
        "Manioc": (6.0, 15.0),
        "Igname": (8.0, 18.0),
        "Banane plantain": (5.0, 12.0),
        "Cacao": (0.3, 0.8),
        "Café": (0.2, 0.6),
        "Anacarde": (0.5, 1.5),
        "Palmier à huile": (8.0, 15.0),
        "Hévéa": (1.0, 2.5),
    }

    for country in COUNTRIES:
        c_db = countries_db[country["code"]]
        for crop in CROPS:
            if random.random() > 0.3:  # ~70% of crop-country combos have data
                base_min, base_max = base_yields.get(crop["name"], (1.0, 3.0))
                for year in range(2020, 2025):
                    value = _rand(base_min, base_max)
                    production_tonnes = value * _rand(1000, 50000)
                    c = crops_db[crop["code"]]

                    sp = StagingProduction(
                        country_code=country["code"],
                        country_name=country["name"],
                        crop_code=crop["code"],
                        crop_name=crop["name"],
                        year=year,
                        value=value,
                        unit="kg/ha",
                        source="FAO",
                        quality_score=_rand(0.7, 1.0),
                        is_validated=1 if random.random() > 0.3 else 0,
                    )
                    db.add(sp)

                    # Also add summary production
                    p = Production(
                        year=year,
                        production_tonnes=production_tonnes,
                        yield_tonnes_per_ha=value,
                        country_id=c_db.id,
                        crop_id=c.id,
                    )
                    db.add(p)

        await db.flush()
        print(f"  → Production data for {country['name']}")

    await db.commit()
    print("✅ Production data seeded")


async def seed_indicators(db: AsyncSession):
    """Seed indicator values for actors"""
    existing = await db.execute(select(IndicateurValeur).limit(1))
    if existing.scalar_one_or_none():
        print("⚠️  Indicators already exist, skipping")
        return

    actors = (
        (await db.execute(select(Actor).where(Actor.is_active == True))).scalars().all()
    )
    indicator_count = 0

    categories = {
        "vegetal": [
            ("revenus", ["revenu_annuel"], "XOF"),
            ("comptes_exploitation", ["chiffre_affaires"], "XOF"),
        ],
        "animal": [
            ("revenus", ["revenu_annuel"], "XOF"),
            ("sante", ["couverture_veterinaire"], "binaire"),
        ],
        "halieutique": [
            ("revenus", ["revenu_mensuel"], "XOF"),
        ],
        "forestier": [
            ("revenus", ["revenu_annuel"], "XOF"),
        ],
    }

    for actor in actors:
        sector = actor.sous_secteur.value
        cats = categories.get(sector, categories["vegetal"])
        for cat, types, unit in cats:
            for t in types:
                val = IndicateurValeur(
                    actor_id=actor.id,
                    sous_secteur=actor.sous_secteur,
                    categorie=cat,
                    type_indicateur=t,
                    valeur_numerique=Decimal(str(_rand(50000, 5000000, 2)))
                    if unit == "XOF"
                    else Decimal(str(_rand_int(0, 1))),
                    unite=unit,
                    periode="annuelle",
                    date_debut=date(2024, 1, 1),
                    date_fin=date(2024, 12, 31),
                    annee=2024,
                    source="enquête terrain",
                    qualite_donnee=_rand(0.6, 1.0),
                    is_valide=True,
                )
                db.add(val)
                indicator_count += 1

        if indicator_count % 50 == 0:
            await db.flush()

    await db.commit()
    print(f"✅ {indicator_count} indicator values seeded")


async def seed_weather_data(db: AsyncSession):
    """Seed staging weather data"""
    existing = await db.execute(select(StagingWeather).limit(1))
    if existing.scalar_one_or_none():
        print("⚠️  Weather data already exists, skipping")
        return

    cities = [
        ("Dakar", "SN", 14.7645, -17.3660),
        ("Bamako", "ML", 12.6392, -8.0029),
        ("Ouagadougou", "BF", 12.3714, -1.5197),
        ("Niamey", "NE", 13.5127, 2.1126),
        ("Abidjan", "CI", 5.3600, -4.0083),
        ("Lomé", "TG", 6.1728, 1.2315),
        ("Cotonou", "BJ", 6.3654, 2.4183),
        ("Accra", "GH", 5.6037, -0.1870),
        ("Lagos", "NG", 6.5244, 3.3792),
        ("Douala", "CM", 4.0511, 9.7679),
    ]

    weather_count = 0
    for city, country, lat, lon in cities:
        for day_offset in range(0, 90):
            day = datetime.now(timezone.utc) - timedelta(days=day_offset)
            w = StagingWeather(
                city=city,
                country=country,
                temperature=_rand(22, 38),
                humidity=_rand(40, 95),
                precipitation=_rand(0, 50) if random.random() > 0.4 else 0,
                date=day,
                lat=lat,
                lon=lon,
                elevation=_rand(0, 300),
                weather_condition=random.choice(
                    ["Ensoleillé", "Nuageux", "Pluie", "Orages"]
                ),
                wind_speed=_rand(0, 30),
                pressure=_rand(1008, 1016),
                source="openweather",
                quality_score=_rand(0.8, 1.0),
            )
            db.add(w)
            weather_count += 1
            if weather_count % 200 == 0:
                await db.flush()

    await db.commit()
    print(f"✅ {weather_count} weather records seeded")


async def seed_economic_data(db: AsyncSession):
    """Seed staging economic data"""
    existing = await db.execute(select(StagingEconomic).limit(1))
    if existing.scalar_one_or_none():
        print("⚠️  Economic data already exists, skipping")
        return

    indicators = [
        "gdp",
        "inflation",
        "agricultural_gdp",
        "employment",
        "export",
        "import",
    ]
    econ_count = 0
    for country in COUNTRIES:
        for indicator_name in indicators:
            for year in range(2020, 2025):
                base = {
                    "gdp": 15,
                    "inflation": 3,
                    "agricultural_gdp": 20,
                    "employment": 50,
                    "export": 30,
                    "import": 35,
                }
                eco = StagingEconomic(
                    country_code=country["code"],
                    country_name=country["name"],
                    indicator=indicator_name,
                    year=year,
                    value=_rand(base[indicator_name] * 0.7, base[indicator_name] * 1.3),
                    unit="%"
                    if indicator_name in ("inflation", "agricultural_gdp", "employment")
                    else "USD_B",
                    source="World Bank",
                    is_estimated=1 if random.random() > 0.7 else 0,
                )
                db.add(eco)
                econ_count += 1
        await db.flush()

    await db.commit()
    print(f"✅ {econ_count} economic records seeded")


async def seed_alerts(db: AsyncSession):
    """Seed alerts for the admin user"""
    existing = await db.execute(select(Alert).limit(1))
    if existing.scalar_one_or_none():
        print("⚠️  Alerts already exist, skipping")
        return

    user = (
        await db.execute(select(User).where(User.username == "admin"))
    ).scalar_one_or_none()
    if not user:
        print("⚠️  Admin user not found, skipping alerts")
        return

    countries_db = {
        c.code: c for c in (await db.execute(select(Country))).scalars().all()
    }
    crops_db = {c.name: c for c in (await db.execute(select(Crop))).scalars().all()}

    alert_templates = [
        {
            "title": "Sécheresse modérée détectée",
            "message": "Les précipitations sont inférieures de 30% à la moyenne saisonnière dans la région de {region}, {country}. Risque pour les cultures de {crop}.",
            "type": "weather",
            "severity": "warning",
        },
        {
            "title": "Alerte inondation",
            "message": "Risque élevé d'inondation dans le delta du fleuve à {region}, {country}. Les cultures de {crop} sont menacées.",
            "type": "weather",
            "severity": "critical",
        },
        {
            "title": "Hausse des prix du {crop}",
            "message": "Le prix du {crop} a augmenté de 15% sur le marché de {region}, {country}. Tendance haussière prévue.",
            "type": "market",
            "severity": "warning",
        },
        {
            "title": "Baisse des prix du {crop}",
            "message": "Le prix du {crop} a chuté de 20% à {region}, {country}. Impact potentiel sur les revenus des producteurs.",
            "type": "market",
            "severity": "info",
        },
        {
            "title": "Épizootie signalée",
            "message": "Cas de fièvre aphteuse signalés dans la région de {region}, {country}. Surveillance renforcée recommandée.",
            "type": "health",
            "severity": "critical",
        },
        {
            "title": "Risque de feux de brousse",
            "message": "Conditions sèches dans {region}, {country}. Risque accru de feux de brousse pour les zones forestières.",
            "type": "weather",
            "severity": "warning",
        },
        {
            "title": "Opportunité de marché",
            "message": "Nouveau programme d'achat de {crop} lancé par l'État dans {region}, {country}. Prix garanti.",
            "type": "market",
            "severity": "info",
        },
        {
            "title": "Alerte nutritionnelle",
            "message": "Signes de malnutrition dans les ménages agricoles de {region}, {country}. Distribution de vivres recommandée.",
            "type": "system",
            "severity": "emergency",
        },
    ]

    alerts_created = 0
    for template in alert_templates:
        for _ in range(_rand_int(1, 4)):
            country = random.choice(COUNTRIES)
            region = random.choice(REGIONS[country["code"]])
            crop = random.choice(CROPS)

            alert = Alert(
                title=template["title"].format(
                    crop=crop["name"], region=region, country=country["name"]
                ),
                message=template["message"].format(
                    crop=crop["name"], region=region, country=country["name"]
                ),
                alert_type=template["type"],
                severity=template["severity"],
                is_read=random.random() > 0.5,
                user_id=user.id if random.random() > 0.3 else None,
                country_id=countries_db[country["code"]].id
                if random.random() > 0.3
                else None,
                crop_id=crops_db[crop["name"]].id if random.random() > 0.5 else None,
                created_at=datetime.now(timezone.utc) - timedelta(days=_rand_int(0, 30)),
            )
            db.add(alert)
            alerts_created += 1

    await db.commit()
    print(f"✅ {alerts_created} alerts seeded")


async def seed_malabo_data(db: AsyncSession):
    """Seed Malabo yield indicators"""
    existing = await db.execute(select(MalaboYieldIndicator).limit(1))
    if existing.scalar_one_or_none():
        print("⚠️  Malabo data already exists, skipping")
        return

    for country in COUNTRIES:
        for crop in CROPS:
            if random.random() > 0.5:
                for year in range(2018, 2025):
                    m = MalaboYieldIndicator(
                        country_name=country["name"],
                        crop_name=crop["name"],
                        year=year,
                        production_tonnes=_rand(1000, 500000),
                    )
                    db.add(m)
        await db.flush()

    await db.commit()
    print("✅ Malabo yield indicators seeded")


async def main():
    print("🌾 Seeding AgriIntel360 database...\n")
    async with async_session_maker() as db:
        await seed_countries(db)
        await seed_crops(db)
        await seed_actors(db, count=60)
        await seed_production_data(db)
        await seed_indicators(db)
        await seed_weather_data(db)
        await seed_economic_data(db)
        await seed_alerts(db)
        await seed_malabo_data(db)
    print("\n✅ Database seeding complete!")


if __name__ == "__main__":
    asyncio.run(main())
