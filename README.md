
<p align="center">
  <img src="https://img.shields.io/badge/AgriIntel360-API-16A34A?style=for-the-badge&logo=fastapi" alt="AgriIntel360 API" width="300">
</p>

<h1 align="center">⚙️ AgriIntel360 — Backend API</h1>

<p align="center">
  <strong>API REST Asynchrone — Intelligence Agricole pour l'Afrique</strong>
  <br>
  <em>FastAPI · PostgreSQL · Redis · MongoDB · Elasticsearch · IA/LLM</em>
</p>

<p align="center">
  <a href="https://fastapi.tiangolo.com/">
    <img src="https://img.shields.io/badge/FastAPI-0.136-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12">
  </a>
  <a href="https://www.postgresql.org/">
    <img src="https://img.shields.io/badge/PostgreSQL-15-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
  </a>
  <a href="https://redis.io/">
    <img src="https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis">
  </a>
  <a href="https://www.mongodb.com/">
    <img src="https://img.shields.io/badge/MongoDB-6-47A248?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB">
  </a>
  <a href="https://www.elastic.co/elasticsearch/">
    <img src="https://img.shields.io/badge/Elasticsearch-8-005571?style=for-the-badge&logo=elasticsearch&logoColor=white" alt="Elasticsearch">
  </a>
  <br>
  <a href="https://www.docker.com/">
    <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
  </a>
  <a href="https://docs.celeryq.dev/">
    <img src="https://img.shields.io/badge/Celery-5.4-37814A?style=for-the-badge&logo=celery&logoColor=white" alt="Celery">
  </a>
  <a href="https://alembic.sqlalchemy.org/">
    <img src="https://img.shields.io/badge/Alembic-1.13-2F2626?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="Alembic">
  </a>
  <a href="https://prometheus.io/">
    <img src="https://img.shields.io/badge/Prometheus-E6522C?style=for-the-badge&logo=prometheus&logoColor=white" alt="Prometheus">
  </a>
  <a href="https://sentry.io/">
    <img src="https://img.shields.io/badge/Sentry-362D59?style=for-the-badge&logo=sentry&logoColor=white" alt="Sentry">
  </a>
  <a href="https://pytorch.org/">
    <img src="https://img.shields.io/badge/PyTorch-2.2-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white" alt="PyTorch">
  </a>
  <a href="https://xgboost.readthedocs.io/">
    <img src="https://img.shields.io/badge/XGBoost-2.0-2C4F7C?style=for-the-badge&logo=xgboost&logoColor=white" alt="XGBoost">
  </a>
  <br>
  <a href="https://langchain.com/">
    <img src="https://img.shields.io/badge/LangChain-0.1-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangChain">
  </a>
  <a href="https://openai.com/">
    <img src="https://img.shields.io/badge/OpenAI-1.6-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI">
  </a>
  <a href="https://openrouter.ai/">
    <img src="https://img.shields.io/badge/OpenRouter-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenRouter">
  </a>
  <a href="https://www.selenium.dev/">
    <img src="https://img.shields.io/badge/selenium-43B02A?style=for-the-badge&logo=selenium&logoColor=white" alt="Selenium">
  </a>
</p>

<p align="center">
  <a href="#-architecture">Architecture</a> •
  <a href="#-stack-technique">Stack</a> •
  <a href="#-endpoints-api">API</a> •
  <a href="#-modèles-de-données">Modèles</a> •
  <a href="#-services">Services</a> •
  <a href="#-authentification">Auth</a> •
  <a href="#-installation">Installation</a> •
  <a href="#-d%C3%A9ploiement">Déploiement</a>
</p>

---

## ✨ Aperçu

**AgriIntel360 Backend** est une **API REST asynchrone** complète au service de l'intelligence agricole africaine. Elle couvre **4 sous-secteurs agricoles** (Végétal, Animal, Halieutique, Forestier) avec des fonctionnalités avancées :

### 🔥 20 modules API

| Module | Description |
|:---|:---|
| 🔐 **Auth** | JWT, OAuth Google/Microsoft, 2FA TOTP, API Keys, RBAC |
| 👤 **Users** | Profils, avatars, CRUD, statistiques |
| 💬 **Messaging** | Conversations privées, messages, sondages, upload, présence |
| 👥 **Community** | Groupes, posts, commentaires, réactions, invitations |
| 🔔 **Alerts** | Alertes météo, prix, ravageurs, sécheresse, inondation |
| 🔔 **Notifications** | Notifications in-app, email, SMS, push |
| 📊 **Dashboard** | Vue d'ensemble agrégée, KPIs, graphiques |
| 📈 **Analytics** | Analyses approfondies, tendances, comparaisons |
| 🌾 **Indicators** | 60+ indicateurs FAOSTAT/World Bank |
| 🔮 **Predictions** | ML (XGBoost, Prophet, PyTorch, scikit-learn) |
| 🤖 **Chatbot** | AgriBot IA (Kimi, DeepSeek, GPT-4, Claude) via LangChain |
| 📁 **Files** | Upload, stockage, permissions, organisation |
| 👥 **Actors** | Agriculteurs, éleveurs, pêcheurs, forestiers, coopératives |
| 🌤️ **Weather** | Météo actuelle, prévisions 7j, historique |
| 💰 **Economics** | PIB, inflation, emploi, export/import |
| 📍 **Geolocation** | Calcul distance, lieux proches |
| 🌍 **Reference** | Pays, cultures, données de référence |
| 🛡️ **Admin** | Administration utilisateurs, stats |
| ❤️ **Health** | Health checks (simple, détaillé, ready, live) |
| 🔌 **WebSocket** | Connexions temps réel, messagerie live |

### 🧠 Intelligence Artificielle

- **AgriBot** — Chatbot spécialisé agriculture africaine (multi-providers LLM)
- **Génération SQL sécurisée** — SELECT uniquement, pas de mutation
- **Prédictions ML** — XGBoost, LightGBM, Prophet, PyTorch
- **Recommandations** — Cultures, engrais, calendrier agricole
- **5 providers LLM** — Kimi, DeepSeek, GPT-4, Claude, Gemini

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTS                                        │
│      (Next.js App · Mobile · IoT Sensors · API Consumers)                   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ HTTPS / WebSocket
┌────────────────────────────────▼────────────────────────────────────────────┐
│                          FASTAPI APPLICATION                                │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        MIDDLEWARE STACK                               │   │
│  │  ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │   │
│  │  │ TrustedHost   │ │   CORS   │ │ Logging  │ │   RateLimit        │  │   │
│  │  │ (production)  │ │          │ │Middleware│ │   60 req/min       │  │   │
│  │  └──────────────┘ └──────────┘ └──────────┘ └────────────────────┘  │   │
│  │  ┌────────────────┐ ┌────────────────────┐ ┌──────────────────────┐ │   │
│  │  │ SecurityHeaders│ │  SessionMiddleware  │ │  Cache-Control      │ │   │
│  │  │ HSTS/CSP/XFO   │ │  (JWT secret)      │ │  no-store API       │ │   │
│  │  └────────────────┘ └────────────────────┘ └──────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        20 ROUTERS API v1                              │   │
│  │  /auth /users /messaging /community /alerts /notifications           │   │
│  │  /dashboard /analytics /indicators /predictions /chatbot             │   │
│  │  /files /actors /weather /economics /geolocation /reference          │   │
│  │  /admin /health /ws                                                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         SERVICES LAYER                                │   │
│  │  Auth · Messaging · Community · Chatbot · Email · Files              │   │
│  │  Indicators · Notifications · Redis · Session · Seed                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
     ┌───────────────────────────┼───────────────────────────┐
     │                           │                           │
┌────▼──────┐           ┌───────▼────────┐          ┌──────▼───────┐
│ PostgreSQL│           │     MongoDB    │          │    Redis     │
│ SQLAlchemy│           │   (Documents)  │          │ Cache/Session│
│  Async    │           │   (optionnel)  │          │  JWT Blacklist│
└───────────┘           └────────────────┘          └──────────────┘
     │
┌────▼────────┐    ┌────────────┐    ┌────────────────┐
│Elasticsearch│    │   Twilio   │    │   Prometheus   │
│  (Search)   │    │   (SMS)    │    │   + Sentry     │
└─────────────┘    └────────────┘    └────────────────┘
```

---

## 🛠 Stack Technique

### Core

| Technologie | Version | Usage |
|:---|---:|:---|
| **Python** | 3.12 | Langage principal |
| **FastAPI** | 0.136.3 | Framework HTTP asynchrone |
| **Uvicorn** | 0.27.1 | Serveur ASGI |
| **Starlette** | ≥0.36.3 | Base ASGI |

### Base de données

| Technologie | Version | Usage |
|:---|---:|:---|
| **PostgreSQL** | 15+ | Données relationnelles (primaire) |
| **SQLAlchemy** | 2.0.27 | ORM asynchrone |
| **Alembic** | 1.13.1 | Migrations de schéma |
| **asyncpg** | 0.29.0 | Driver PostgreSQL asynchrone |
| **MongoDB** | 6+ | Données documentaires (optionnel) |
| **Motor** | 3.3.2 | Driver MongoDB asynchrone |
| **Redis** | 7+ | Cache, sessions, blacklist JWT |
| **Elasticsearch** | 8+ | Recherche full-text (optionnel) |

### Authentification & Sécurité

| Technologie | Usage |
|:---|:---|
| **python-jose** | JWT (HS256) — access 24h / refresh 7j |
| **bcrypt** | Hashage mots de passe (12 rounds) |
| **Authlib** | OAuth Google & Microsoft |
| **pyotp** | 2FA TOTP |
| **fastapi-csrf-protect** | Protection CSRF |
| **Rate limiting** | 60 req/min (middleware custom) |
| **Security headers** | HSTS, CSP, X-Frame-Options (middleware) |

### Intelligence Artificielle & ML

| Technologie | Usage |
|:---|:---|
| **LangChain** | 0.1.0 — Orchestration LLM |
| **OpenAI** | GPT-4/GPT-4o |
| **OpenRouter** | Kimi (Moonshot), DeepSeek |
| **XGBoost** | 2.0.2 — Prédictions rendement |
| **LightGBM** | 4.1.0 — Prédictions prix |
| **Prophet** | 1.1.5 — Prédictions séries temporelles |
| **PyTorch** | 2.2.0 — Deep learning agricole |
| **scikit-learn** | 1.3.2 — ML classique |
| **Transformers** | 4.38.0 — NLP agricole |
| **Sentence-Transformers** | 2.2.2 — Embeddings |
| **spaCy** | 3.7.2 — NLP français |

### Géospatial

| Technologie | Usage |
|:---|:---|
| **GeoPandas** | Données géospatiales |
| **Shapely** | Opérations géométriques |
| **PyProj** | Projections cartographiques |
| **Folium** | Cartes Leaflet |
| **GeoPy** | Géocodage |

### Notifications

| Technologie | Usage |
|:---|:---|
| **FastAPI-Mail** | Emails transactionnels (HTML) |
| **Twilio** | SMS (alertes mobiles) |
| **SendGrid** | Email alternatif |
| **WebSocket** | Notifications temps réel |

### Monitoring

| Technologie | Usage |
|:---|:---|
| **Prometheus** | Métriques API |
| **Sentry** | Traçage d'erreurs |
| **Loguru** | Logging structuré |
| **psutil** | Métriques système (CPU, RAM, disque) |

### DevOps

| Technologie | Usage |
|:---|:---|
| **Docker** | Conteneurisation |
| **Celery** | 5.3.4 — Tâches asynchrones |
| **Flower** | 2.0.1 — Monitoring Celery |
| **MLflow** | 2.9.2 — Tracking experiments ML |
| **Alembic** | Migrations DB automatiques au démarrage |

---

## 🔗 Endpoints API

Base : **`/api/v1`** — Live : `https://agriintel360.lsgrouptogo.com/api/v1`

### 🔐 Authentification (`/auth`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `POST` | `/auth/register` | Inscription avec vérification email |
| `POST` | `/auth/login` | Connexion JWT (access + refresh) |
| `POST` | `/auth/logout` | Déconnexion + blacklist token Redis |
| `POST` | `/auth/refresh` | Rafraîchissement access token |
| `GET` | `/auth/me` | Profil utilisateur courant |
| `POST` | `/auth/change-password` | Changement mot de passe |
| `POST` | `/auth/reset-password` | Réinitialisation par email |
| `POST` | `/auth/verify-email` | Vérification email par token |
| `POST` | `/auth/2fa/setup` | Configuration 2FA TOTP (QR code) |
| `POST` | `/auth/2fa/verify` | Vérification code 2FA |
| `POST` | `/auth/2fa/disable` | Désactivation 2FA |
| `POST` | `/auth/api-keys` | Création clé API |
| `GET` | `/auth/api-keys` | Liste des clés API |
| `DELETE` | `/auth/api-keys/{id}` | Révocation clé API |
| `POST` | `/auth/oauth/{provider}` | URL d'authentification OAuth |
| `GET` | `/auth/oauth/{provider}/callback` | Callback OAuth |

### 👤 Utilisateurs (`/users`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/users/` | Liste des utilisateurs |
| `GET` | `/users/{id}` | Profil utilisateur |
| `PUT` | `/users/{id}` | Mise à jour profil |
| `DELETE` | `/users/{id}` | Suppression compte |
| `POST` | `/users/{id}/avatar` | Upload avatar |
| `GET` | `/users/stats/overview` | Statistiques utilisateurs |

### 💬 Messagerie (`/messaging`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/messaging/conversations` | Liste conversations |
| `POST` | `/messaging/conversations` | Créer conversation |
| `GET` | `/messaging/conversations/{id}` | Détail conversation |
| `PUT` | `/messaging/conversations/{id}` | Modifier conversation |
| `DELETE` | `/messaging/conversations/{id}` | Supprimer conversation |
| `GET` | `/messaging/conversations/{id}/messages` | Messages d'une conversation |
| `POST` | `/messaging/conversations/{id}/messages` | Envoyer message |
| `GET` | `/messaging/conversations/{id}/messages/unread/count` | Compteur messages non lus |
| `PUT` | `/messaging/conversations/{id}/messages/{msg}/read` | Marquer message lu |
| `POST` | `/messaging/conversations/{id}/messages/{msg}/vote` | Voter dans un sondage |
| `POST` | `/messaging/conversations/{id}/upload` | Upload fichier dans conversation |
| `PUT` | `/messaging/conversations/{id}/typing` | Indicateur de saisie |
| `POST` | `/messaging/conversations/{id}/leave` | Quitter conversation |
| `POST` | `/messaging/conversations/{id}/members` | Ajouter membres |
| `DELETE` | `/messaging/conversations/{id}/members/{uid}` | Retirer membre |
| `GET` | `/messaging/search-users` | Rechercher utilisateurs |

### 👥 Communautés (`/community`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `POST` | `/community/groups` | Créer un groupe |
| `GET` | `/community/groups` | Rechercher des groupes |
| `GET` | `/community/groups/{id}` | Détails groupe |
| `PUT` | `/community/groups/{id}` | Modifier groupe |
| `DELETE` | `/community/groups/{id}` | Supprimer groupe |
| `POST` | `/community/groups/{id}/join` | Rejoindre un groupe |
| `POST` | `/community/groups/{id}/leave` | Quitter un groupe |
| `GET` | `/community/groups/{id}/members` | Membres du groupe |
| `PUT` | `/community/groups/{id}/members/{uid}` | Modérer membre |
| `POST` | `/community/posts` | Créer une publication |
| `GET` | `/community/groups/{id}/posts` | Publications du groupe |
| `PUT` | `/community/posts/{id}` | Modifier publication |
| `DELETE` | `/community/posts/{id}` | Supprimer publication |
| `POST` | `/community/posts/{id}/reactions` | Ajouter une réaction |
| `POST` | `/community/comments` | Ajouter un commentaire |
| `GET` | `/community/posts/{id}/comments` | Commentaires d'un post |
| `DELETE` | `/community/comments/{id}` | Supprimer commentaire |

### 📁 Fichiers (`/files`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `POST` | `/files/upload` | Upload fichier unique |
| `POST` | `/files/upload-multiple` | Upload multiple |
| `GET` | `/files/{id}` | Détails fichier |
| `PUT` | `/files/{id}` | Modifier fichier |
| `DELETE` | `/files/{id}` | Supprimer fichier |
| `GET` | `/files/` | Recherche avancée fichiers |
| `GET` | `/files/folders` | Arborescence dossiers |
| `POST` | `/files/folders` | Créer dossier |
| `POST` | `/files/{id}/permissions` | Gérer permissions |

### 🔔 Alertes (`/alerts`) & Notifications (`/notifications`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/alerts/` | Liste des alertes |
| `POST` | `/alerts/` | Créer une alerte |
| `GET` | `/alerts/{id}` | Détail alerte |
| `PUT` | `/alerts/{id}` | Modifier alerte |
| `DELETE` | `/alerts/{id}` | Supprimer alerte |
| `GET` | `/notifications/` | Notifications utilisateur |
| `GET` | `/notifications/unread-count` | Compteur non lus |
| `PUT` | `/notifications/{id}/read` | Marquer comme lu |
| `POST` | `/notifications/mark-all-read` | Tout marquer lu |

### 📊 Dashboard (`/dashboard`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/dashboard/overview` | Vue d'ensemble (KPIs, tendances) |
| `GET` | `/dashboard/charts/production` | Graphiques production |
| `GET` | `/dashboard/charts/prices` | Graphiques prix marchés |
| `GET` | `/dashboard/maps/production` | Carte de production |
| `GET` | `/dashboard/export/{format}` | Export données (CSV/Excel/PDF) |

### 📈 Analytics (`/analytics`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/analytics/reports/production` | Rapports production agricole |
| `GET` | `/analytics/trends/prices` | Tendances des prix |
| `GET` | `/analytics/compare` | Comparaison entre pays |

### 🌾 Indicateurs (`/indicators`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/indicators/` | Liste des indicateurs |
| `GET` | `/indicators/types` | Types d'indicateurs |
| `GET` | `/indicators/{id}` | Détail indicateur |
| `GET` | `/indicators/{id}/data` | Données d'un indicateur |
| `POST` | `/indicators/sync` | Synchronisation FAOSTAT/World Bank |

### 🤖 Chatbot (`/chatbot`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `POST` | `/chatbot/chat` | Conversation avec AgriBot |
| `GET` | `/chatbot/suggestions` | Questions suggérées |
| `GET` | `/chatbot/history` | Historique conversations |
| `POST` | `/chatbot/clear-history` | Effacer historique |
| `POST` | `/chatbot/switch-provider` | Changer provider LLM |
| `GET` | `/chatbot/status` | Statut du chatbot |
| `POST` | `/chatbot/feedback` | Feedback utilisateur |

### 🔮 Prédictions (`/predictions`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `POST` | `/predictions/yield` | Prédire rendement agricole |
| `POST` | `/predictions/price` | Prédire prix marchés |
| `POST` | `/predictions/weather` | Prédire météo |
| `GET` | `/predictions/history` | Historique prédictions |
| `POST` | `/predictions/batch` | Prédictions par lot |

### 🌤️ Météo (`/weather`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/weather/current` | Météo actuelle |
| `GET` | `/weather/forecast` | Prévisions 7 jours |
| `GET` | `/weather/history` | Historique météo |

### 💰 Économie (`/economics`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/economics/indicators` | Indicateurs économiques |
| `GET` | `/economics/gdp` | Données PIB |
| `GET` | `/economics/summary` | Résumé économique |

### 👥 Acteurs (`/actors`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/actors/` | Liste des acteurs agricoles |
| `POST` | `/actors/` | Créer un acteur |
| `GET` | `/actors/{id}` | Profil acteur |
| `PUT` | `/actors/{id}` | Modifier acteur |
| `DELETE` | `/actors/{id}` | Supprimer acteur |

### 📍 Géolocalisation (`/geolocation`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `POST` | `/geolocation/distance` | Calcul distance (lat/lon) |
| `POST` | `/geolocation/nearby` | Recherche lieux proches |

### 🌍 Référence (`/reference`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/reference/countries` | Liste des pays |
| `GET` | `/reference/countries/{code}` | Détail pays |
| `GET` | `/reference/crops` | Liste des cultures |
| `GET` | `/reference/crops/{id}` | Détail culture |

### 🛡️ Administration (`/admin`) — *Requiert rôle admin*

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/admin/users` | Liste tous les utilisateurs |
| `PUT` | `/admin/users/{id}` | Modifier utilisateur |
| `DELETE` | `/admin/users/{id}` | Supprimer utilisateur |
| `POST` | `/admin/users/{id}/activate` | Activer compte |
| `POST` | `/admin/users/{id}/deactivate` | Désactiver compte |
| `GET` | `/admin/stats` | Statistiques plateforme |

### ❤️ Health (`/health`)

| Méthode | Endpoint | Description |
|:---|:---|---:|
| `GET` | `/health` | Health check simple |
| `GET` | `/health/detailed` | Health check détaillé (DB + système) |
| `GET` | `/health/ready` | Readiness probe (Kubernetes) |
| `GET` | `/health/live` | Liveness probe (Kubernetes) |

### 🔌 WebSocket (`/ws`)

| Connexion | Description |
|:---|:---|
| `ws://.../api/v1/ws` | Connexion WebSocket pour messagerie temps réel |

---

## 📁 Structure du projet

```
backend/
├── src/                              # Code source principal
│   ├── main.py                       # Point d'entrée FastAPI, lifespan, middleware
│   └── services/                     # Services métier
│       ├── auth.py                   # JWT, OAuth, 2FA, API keys
│       ├── messaging.py              # Messagerie privée
│       ├── community.py              # Groupes, posts, commentaires
│       ├── chatbot.py                # AgriBot IA (LangChain)
│       ├── email.py                  # Envoi d'emails (FastAPI-Mail)
│       ├── files.py                  # Upload et gestion fichiers
│       ├── notifications.py          # Notifications dispatch
│       ├── indicators_fetch.py       # Fetch FAOSTAT/World Bank
│       ├── redis.py                  # Client Redis
│       ├── session.py                # Gestion sessions
│       ├── admin_seed.py             # Seed compte admin
│       └── seed_data.py              # Données de démonstration
│   └── middleware/                   # Middleware FastAPI
│       ├── security.py               # SecurityHeaders + RateLimit
│       ├── logging.py                # Logging structuré
│       └── monitoring.py             # Métriques Prometheus
│   └── tasks/                        # Tâches asynchrones
│       ├── celery_app.py             # Configuration Celery
│       └── indicator_sync.py         # Sync périodique indicateurs (asyncio)
│
├── api/                              # API Layer
│   ├── routers/                      # Routeurs FastAPI
│   │   ├── router.py                 # Route principal (monte tous les routers)
│   │   ├── auth.py / users.py        # Auth & Users
│   │   ├── messaging.py              # Messagerie
│   │   ├── community.py              # Communautés
│   │   ├── alerts.py / notifications.py  # Alertes & Notifications
│   │   ├── dashboard.py / analytics.py   # Dashboard & Analytics
│   │   ├── indicators.py             # Indicateurs
│   │   ├── predictions.py            # Prédictions ML
│   │   ├── chatbot.py                # Chatbot IA
│   │   ├── files.py                  # Fichiers
│   │   ├── actors.py                 # Acteurs agricoles
│   │   ├── weather.py / economics.py # Météo & Économie
│   │   ├── geolocation.py            # Géolocalisation
│   │   ├── countries.py              # Référentiel pays/cultures
│   │   ├── admin.py                  # Administration
│   │   ├── health.py                 # Health checks
│   │   ├── websocket.py              # WebSocket
│   │   └── mocks.py                  # Données mock pour tests
│   ├── models/                       # Modèles SQLAlchemy
│   │   └── sql/
│   │       ├── base.py               # Base déclarative
│   │       ├── user.py               # User, RefreshToken, TwoFactorCode
│   │       ├── agricultural.py       # Alert, Country, Crop, Indicator, MarketPrice
│   │       ├── community.py          # Group, GroupMember, Post, Comment
│   │       ├── messaging.py          # Conversation, ConversationParticipant, PrivateMessage
│   │       ├── actors.py             # Actor (37 rôles agricoles)
│   │       ├── files.py              # UploadedFile
│   │       ├── indicators.py         # IndicatorData
│   │       └── api_keys.py           # ApiKey
│   └── schemas/                      # Schémas Pydantic (validation requête/réponse)
│       ├── auth.py                   # Auth schemas
│       ├── alert.py                  # Alert schemas
│       ├── actors.py                 # Actor schemas
│       ├── community.py              # Community schemas
│       ├── dashboard.py              # Dashboard schemas
│       ├── files.py                  # File schemas
│       └── indicators.py             # Indicator schemas
│
├── config/                           # Configuration
│   ├── config.py                     # Settings (pydantic-settings)
│   ├── database.py                   # Connexions DB (async engine, session makers)
│   └── logging.py                    # Configuration logging
│
├── migrations/                       # Migrations Alembic (6 versions)
│   └── versions/
│       ├── 001_initial.py            # Tables initiales
│       ├── 002_community_files.py    # Community & files
│       ├── 003_add_user_columns.py   # Colonnes utilisateur
│       ├── 004_add_registration_fields.py  # Champs inscription
│       ├── 005_add_2fa_and_api_keys.py     # 2FA & API keys
│       └── 006_add_sector_and_messages.py  # Secteurs & messages
│
├── db/                               # Scripts base de données
├── pipeline/                         # Pipeline données
├── docker-compose.yml                # Stack Docker complète
├── Dockerfile                        # Image Docker API
├── mlflow.Dockerfile                 # Image Docker MLflow
├── requirements.txt                  # Dépendances Python (122 lignes)
├── requirements-base.txt             # Dépendances de base
├── requirements-dev.txt              # Dépendances développement
├── alembic.ini                       # Configuration Alembic
└── passenger_wsgi.py                 # Entrypoint Passenger (Apache)
```

---

## 🗄 Modèles de Données

### Tables PostgreSQL

| Table | Modèle | Champs clés |
|:---|---:|:---|
| `users` | `User` | id UUID, full_name, username, email, password_hash, role, avatar_url, last_login, is_active, is_verified, cover_url, phone, location, bio |
| `refresh_tokens` | `RefreshToken` | id, token_hash, user_id, expires_at, revoked |
| `two_factor_codes` | `TwoFactorCode` | id, user_id, secret, is_enabled, backup_codes |
| `api_keys` | `ApiKey` | id, user_id, key_hash, name, permissions, last_used_at |
| `conversations` | `Conversation` | id UUID, title, is_group, created_by, updated_at |
| `conversation_participants` | `ConversationParticipant` | conversation_id, user_id, last_read_at, is_active, role |
| `private_messages` | `PrivateMessage` | id UUID, conversation_id, sender_id, content, message_type (text/voice/file/poll), poll_data JSONB, audio_url, file_url, duration |
| `groups` | `Group` | id UUID, name, description, type (varchar), sector, cover_url, is_private |
| `group_members` | `GroupMember` | group_id, user_id, role, joined_at |
| `posts` | `Post` | id UUID, group_id, author_id, content, media_urls, post_type |
| `comments` | `Comment` | id UUID, post_id, author_id, content, parent_id |
| `alerts` | `Alert` | id UUID, title, message, alert_type, severity, is_read, user_id, action_url, status, is_active |
| `actors` | `Actor` | id UUID, full_name, actor_type, sector, location, contact, certifications |
| `countries` | `Country` | id, code, name, region, coordinates |
| `crops` | `Crop` | id, name, category, season, countries |
| `indicators` | `Indicator` | id, name, type, unit, category, description |
| `indicator_data` | `IndicatorData` | id, indicator_id, country_id, value, date, source |
| `market_prices` | `MarketPrice` | id, crop_id, country_id, price, currency, market, date |
| `uploaded_files` | `UploadedFile` | id UUID, filename, original_name, mime_type, size, path, folder_id, uploaded_by, permissions |

### Types d'Acteurs Agricoles (37 rôles)

| Sous-secteur | Rôles |
|:---|:---|
| 🌱 **Végétal** | Producteur, Agriculteur, Maraîcher, Arboriculteur, Céréalier, Pépiniériste, Horticulteur, Riziculteur, Cotonculteur |
| 🐄 **Animal** | Éleveur bovin, Éleveur ovin, Éleveur caprin, Aviculteur, Porcinculteur, Apiculteur, Éleveur camelin |
| 🎣 **Halieutique** | Pêcheur artisanal, Pêcheur semi-industriel, Aquaculteur, Mareyeur, Transformateur produits halieutiques |
| 🌲 **Forestier** | Exploitant forestier, Sylviculteur, Producteur PFNL, Pépiniériste forestier, Certificateur |
| 🤝 **Institutionnel** | Coopérative, ONG, Gouvernement, Institution recherche, Bureau d'études |
| 💼 **Marché** | Acheteur, Fournisseur, Transformateur, Exportateur, Transporteur, Courtier |

---

## 🔐 Authentification & Sécurité

### JWT Flow

```
┌────────┐    POST /auth/login     ┌──────────┐
│ Client │────────────────────────▶│  API      │
│        │◀────────────────────────│          │
└────────┘   {access_token,         └──────────┘
             refresh_token, user}
```

| Paramètre | Valeur |
|:---|---:|
| Algorithme | **HS256** |
| Access Token | **24h** (1440 min) |
| Refresh Token | **7 jours** |
| Bcrypt rounds | **12** |
| Rate limit | **60 req/min** |

### Modes d'authentification

1. **JWT standard** — Login/password → access + refresh tokens
2. **OAuth 2.0** — Google & Microsoft (Authlib)
3. **2FA TOTP** — Double facteur (Google Authenticator, Authy)
4. **API Keys** — Accès programmatique (création, liste, révocation)

### RBAC — Rôles & Permissions

| Rôle | Accès |
|:---|:---|
| `super_admin` | Tout accès sans restriction |
| `admin` | Administration complète, gestion utilisateurs |
| `analyst` | Données, analytics, indicateurs |
| `user` | Fonctionnalités standard |
| `guest` | Accès public restreint |

### Middleware de sécurité

```
Ordre d'exécution (outer → inner) :
1. TrustedHostMiddleware    — Hôtes autorisés (production)
2. CORSMiddleware           — Origines autorisées
3. LoggingMiddleware        — Requête/réponse loggées
4. RateLimitMiddleware      — 60 req/min par IP
5. SecurityHeadersMiddleware — HSTS, CSP, X-Frame-Options
6. SessionMiddleware        — Sessions signées (JWT secret)

Cache-Control: no-store sur toutes les routes /api/ (Varnish CDN)
```

---

## 🚀 Installation

### Option 1 : Docker Compose (recommandé)

```bash
# Cloner et configurer
cp .env.example .env
# Éditer .env avec vos credentials

# Lancer toute la stack
docker-compose up -d --build

# Vérifier
docker-compose ps
```

### Option 2 : Installation manuelle

```bash
# Python 3.12 requis
python -m venv .venv
source .venv/bin/activate

# Dépendances
pip install -r requirements.txt

# Configuration
cp .env.example .env
# Éditer DATABASE_URL, JWT_SECRET_KEY, etc.

# Base de données
alembic upgrade head

# Lancer le serveur
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Configuration `.env`

```env
# === Application ===
PROJECT_NAME=AgriIntel360
VERSION=1.0.0
ENVIRONMENT=development
DEBUG=true

# === Base de données ===
DATABASE_URL=postgresql://user:pass@127.0.0.1:5432/agriintel360
REDIS_URL=redis://127.0.0.1:6379
MONGODB_URL=mongodb://user:pass@localhost:27017/agriintel360
ELASTICSEARCH_URL=http://localhost:9200

# === JWT ===
JWT_SECRET_KEY=votre_cle_secrete_64_caracteres_hex
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# === Admin par défaut ===
DEFAULT_ADMIN_EMAIL=admin@agri.com
DEFAULT_ADMIN_PASSWORD=CHANGE_ME
DEFAULT_ADMIN_USERNAME=admin

# === OAuth ===
GOOGLE_CLIENT_ID=votre_client_id
GOOGLE_CLIENT_SECRET=votre_secret
MICROSOFT_CLIENT_ID=votre_client_id
MICROSOFT_CLIENT_SECRET=votre_secret

# === LLM / OpenRouter ===
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENAI_API_KEY=sk-xxxxx
DEFAULT_LLM_PROVIDER=kimi

# === Monitoring ===
SENTRY_DSN=https://xxxxx@xxxx.ingest.sentry.io/xxxxx
LOG_LEVEL=INFO

# === Email (FastAPI-Mail) ===
MAIL_USERNAME=noreply@agriintel360.com
MAIL_PASSWORD=votre_password
MAIL_FROM=noreply@agriintel360.com
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
```

---

## 🐳 Déploiement

### Production (LWS)

```bash
# Redémarrer l'API
pkill -9 -f 'uvicorn.*src.main'
cd /home/user/public_html/agriintel360/api
HOME=/home/user ENVIRONMENT=production nohup /usr/bin/python3 \
  -m uvicorn src.main:app --host 127.0.0.1 --port 8001 --workers 1 \
  --timeout-keep-alive 30 --log-level warning \
  >> logs/backend.log 2>&1 &
```

### Health Checks (Kubernetes-ready)

| Endpoint | Type | Description |
|:---|:---|:---|
| `GET /health` | Simple | `{"status": "healthy"}` |
| `GET /health/detailed` | Complet | Status DB, système, version |
| `GET /health/ready` | Readiness | OK si PostgreSQL accessible |
| `GET /health/live` | Liveness | `{"status": "alive"}` |
| `GET /metrics` | Prometheus | Métriques (admin only) |

### Migrations automatiques

Au démarrage, l'application exécute automatiquement :
1. `alembic upgrade head` — Migrations pendantes
2. `Base.metadata.create_all` — Création tables manquantes
3. `_add_missing_columns()` — Ajout colonnes manquantes
4. `ensure_default_admin_user()` — Seed compte admin

---

## 📈 Monitoring

| Outil | Endpoint | Usage |
|:---|:---|:---|
| **Prometheus** | `GET /metrics` | Métriques API (requêtes, latence, erreurs) |
| **Sentry** | SDK intégré | Traçage d'erreurs en production |
| **Loguru** | Fichier + stdout | Logging structuré JSON |
| **psutil** | `GET /health/detailed` | CPU, RAM, disque |
| **Health checks** | `GET /health/*` | Probes Kubernetes |

---

## 📊 Pipeline ETL & Background Tasks

### Synchronisation périodique (asyncio)

| Tâche | Intervalle | Source | Destination |
|:---|:---:|:---|:---|
| **FAOSTAT** | 24h | fao.org | `indicator_data` |
| **World Bank** | 24h | worldbank.org | `indicator_data` |
| **OpenWeatherMap** | 6h | openweathermap.org | Cache Redis + API |

### Celery Tasks

```python
# backend/src/tasks/celery_app.py
- sync_faostat_data()     # Tâche périodique FAOSTAT
- sync_world_bank_data()  # Tâche périodique World Bank
- calculate_indicators()  # Calculs d'indicateurs aggrégés
- clean_expired_tokens()  # Nettoyage tokens expirés
- send_scheduled_alerts() # Envoi d'alertes programmées
```

---

## 🧪 Tests & Documentation

```bash
# Lancer les tests
pytest tests/ -v

# Documentation API (dev)
# Swagger UI : http://localhost:8000/api/v1/docs
# ReDoc     : http://localhost:8000/api/v1/redoc
# OpenAPI   : http://localhost:8000/api/v1/openapi.json
```

---

## 🔒 Sécurité — Bonnes pratiques

- ✅ **JWT** avec rotation des refresh tokens
- ✅ **Blacklist Redis** des tokens révoqués
- ✅ **bcrypt** (12 rounds) pour les mots de passe
- ✅ **Validation MIME** type + extension fichiers
- ✅ **SQL injection** protégée par SQLAlchemy ORM
- ✅ **Rate limiting** 60 requêtes/minute par IP
- ✅ **Headers sécurisés** HSTS, CSP, X-Frame-Options
- ✅ **CORS** origines strictes
- ✅ **Verrouillage de compte** après 5 tentatives échouées (30 min)
- ✅ **Cache-Control: no-store** sur toutes les routes API (Varnish CDN)
- ⚠️ **Ne jamais utiliser `localhost`** pour PostgreSQL/Redis (IPv6 refusé) → `127.0.0.1`
- ⚠️ **JWT secret** obligatoirement personnalisé en production

### Bugs connus & fixes

| Problème | Solution |
|:---|:---|
| Routes paramétrées avant routes statiques | Toujours déclarer `/unread/count` avant `/{id}` |
| UUID PostgreSQL | Toujours utiliser `_to_uuid()` avant comparaison |
| Timezone | `datetime.now(timezone.utc)` jamais `utcnow()` |
| JSONB mutation SQLAlchemy | `copy.deepcopy()` + `flag_modified()` |
| Redis `localhost` | Forcer `127.0.0.1` (IPv6) |
| `Group.type` enum | `SAEnum(native_enum=False)` — colonne varchar |
| Pydantic extra fields | `extra='ignore'` (pas `forbid`) |

---

## 🗺️ Couverture Géographique

### Afrique de l'Ouest (priorité)

| Pays | Code | Région |
|:---|---:|:---|
| 🇸🇳 Sénégal | SN | UEMOA |
| 🇹🇬 Togo | TG | UEMOA |
| 🇬🇭 Ghana | GH | CEDEAO |
| 🇳🇬 Nigeria | NG | CEDEAO |
| 🇨🇮 Côte d'Ivoire | CI | UEMOA |
| 🇧🇫 Burkina Faso | BF | UEMOA |
| 🇲🇱 Mali | ML | UEMOA |
| 🇧🇯 Bénin | BJ | UEMOA |
| 🇳🇪 Niger | NE | CEDEAO |
| 🇬🇳 Guinée | GN | CEDEAO |

---

## 📦 Dépendances (122 paquets)

### Core (FastAPI)
`fastapi==0.136.3` · `uvicorn==0.27.1` · `starlette>=0.36.3` · `pydantic==2.13.4`

### Base de données
`asyncpg==0.29.0` · `sqlalchemy==2.0.27` · `alembic==1.13.1` · `motor==3.3.2` · `redis==5.0.1`

### ML & IA
`torch==2.2.0` · `xgboost==2.0.2` · `lightgbm==4.1.0` · `prophet==1.1.5` · `scikit-learn==1.3.2` · `transformers==4.38.0`
`langchain==0.1.0` · `openai==1.6.1` · `sentence-transformers==2.2.2` · `spacy==3.7.2`

### Geospatial
`geopandas==0.14.1` · `shapely==2.0.2` · `pyproj==3.6.1` · `folium==0.15.1`

### Notifications
`fastapi-mail==1.4.1` · `twilio==8.10.3` · `sendgrid==6.11.0`

### Monitoring
`loguru==0.7.2` · `prometheus-client==0.19.0` · `sentry-sdk==1.39.1` · `psutil==5.9.5`

---

## 📋 État du projet

| Module | Statut |
|:---|---:|
| 🔐 Authentification & Sécurité | ✅ Complet |
| 👤 Gestion Utilisateurs & RBAC | ✅ Complet |
| 💬 Messagerie privée | ✅ Complet |
| 👥 Communautés & Groupes | ✅ Complet |
| 🔔 Alertes & Notifications | ✅ Complet |
| 📊 Dashboard & Analytics | ✅ Complet |
| 🌾 Indicateurs Agricoles | ✅ Complet |
| 🤖 Chatbot IA (AgriBot) | ✅ Complet |
| 🔮 Prédictions ML | ✅ Complet |
| 📁 Gestion Fichiers | ✅ Complet |
| 🌤️ Météo & Économie | ✅ Complet |
| 📍 Géolocalisation | ✅ Complet |
| 👤 Acteurs Agricoles | ✅ Complet |
| 🛡️ Administration | ✅ Complet |
| ❤️ Health Checks & Monitoring | ✅ Complet |
| 🔌 WebSocket Temps Réel | ✅ Complet |
| 🐳 Docker & Celery | ✅ Complet |
| 🔄 OAuth Google/Microsoft | ⚠️ Implémenté, à configurer |
| 📱 Push Notifications FCM | ⚠️ TODO |

---

<p align="center">
  <strong>⚙️ AgriIntel360 Backend</strong><br>
  <em>API REST Intelligente pour l'Agriculture Africaine</em><br>
  <br>
  <a href="https://agriintel360.lsgrouptogo.com">🌐 Site Live</a> •
  <a href="https://agriintel360.lsgrouptogo.com/api/v1/docs">📚 API Docs</a> •
  <a href="mailto:contact@agriintel360.lsgrouptogo.com">📧 Contact</a>
  <br><br>
  <strong>Construit avec ❤️ pour les agriculteurs africains</strong>
</p>
