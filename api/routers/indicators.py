"""
API Router pour les indicateurs agricoles — enrichi avec données mock et gestion d'images
"""

from typing import Optional
from datetime import datetime, date, timedelta
import random
import math

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User

router = APIRouter()

CURRENT_MODEL = "agri_indicators_v2"
MODEL_SUPPORTS_IMAGES = False


def _generate_history(days: int, base: float, variance: float):
    now = datetime.utcnow()
    return [
        {
            "date": (now - timedelta(days=days - i)).strftime("%Y-%m-%d"),
            "value": round(base + math.sin(i * 0.4) * variance + random.uniform(-variance * 0.3, variance * 0.3), 2),
        }
        for i in range(days)
    ]


# ─── Overview ─────────────────────────────────────────────────────────────────

@router.get("/overview")
async def get_indicators_overview(
    current_user: User = Depends(get_current_verified_user),
):
    """Vue d'ensemble des indicateurs"""
    return {
        "total_indicators": 48,
        "categories": 15,
        "countries": 14,
        "with_alerts": 7,
        "avg_health": 0.78,
        "recent_updates": 23,
        "by_sector": [
            {"sector": "Végétal", "count": 18, "color": "#16A34A"},
            {"sector": "Animal", "count": 12, "color": "#D97706"},
            {"sector": "Halieutique", "count": 8, "color": "#0891B2"},
            {"sector": "Forestier", "count": 6, "color": "#92400E"},
            {"sector": "Économique", "count": 4, "color": "#4F46E5"},
        ],
        "health_distribution": [
            {"status": "Optimal", "count": 22, "color": "#22C55E"},
            {"status": "Alerte", "count": 14, "color": "#EAB308"},
            {"status": "Critique", "count": 7, "color": "#DC2626"},
            {"status": "Inconnu", "count": 5, "color": "#6B7280"},
        ],
    }


# ─── List / Search ────────────────────────────────────────────────────────────

@router.get("/")
async def list_indicators(
    sector: Optional[str] = None,
    category: Optional[str] = None,
    country: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_verified_user),
):
    """Liste enrichie des indicateurs agricoles"""
    indicators = []
    base_indicators = [
        {"name": "Rendement Maïs", "category": "rendement", "sector": "vegetal", "unit": "t/ha", "base": 4.5},
        {"name": "Rendement Riz", "category": "rendement", "sector": "vegetal", "unit": "t/ha", "base": 3.2},
        {"name": "Prix Maïs", "category": "prix", "sector": "vegetal", "unit": "FCFA/kg", "base": 350},
        {"name": "Prix Riz", "category": "prix", "sector": "vegetal", "unit": "FCFA/kg", "base": 650},
        {"name": "Production céréalière", "category": "production", "sector": "vegetal", "unit": "tonnes", "base": 2450000},
        {"name": "Production animale", "category": "production", "sector": "animal", "unit": "tonnes", "base": 520000},
        {"name": "Captures halieutiques", "category": "production", "sector": "halieutique", "unit": "tonnes", "base": 480000},
        {"name": "Produits forestiers", "category": "production", "sector": "forestier", "unit": "m³", "base": 125000},
        {"name": "PIB agricole", "category": "marché", "sector": "vegetal", "unit": "Mds FCFA", "base": 3200},
        {"name": "Emploi agricole", "category": "emploi", "sector": "vegetal", "unit": "%", "base": 32.5},
        {"name": "Inflation alimentaire", "category": "prix", "sector": "vegetal", "unit": "%", "base": 5.2},
        {"name": "Exportations agricoles", "category": "marché", "sector": "vegetal", "unit": "Mds FCFA", "base": 890},
        {"name": "Importations alimentaires", "category": "marché", "sector": "vegetal", "unit": "Mds FCFA", "base": 1200},
        {"name": "Investissement agricole", "category": "marché", "sector": "vegetal", "unit": "Mds FCFA", "base": 450},
        {"name": "Pluviométrie annuelle", "category": "climat", "sector": "vegetal", "unit": "mm", "base": 850},
        {"name": "Température moyenne", "category": "climat", "sector": "vegetal", "unit": "°C", "base": 28.5},
        {"name": "Indice de végétation", "category": "environnement", "sector": "vegetal", "unit": "NDVI", "base": 0.72},
    ]

    countries = ["Sénégal", "Mali", "Côte d'Ivoire", "Ghana", "Nigeria", "Burkina Faso", "Togo", "Bénin"]

    for i, ind in enumerate(base_indicators):
        if search and search.lower() not in ind["name"].lower():
            continue
        if sector and ind["sector"] != sector:
            continue
        if category and ind["category"] != category:
            continue

        country = random.choice(countries)
        value = round(ind["base"] * (0.85 + random.random() * 0.3), 2)
        prev_value = round(ind["base"] * (0.80 + random.random() * 0.3), 2)
        trend_pct = round(((value - prev_value) / prev_value) * 100, 1)
        trend = "up" if trend_pct > 1 else "down" if trend_pct < -1 else "stable"

        threshold_critical = ind["base"] * (0.5 if trend in ["up", "stable"] else 1.5)
        threshold_alert = ind["base"] * (0.7 if trend in ["up", "stable"] else 1.3)

        indicators.append({
            "id": f"ind-{i + 1}",
            "name": ind["name"],
            "description": f"{ind['name']} - Indicateur de suivi {ind['category']}",
            "category": ind["category"],
            "sector": ind["sector"],
            "unit": ind["unit"],
            "value": value,
            "previous_value": prev_value,
            "trend": trend,
            "trend_percent": trend_pct,
            "period": "annual",
            "year": 2024,
            "country": country,
            "source": "FAO / ANSD",
            "threshold_critical": round(threshold_critical, 2),
            "threshold_alert": round(threshold_alert, 2),
            "threshold_optimal": round(ind["base"] * 1.2, 2),
            "higher_is_better": trend in ["up", "stable"],
            "health_status": "optimal" if abs(trend_pct) < 5 else "alert" if abs(trend_pct) < 15 else "critical",
            "history": _generate_history(24, value, value * 0.1),
            "last_updated": (datetime.utcnow() - timedelta(hours=random.randint(1, 72))).isoformat() + "Z",
        })

        if len(indicators) >= limit:
            break

    return {"data": indicators, "count": len(indicators)}


# ─── Detail ───────────────────────────────────────────────────────────────────

@router.get("/{id}")
async def get_indicator(
    id: str,
    current_user: User = Depends(get_current_verified_user),
):
    """Récupérer un indicateur par ID avec historique"""
    import hashlib
    seed = int(hashlib.md5(id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)

    base = 100 + (seed % 9000)
    value = round(base * (0.85 + rng.random() * 0.3), 2)
    prev = round(base * (0.80 + rng.random() * 0.3), 2)
    trend_pct = round(((value - prev) / prev) * 100, 1)
    trend = "up" if trend_pct > 1 else "down" if trend_pct < -1 else "stable"

    return {
        "id": id,
        "name": f"Indicateur {id}",
        "description": "Description détaillée de l'indicateur avec son contexte et son objectif",
        "category": "production",
        "sector": "vegetal",
        "unit": "t/ha",
        "value": value,
        "previous_value": prev,
        "trend": trend,
        "trend_percent": trend_pct,
        "period": "monthly",
        "year": 2024,
        "country": "Sénégal",
        "source": "ANSD",
        "history": _generate_history(36, value, value * 0.12),
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }


# ─── History ──────────────────────────────────────────────────────────────────

@router.get("/{id}/history")
async def get_indicator_history(
    id: str,
    period: str = "monthly",
    current_user: User = Depends(get_current_verified_user),
):
    """Historique d'un indicateur"""
    import hashlib
    seed = int(hashlib.md5(id.encode()).hexdigest()[:8], 16)
    base = 50 + (seed % 200)
    days = {"daily": 90, "weekly": 52, "monthly": 24, "quarterly": 8, "annual": 5}
    d = days.get(period, 24)

    return {
        "indicator_id": id,
        "data": _generate_history(d, base, base * 0.15),
        "period": period,
        "total_points": d,
    }


# ─── Thresholds ───────────────────────────────────────────────────────────────

@router.patch("/{id}/thresholds")
async def update_indicator_thresholds(
    id: str,
    thresholds: dict,
    current_user: User = Depends(get_current_verified_user),
):
    """Mettre à jour les seuils d'un indicateur"""
    return {
        "message": "Seuils mis à jour avec succès",
        "id": id,
        "thresholds": thresholds,
    }


# ─── Image Upload ─────────────────────────────────────────────────────────────

@router.post("/upload-image")
async def upload_indicator_image(
    file: UploadFile = File(...),
    indicator_id: str = Form(default=""),
    current_user: User = Depends(get_current_verified_user),
):
    """Upload d'image pour analyse d'indicateur visuel"""
    if not MODEL_SUPPORTS_IMAGES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "IMAGE_NOT_SUPPORTED",
                "message": f'Impossible de lire "{file.filename}" (ce modèle ne supporte pas les images). '
                           f'Le modèle "{CURRENT_MODEL}" est un modèle d\'indicateurs agricoles qui '
                           f"traite uniquement des données statistiques et numériques. "
                           f"Pour l'analyse d'images, utilisez plutôt l'assistant IA.",
                "model": CURRENT_MODEL,
                "supported_inputs": ["statistiques", "séries temporelles", "données par pays", "seuils"],
            }
        )
    return {"status": "processing", "message": "Analyse d'image en cours...", "file": file.filename}


# ─── Export ───────────────────────────────────────────────────────────────────

@router.post("/export")
async def export_indicators(
    ids: list[str],
    current_user: User = Depends(get_current_verified_user),
):
    """Exporter des indicateurs"""
    if not ids:
        raise HTTPException(status_code=400, detail="Aucun ID fourni")
    return {
        "format": "csv",
        "data": "id,nom,valeur,unite,tendance,pays,date\n" + "\n".join(
            f"{i},Indicateur {i},{round(100+random.random()*50,2)},{['t/ha','FCFA','%'][i%3]},{['hausse','baisse','stable'][i%3]},Sénégal,2024-01-{str(i+1).zfill(2)}"
            for i, _  in enumerate(ids[:50])
        ),
        "count": min(len(ids), 50),
    }
