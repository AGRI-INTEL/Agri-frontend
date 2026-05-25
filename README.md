
---

# 🌾 AgriIntel— Backend

**Plateforme Intelligente de Décision Agricole pour l'Afrique**

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![License](https://img.shields.io/badge/License-Proprietary-FF6B6B?style=for-the-badge)]()

> **API REST asynchrone** couvrant 4 sous-secteurs agricoles : **Végétal**, **Animal**, **Halieutique** et **Forestier** — avec intelligence artificielle, géolocalisation, communautés et monitoring temps réel.

---

## 📋 Table des matières

- [Architecture](#-architecture)
- [Stack Technique](#-stack-technique)
- [Fonctionnalités](#-fonctionnalités)
- [Prérequis](#-prérequis)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Démarrage](#-démarrage)
- [Documentation API](#-documentation-api)
- [Endpoints](#-endpoints)
- [Modèles de Données](#-modèles-de-données)
- [Déploiement](#-déploiement)
- [Monitoring & Santé](#-monitoring--santé)
- [Sécurité](#-sécurité)
- [Licence](#-licence)

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENTS                              │
│         (Web App, Mobile, Dashboard, IoT Sensors)           │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                    FASTAPI BACKEND                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │
│  │   Auth &    │ │  Chatbot    │ │   Communautés &         │ │
│  │   Sécurité  │ │    IA/LLM   │ │   Gestion Fichiers      │ │
│  └─────────────┘ └─────────────┘ └─────────────────────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │
│  │  Indicateurs│ │   Alertes   │ │   Pipeline ETL          │ │
│  │  & Calculs  │ │  & Notifs   │ │   (Airflow)             │ │
│  └─────────────┘ └─────────────┘ └─────────────────────────┘ │
└──────────────────────┬──────────────────────────────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    │                  │                  │
┌───▼────┐      ┌──────▼──────┐    ┌────▼─────┐
│PostgreSQL│      │   MongoDB   │    │  Redis   │
│(SQLAlchemy│      │  (Documents)│    │(Cache/   │
│  async)  │      │             │    │ Sessions)│
└─────────┘      └─────────────┘    └──────────┘
    │
┌───▼────────┐  ┌─────────────┐  ┌─────────────┐
│Elasticsearch│  │   Twilio    │  │  Prometheus │
│  (Search)   │  │    (SMS)    │  │  (Metrics)  │
└─────────────┘  └─────────────┘  └─────────────┘
```

---

## 🛠 Stack Technique

| Couche | Technologie | Usage |
|--------|-------------|-------|
| **Framework** | FastAPI (async) | API REST haute performance |
| **ORM** | SQLAlchemy 2.0 (async) | Modélisation PostgreSQL |
| **Bases de données** | PostgreSQL 15+ | Données relationnelles |
| | MongoDB | Données documentaires |
| | Redis | Cache, sessions, blacklist JWT |
| | Elasticsearch | Recherche full-text |
| **Auth** | JWT (PyJWT) | Access + Refresh tokens |
| **2FA** | TOTP | Authentification forte |
| **LLM/IA** | OpenRouter (Kimi, DeepSeek) | Chatbot intelligent |
| | OpenAI GPT | Fallback IA |
| **Notifications** | fastapi-mail (Email) | Templates HTML |
| | Twilio (SMS) | Alertes mobiles |
| | WebSocket | Temps réel |
| **ETL** | Apache Airflow | Pipeline données FAOSTAT, OWM, World Bank |
| **Monitoring** | Prometheus | Métriques |
| | Sentry | Traçage erreurs |
| | psutil | Métriques système |
| **DevOps** | Docker + docker-compose | Conteneurisation |
| **Migrations** | Alembic | Gestion schéma DB |

---

## ✨ Fonctionnalités

### 🔐 Authentification & Sécurité
- Inscription avec **vérification email** par token sécurisé
- Login **JWT** (access token + refresh token)
- **Blacklist Redis** des tokens à la déconnexion
- **Verrouillage compte** après 5 tentatives échouées (30 min)
- **2FA TOTP** — setup, vérification, désactivation
- **Clés API programmatiques** (création, liste, révocation)
- **RBAC hiérarchique** — rôles : `admin`, `analyst`, `user`, `guest`
- Permissions granulaires par **module/ressource/action**

### 🤖 Chatbot IA — AgriBot
- Spécialisé **agriculture africaine**
- Multi-providers LLM : **Kimi (Moonshot)**, **DeepSeek**, **OpenAI GPT**
- **Génération SQL sécurisée** (SELECT uniquement) pour requêtes données
- Historique conversation (10 derniers échanges)
- Mode démo sans clé API
- Bascule dynamique entre providers

### 👥 Communautés & Groupes
- Groupes : `public`, `privé`, `professionnel`, `recherche`, `régional`, `thématique`
- Adhésion directe ou avec **approbation**
- **Invitations par email** avec token
- Publications multi-types : texte, image, vidéo, document, lien, sondage, événement
- Commentaires avec **réponses imbriquées**
- Réactions : 👍 like, ❤️ love, ✅ useful, 😂 funny, 😠 angry, 😢 sad
- Rôles : `owner`, `admin`, `moderator`, `member`, `guest`

### 📁 Gestion des Fichiers
- Upload : images (10MB), vidéos (100MB), audio (50MB), documents (25MB), archives (100MB)
- **Validation MIME type** + extension (blocage extensions dangereuses)
- Organisation en **dossiers arborescents**
- Permissions granulaires : `view`, `download`, `edit`, `delete`, `share`
- Extraction métadonnées images (PIL)
- Stockage local structuré `YYYY/MM/DD`
- Journal d'activité complet

### 🔔 Alertes & Notifications
- Types : météo, prix, rendement, sécheresse, inondation, ravageurs, marché, système
- Niveaux : `info`, `warning`, `critical`, `emergency`
- Canaux : **Email (HTML)**, **SMS (Twilio)**, **WebSocket temps réel**
- Seuils configurables par indicateur/secteur/région
- **Déduplication** 24h + TTL Redis 7 jours
- Alertes sectorielles intelligentes :
  - 🌱 Végétal : rendement < moyenne régionale
  - 🐄 Animal : mortalité cheptel > 10%
  - 🎣 Halieutique : captures en baisse de 50%
  - 🌲 Forestier : surexploitation détectée

### 📊 Indicateurs & Calculs
- **60+ types d'indicateurs** — 6 catégories : comptes d'exploitation, revenus, pauvreté, nutrition, santé, bien-être
- Historisation complète (mensuelle, trimestrielle, semestrielle, annuelle)
- Calculs avancés :
  - Seuil de pauvreté contextualisé (taille ménage + facteur régional)
  - Vulnérabilité saisonnière (CV des revenus)
  - Score diversité alimentaire FAO (10 groupes)
  - Marge brute, rendement/hectare, bénéfice net élevage
  - Productivité laitière vs standard régional
  - Valeur ajoutée transformation PFNL
- Vue matérialisée pour agrégations statistiques

### 🔄 Pipeline ETL (Apache Airflow)
- DAG quotidien parallélisé :
  - **FAOSTAT** — données de production agricole
  - **OpenWeatherMap** — météo capitales africaines
  - **World Bank** — PIB, inflation, emploi, export/import
- Validation Pydantic à chaque étape
- Tables staging PostgreSQL + agrégation indicateurs Malabo
- Simulation prédictions ML

### 📍 Géolocalisation
- Calcul distance entre deux points (lat/lon)
- Recherche lieux proches (centres agricoles, stations météo)

---

## 📦 Prérequis

- **Python** 3.11+
- **Docker** & **Docker Compose** (recommandé)
- **PostgreSQL** 15+
- **Redis** 7+
- **MongoDB** 6+ (optionnel)
- **Elasticsearch** 8+ (optionnel)

---

## 🚀 Installation

### Option 1 : Docker (Recommandé)

```bash
# Cloner le repository
git clone https://github.com/votre-org/agriintel360-backend.git
cd agriintel360-backend

# Copier et configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos credentials

# Lancer l'ensemble de la stack
docker-compose up -d --build

# Vérifier les services
docker-compose ps
```

### Option 2 : Installation Manuelle

```bash
# Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env

# Exécuter les migrations
alembic upgrade head

# Lancer le serveur
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## ⚙ Configuration

Créer un fichier `.env` à la racine :

```env
# === Application ===
APP_NAME=AgriIntel360
APP_VERSION=1.0.0
DEBUG=false
ENVIRONMENT=production  # development | staging | production

# === Base de données ===
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/agriintel360
MONGODB_URL=mongodb://localhost:27017/agriintel360
REDIS_URL=redis://localhost:6379/0
ELASTICSEARCH_URL=http://localhost:9200

# === Sécurité ===
SECRET_KEY=votre-cle-secrete-tres-longue-et-aleatoire
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION_MINUTES=30

# === Email (fastapi-mail) ===
MAIL_USERNAME=noreply@agriintel360.com
MAIL_PASSWORD=votre-mot-de-passe-app
MAIL_FROM=noreply@agriintel360.com
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
MAIL_TLS=true

# === SMS (Twilio) ===
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+1234567890

# === LLM / OpenRouter ===
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEFAULT_LLM_PROVIDER=kimi  # kimi | deepseek | openai

# === Monitoring ===
SENTRY_DSN=https://xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@o000000.ingest.sentry.io/0000000
PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

# === Fichiers ===
UPLOAD_DIR=/app/uploads
MAX_IMAGE_SIZE=10485760        # 10MB
MAX_VIDEO_SIZE=104857600       # 100MB
MAX_AUDIO_SIZE=52428800        # 50MB
MAX_DOCUMENT_SIZE=26214400     # 25MB
MAX_ARCHIVE_SIZE=104857600     # 100MB
```

---

## ▶ Démarrage

```bash
# Mode développement (hot reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Mode production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Avec Docker Compose
docker-compose up -d
```

---

## 📚 Documentation API

Une fois le serveur démarré, accédez à :

| Ressource | URL |
|-----------|-----|
| **Swagger UI** | `http://localhost:8000/api/v1/docs` |
| **ReDoc** | `http://localhost:8000/api/v1/redoc` |
| **OpenAPI JSON** | `http://localhost:8000/api/v1/openapi.json` |

---

## 🔗 Endpoints

### Authentification (`/api/v1/auth`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/register` | Inscription + vérification email |
| `POST` | `/login` | Connexion JWT |
| `POST` | `/logout` | Déconnexion + blacklist token |
| `POST` | `/refresh` | Renouvellement access token |
| `POST` | `/change-password` | Changement mot de passe |
| `POST` | `/reset-password` | Reset par email |
| `POST` | `/verify-email` | Vérification email par token |
| `POST` | `/2fa/setup` | Configuration 2FA TOTP |
| `POST` | `/2fa/verify` | Vérification code 2FA |
| `POST` | `/api-keys` | Création clé API |
| `GET` | `/api-keys` | Liste des clés API |
| `DELETE` | `/api-keys/{id}` | Révocation clé API |

### Utilisateurs (`/api/v1/users`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/` | Liste des utilisateurs |
| `GET` | `/{user_id}` | Profil utilisateur |
| `PUT` | `/{user_id}` | Mise à jour profil |
| `DELETE` | `/{user_id}` | Suppression compte |
| `GET` | `/stats/overview` | Statistiques utilisateurs |

### Chatbot IA (`/api/v1/chatbot`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/chat` | Conversation avec AgriBot |
| `GET` | `/suggestions` | Questions suggérées |
| `POST` | `/clear-history` | Effacer historique |
| `POST` | `/switch-provider` | Changer de provider LLM |
| `GET` | `/status` | Statut du chatbot |
| `POST` | `/feedback` | Soumettre feedback |
| `GET` | `/history` | Historique conversations |

### Communautés (`/api/v1/community`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/groups` | Créer un groupe |
| `GET` | `/groups` | Rechercher des groupes |
| `GET` | `/groups/{id}` | Détails groupe |
| `PUT` | `/groups/{id}` | Modifier groupe |
| `POST` | `/groups/{id}/join` | Rejoindre un groupe |
| `POST` | `/groups/{id}/leave` | Quitter un groupe |
| `POST` | `/posts` | Créer une publication |
| `GET` | `/groups/{id}/posts` | Publications du groupe |
| `POST` | `/posts/{id}/reactions` | Ajouter une réaction |
| `POST` | `/comments` | Ajouter un commentaire |

### Fichiers (`/api/v1/files`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/upload` | Upload fichier |
| `POST` | `/upload-multiple` | Upload multiple |
| `GET` | `/files/{id}` | Détails fichier |
| `PUT` | `/files/{id}` | Modifier fichier |
| `DELETE` | `/files/{id}` | Supprimer fichier |
| `GET` | `/files` | Recherche avancée |
| `GET` | `/folders` | Arborescence dossiers |
| `POST` | `/folders` | Créer dossier |
| `POST` | `/files/{id}/permissions` | Gérer permissions |

### Alertes & Notifications (`/api/v1/alerts`, `/api/v1/notifications`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/alerts/` | Liste des alertes |
| `POST` | `/alerts/` | Créer une alerte |
| `GET` | `/notifications/` | Notifications utilisateur |
| `GET` | `/notifications/unread-count` | Compteur non lus |
| `PUT` | `/notifications/{id}/read` | Marquer comme lu |
| `POST` | `/notifications/mark-all-read` | Tout marquer lu |

### Dashboard & Analytics (`/api/v1/dashboard`, `/api/v1/analytics`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/dashboard/overview` | Vue d'ensemble |
| `GET` | `/dashboard/charts/production` | Graphiques production |
| `GET` | `/dashboard/charts/prices` | Graphiques prix |
| `GET` | `/dashboard/maps/production` | Carte production |
| `GET` | `/dashboard/export/{format}` | Export données |
| `GET` | `/analytics/reports/production` | Rapports production |
| `GET` | `/analytics/trends/prices` | Tendances prix |
| `GET` | `/analytics/compare` | Comparaison pays |

### Météo & Économie (`/api/v1/weather`, `/api/v1/economics`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/weather/current` | Météo actuelle |
| `GET` | `/weather/forecast` | Prévisions |
| `GET` | `/weather/history` | Historique météo |
| `GET` | `/economics/indicators` | Indicateurs économiques |
| `GET` | `/economics/gdp` | Données PIB |
| `GET` | `/economics/summary` | Résumé économique |

### Prédictions IA (`/api/v1/predictions`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/predict/yield` | Prédire rendement |
| `POST` | `/predict/price` | Prédire prix |
| `POST` | `/predict/weather` | Prédire météo |
| `GET` | `/history` | Historique prédictions |
| `POST` | `/batch` | Prédictions batch |

### Administration (`/api/v1/admin`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/users` | Liste utilisateurs (admin) |
| `PUT` | `/users/{id}` | Modifier utilisateur |
| `DELETE` | `/users/{id}` | Supprimer utilisateur |
| `POST` | `/users/{id}/activate` | Activer compte |
| `POST` | `/users/{id}/deactivate` | Désactiver compte |
| `GET` | `/stats` | Statistiques admin |

### Santé & Monitoring (`/api/v1/health`, `/metrics`)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check simple |
| `GET` | `/health/detailed` | Health check détaillé |
| `GET` | `/health/ready` | Readiness (Kubernetes) |
| `GET` | `/health/live` | Liveness (Kubernetes) |
| `GET` | `/metrics` | Métriques Prometheus |

---

## 🗄 Modèles de Données

### Acteurs Agricoles
**37 rôles** répartis en 4 sous-secteurs :

| Sous-secteur | Modèle | Champs clés |
|--------------|--------|-------------|
| **Végétal** | `ProducteurVegetal` | superficie, cultures, équipements, irrigation, coopérative |
| **Animal** | `EleveurAnimal` | cheptel (bovins/ovins/caprins/volailles/porcins), type élevage, vétérinaire |
| **Halieutique** | `PecheurHalieutique` | pirogues, filets, moteur, groupement, infrastructure portuaire |
| **Forestier** | `ExploitantForestier` | type exploitation, PFNL, titre foncier, certification durable |

### Indicateurs
- **60+ types** standardisés avec formules de calcul
- Valeurs : numérique, texte, booléen, JSON
- Seuils d'alerte configurables : `critique`, `alerte`, `optimal`

---

## 🐳 Déploiement

### Docker Compose

```yaml
# docker-compose.yml (extrait)
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - postgres
      - redis
      - mongodb
  
  postgres:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
  
  airflow:
    image: apache/airflow:2.8
    # Configuration DAGs ETL
```

### Kubernetes

```bash
# Health checks prêts pour K8s
kubectl apply -f k8s/
# Endpoints : /health/ready (readiness) et /health/live (liveness)
```

---

## 📈 Monitoring & Santé

| Outil | Endpoint | Usage |
|-------|----------|-------|
| **Prometheus** | `/metrics` | Métriques performances |
| **Sentry** | — | Traçage erreurs |
| **psutil** | `/health/detailed` | CPU, RAM, disque |
| **Health Checks** | `/health/*` | Kubernetes probes |

### Middleware Sécurité
- Headers HTTP sécurisés
- Rate limiting : **60 requêtes/minute**
- CORS configuré
- TrustedHost en production
- Logging structuré JSON + fichier

---

## 🔒 Sécurité

- ✅ JWT avec rotation refresh tokens
- ✅ Blacklist Redis des tokens révoqués
- ✅ Hashage bcrypt des mots de passe
- ✅ Validation MIME type + extension fichiers
- ✅ SQL injection protection (SQLAlchemy ORM)
- ✅ Rate limiting par IP
- ✅ Headers sécurisés (HSTS, CSP, X-Frame-Options)
- ✅ CORS strict
- ✅ Verrouillage compte brute-force

---

## 🗺 Cible Géographique

**Afrique de l'Ouest** — avec données spécifiques pour :
- 🇸🇳 Sénégal
- 🇹🇬 Togo
- 🇬🇭 Ghana
- 🇳🇬 Nigeria
- Et autres pays de la CEDEAO

---

## 📌 État du Projet

| Module | Statut |
|--------|--------|
| Authentification & Sécurité | ✅ Complet |
| Gestion Utilisateurs & RBAC | ✅ Complet |
| Chatbot IA | ✅ Complet |
| Communautés & Groupes | ✅ Complet |
| Gestion Fichiers | ✅ Complet |
| Alertes & Notifications | ✅ Complet |
| Acteurs & Indicateurs | ✅ Complet |
| Calculs & Agrégations | ✅ Complet |
| Pipeline ETL (Airflow) | ✅ Complet |
| Géolocalisation | ✅ Complet |
| Monitoring & Health | ✅ Complet |
| OAuth Google | ⚠️ Structure présente, non configuré |
| Push Notifications FCM | ⚠️ TODO |
| Extraction métadonnées vidéo/audio | ⚠️ TODO (ffmpeg/mutagen) |

---

## 🤝 Contribution

Les contributions sont les bienvenues ! Veuillez suivre les guidelines :

1. Fork le projet
2. Créer une branche (`git checkout -b feature/AmazingFeature`)
3. Commit (`git commit -m 'Add: AmazingFeature'`)
4. Push (`git push origin feature/AmazingFeature`)
5. Ouvrir une Pull Request

---

## 📄 Licence

Propriétaire — © 2026 AgriIntel. Tous droits réservés.

---

<p align="center">
  <strong>🌾 AgriIntel</strong> — Intelligence agricole pour l'Afrique<br>
  <em>Construit avec ❤️ pour les agriculteurs africains</em>
</p>

---
