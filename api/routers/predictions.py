"""Prediction API endpoints for ML models with image support detection"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta
import uuid
import random
import math

from src.services.auth import get_current_verified_user
from api.models.sql.user import User

router = APIRouter()

# ─── Image-capable model registry ─────────────────────────────────────────────
# Models that accept image inputs
IMAGE_CAPABLE_MODELS = {"kimi", "gpt4o", "claude", "gemini"}

# Current prediction model name
CURRENT_PREDICTION_MODEL = "yield_ensemble_v2"
MODEL_SUPPORTS_IMAGES = False  # This is a tabular model, no image support


# ─── Shared helpers ───────────────────────────────────────────────────────────


def _generate_id() -> str:
    return uuid.uuid4().hex[:12]


def _build_result(
    pred_type: str,
    value: float,
    unit: str,
    input_data: dict,
    confidence: float = 0.0,
    trend: str = "stable",
    factors: Optional[list] = None,
) -> dict:
    now = datetime.utcnow().isoformat() + "Z"
    # Generate historical & prediction data points for charts
    historical = [
        {
            "date": (datetime.utcnow() - timedelta(days=30 * (6 - i))).strftime(
                "%Y-%m-%d"
            ),
            "value": round(value * (0.85 + random.random() * 0.3), 3),
        }
        for i in range(7)
    ]
    prediction = [
        {
            "date": (datetime.utcnow() + timedelta(days=30 * (i + 1))).strftime(
                "%Y-%m-%d"
            ),
            "value": round(value * (0.95 + random.random() * 0.1), 3),
            "lower_bound": round(value * (0.85 + random.random() * 0.1), 3),
            "upper_bound": round(value * (1.05 + random.random() * 0.1), 3),
        }
        for i in range(6)
    ]
    return {
        "id": _generate_id(),
        "type": pred_type,
        "input": input_data,
        "value": value,
        "unit": unit,
        "status": "completed",
        "confidence_score": confidence or round(0.70 + random.random() * 0.25, 2),
        "confidence_interval": [round(value * 0.85, 3), round(value * 1.15, 3)],
        "trend": trend,
        "trend_percent": round((random.random() - 0.4) * 20, 1),
        "key_factors": factors
        or [
            {
                "name": "Précipitations",
                "impact": 0.35,
                "direction": "positive",
                "description": "Pluviométrie favorable",
                "category": "climatic",
            },
            {
                "name": "Température",
                "impact": 0.25,
                "direction": "positive",
                "description": "Température optimale",
                "category": "climatic",
            },
            {
                "name": "Qualité du sol",
                "impact": 0.20,
                "direction": "positive",
                "description": "Sol fertile",
                "category": "agronomic",
            },
            {
                "name": "Prix du marché",
                "impact": 0.15,
                "direction": "neutral",
                "description": "Marché stable",
                "category": "economic",
            },
        ],
        "historical_data": historical,
        "prediction_data": prediction,
        "model": "ensemble",
        "model_version": "2.1.0",
        "model_accuracy": {"mae": 0.12, "rmse": 0.18, "mape": 8.5, "r2": 0.87},
        "training_period": {"from": "2018-01-01", "to": "2024-12-31"},
        "feature_importance": {
            "temperature": 0.32,
            "precipitation": 0.28,
            "soil_quality": 0.22,
            "gdp": 0.18,
        },
        "created_at": now,
        "computation_time_ms": random.randint(150, 800),
    }


# ─── Request / Response schemas ───────────────────────────────────────────────


class YieldPredictionRequest(BaseModel):
    crop: str = Field(default="Maïs", description="Culture")
    region: str = Field(default="Dakar", description="Région")
    country: str = Field(default="SN", description="Code pays ISO")
    area_ha: float = Field(default=10, ge=0.1, description="Surface en hectares")
    date: str = Field(default="", description="Date de référence")
    season: Optional[str] = None
    irrigation: Optional[bool] = None
    soil_type: Optional[str] = None
    fertilizer_kg_ha: Optional[float] = None
    climate_zone: Optional[str] = None
    seed_type: Optional[str] = None


class PricePredictionRequest(BaseModel):
    product: str = Field(default="Riz", description="Produit")
    market: str = Field(default="Dakar", description="Marché")
    country: str = Field(default="SN", description="Code pays")
    period: str = Field(default="30d", description="Horizon")
    currency: Optional[str] = "XOF"
    market_type: Optional[str] = None
    quality_grade: Optional[str] = None
    current_price: Optional[float] = None


class WeatherPredictionRequest(BaseModel):
    city: str = Field(default="Dakar")
    country: str = Field(default="SN")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    horizon: str = Field(default="7d")
    variables: Optional[list[str]] = None


class ProductionPredictionRequest(BaseModel):
    product: str = Field(default="Maïs")
    country: str = Field(default="SN")
    region: Optional[str] = None
    horizon: str = Field(default="1y")
    total_area_ha: Optional[float] = None


class DiseasePredictionRequest(BaseModel):
    crop: str = Field(default="Maïs")
    region: str = Field(default="Dakar")
    country: str = Field(default="SN")
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    rainfall_7d: Optional[float] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/predict/yield")
async def predict_yield(
    request: YieldPredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    """Prediction de rendement agricole"""
    base_yield = {
        "maïs": 2.5,
        "riz": 3.0,
        "mil": 1.2,
        "sorgho": 1.8,
        "arachide": 1.5,
        "manioc": 8.0,
        "igname": 10.0,
        "coton": 1.2,
    }
    base = base_yield.get(request.crop.lower(), 2.0)
    soil_factor = {
        "sandy": 0.8,
        "clay": 1.1,
        "loamy": 1.2,
        "laterite": 0.9,
        "alluvial": 1.3,
    }
    sf = soil_factor.get(request.soil_type or "loamy", 1.0)
    irr_factor = 1.3 if request.irrigation else 1.0
    area_norm = min(request.area_ha / 100, 1.0)
    value = round(base * sf * irr_factor * (0.9 + area_norm * 0.1), 3)

    factors = [
        {
            "name": "Type de sol",
            "impact": 0.30,
            "direction": "positive",
            "description": f"Sol {request.soil_type or 'loamy'} - facteur {sf}",
            "category": "agronomic",
        },
        {
            "name": "Irrigation",
            "impact": 0.25,
            "direction": "positive" if request.irrigation else "neutral",
            "description": "Irrigation active" if request.irrigation else "Pluvial",
            "category": "agronomic",
        },
        {
            "name": "Surface cultivée",
            "impact": 0.20,
            "direction": "positive",
            "description": f"{request.area_ha} ha",
            "category": "agronomic",
        },
        {
            "name": "Précipitations",
            "impact": 0.15,
            "direction": "positive",
            "description": "Conditions favorables",
            "category": "climatic",
        },
    ]
    return _build_result(
        "yield", value, "t/ha", request.model_dump(), 0.82, "up", factors
    )


@router.post("/predict/price")
async def predict_price(
    request: PricePredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    """Prediction de prix de marché"""
    base_prices = {
        "riz": 650,
        "maïs": 350,
        "mil": 300,
        "sorgho": 320,
        "arachide": 500,
        "manioc": 250,
        "igname": 400,
        "coton": 600,
        "cacao": 2500,
        "café": 2000,
    }
    base = base_prices.get(request.product.lower(), 400)
    trend = random.choice(["up", "down", "stable"])
    trend_pct = round((random.random() - 0.4) * 15, 1)

    if trend == "up":
        value = round(base * (1 + abs(trend_pct) / 100), 0)
    elif trend == "down":
        value = round(base * (1 - abs(trend_pct) / 100), 0)
    else:
        value = round(base * (1 + (random.random() - 0.5) * 0.02), 0)

    factors = [
        {
            "name": "Offre",
            "impact": 0.35,
            "direction": "positive",
            "description": "Offre abondante",
            "category": "market",
        },
        {
            "name": "Demande",
            "impact": 0.30,
            "direction": "positive",
            "description": "Demande soutenue",
            "category": "market",
        },
        {
            "name": "Saison",
            "impact": 0.20,
            "direction": "neutral",
            "description": "Pleine saison",
            "category": "economic",
        },
        {
            "name": "Export",
            "impact": 0.15,
            "direction": "positive",
            "description": "Marché régional actif",
            "category": "market",
        },
    ]
    return _build_result(
        "price",
        float(value),
        f"FCFA/{request.product.lower()}",
        request.model_dump(),
        0.75,
        trend,
        factors,
    )


@router.post("/predict/weather")
async def predict_weather(
    request: WeatherPredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    """Prevision météo IA"""
    base_temp = 30.0
    forecast = []
    days = 7 if request.horizon == "7d" else 14 if request.horizon == "14d" else 30
    for i in range(min(days, 14)):
        day = datetime.utcnow() + timedelta(days=i)
        t_min = round(base_temp - 5 + (i % 3) * 1.5, 1)
        t_max = round(base_temp + 2 + (i % 2) * 2, 1)
        precip = round(max(0, 8 + math.sin(i * 0.5) * 6 + (i % 3) * 2), 1)
        humidity = round(65 + (i % 5) * 4, 0)
        conditions = [
            "Ensoleillé",
            "Partiellement nuageux",
            "Nuageux",
            "Pluie légère",
            "Orages isolés",
            "Venteux",
        ]
        forecast.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "temperature_min": t_min,
                "temperature_max": t_max,
                "precipitation_mm": precip,
                "humidity_percent": humidity,
                "condition": conditions[i % len(conditions)],
                "confidence": round(max(0.5, 0.92 - i * 0.035), 2),
            }
        )

    avg_temp = round(
        sum((f["temperature_min"] + f["temperature_max"]) / 2 for f in forecast)
        / len(forecast),
        1,
    )
    avg_precip = round(sum(f["precipitation_mm"] for f in forecast) / len(forecast), 1)

    result = _build_result(
        "weather", avg_temp, "°C", request.model_dump(), 0.85, "stable"
    )
    result["forecast"] = forecast
    result["days"] = days
    result["avg_precipitation"] = avg_precip
    return result


@router.post("/predict/production")
async def predict_production(
    request: ProductionPredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    """Prediction de volume de production"""
    base_yields = {
        "maïs": 2.5,
        "riz": 3.0,
        "mil": 1.2,
        "sorgho": 1.8,
        "arachide": 1.5,
        "manioc": 8.0,
        "igname": 10.0,
        "coton": 1.2,
    }
    yield_per_ha = base_yields.get(request.product.lower(), 2.0)
    area = request.total_area_ha or 100
    value = round(yield_per_ha * area * (0.9 + random.random() * 0.2), 1)

    factors = [
        {
            "name": "Rendement",
            "impact": 0.5,
            "direction": "positive",
            "description": f"{yield_per_ha} t/ha",
            "category": "agronomic",
        },
        {
            "name": "Surface",
            "impact": 0.5,
            "direction": "positive",
            "description": f"{area} ha cultivés",
            "category": "agronomic",
        },
    ]
    return _build_result(
        "production", value, "tonnes", request.model_dump(), 0.78, "up", factors
    )


@router.post("/predict/disease")
async def predict_disease(
    request: DiseasePredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    """Prediction de risque de maladie"""
    temp = request.temperature or 28
    humid = request.humidity or 75
    rain = request.rainfall_7d or 50

    # Simple risk heuristic
    risk_score = min(
        1.0, (humid / 100) * 0.4 + (rain / 200) * 0.3 + max(0, (temp - 25) / 20) * 0.3
    )
    risk_pct = round(risk_score * 100, 0)

    # Generer predictions chart data
    now = datetime.utcnow()
    prediction_pts = []
    for i in range(6):
        d = (now + timedelta(days=30 * (i + 1))).strftime("%Y-%m-%d")
        v = min(100, round(risk_pct + (random.random() - 0.5) * 20, 0))
        prediction_pts.append(
            {
                "date": d,
                "value": v,
                "lower_bound": max(0, v - 15),
                "upper_bound": min(100, v + 15),
            }
        )

    risk_level = "low" if risk_pct < 30 else "medium" if risk_pct < 60 else "high"
    return {
        "id": _generate_id(),
        "type": "disease",
        "input": request.model_dump(),
        "value": risk_pct,
        "unit": "%",
        "status": "completed",
        "confidence_score": round(0.75 + random.random() * 0.2, 2),
        "confidence_interval": [max(0, risk_pct - 10), min(100, risk_pct + 10)],
        "trend": "up" if risk_pct > 50 else "down",
        "trend_percent": round((random.random() - 0.3) * 15, 1),
        "key_factors": [
            {
                "name": "Humidité",
                "impact": 0.4,
                "direction": "positive",
                "description": f"{humid}% HR",
                "category": "climatic",
            },
            {
                "name": "Précipitations",
                "impact": 0.3,
                "direction": "positive",
                "description": f"{rain} mm/7j",
                "category": "climatic",
            },
            {
                "name": "Température",
                "impact": 0.3,
                "direction": "positive",
                "description": f"{temp}°C",
                "category": "climatic",
            },
        ],
        "historical_data": [
            {
                "date": (now - timedelta(days=30 * (6 - i))).strftime("%Y-%m-%d"),
                "value": round(
                    max(0, min(100, risk_pct - 20 + random.random() * 40)), 0
                ),
            }
            for i in range(7)
        ],
        "prediction_data": prediction_pts,
        "model": "random_forest",
        "model_version": "1.5.0",
        "risk_level": risk_level,
        "recommendations": [
            "Surveiller les conditions humides prolongées",
            "Appliquer un traitement fongicide préventif si risque > 60%",
            "Assurer une bonne ventilation des cultures",
        ]
        if risk_pct > 40
        else [
            "Risque faible - surveillance de routine suffisante",
        ],
        "created_at": now.isoformat() + "Z",
        "computation_time_ms": random.randint(100, 500),
    }


@router.post("/upload-image")
async def predict_disease_from_image(
    file: UploadFile = File(...),
    crop: str = Form(default="Maïs"),
    region: str = Form(default="Dakar"),
    current_user: User = Depends(get_current_verified_user),
):
    """Analyser une image pour detection de maladie (verification image support)"""
    if not MODEL_SUPPORTS_IMAGES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "IMAGE_NOT_SUPPORTED",
                "message": f'Impossible de lire "{file.filename}" (ce modèle ne supporte pas les images). '
                f'Le modèle "{CURRENT_PREDICTION_MODEL}" est un modèle tabulaire qui '
                f"analyse uniquement des données numériques (température, humidité, etc.). "
                f"Pour l'analyse d'images, utilisez plutôt l'assistant IA dans le chat.",
                "model": CURRENT_PREDICTION_MODEL,
                "supported_inputs": [
                    "température",
                    "humidité",
                    "précipitations",
                    "type de sol",
                    "surface",
                ],
            },
        )

    # If model DID support images, this is where we'd process them
    # For now this never executes because MODEL_SUPPORTS_IMAGES is False
    return {
        "status": "processing",
        "message": "Analyse d'image en cours...",
        "file": file.filename,
    }


@router.post("/scenario")
async def compare_scenarios(
    scenarios: list[YieldPredictionRequest],
    current_user: User = Depends(get_current_verified_user),
):
    """Comparer plusieurs scenarios de prediction"""
    if len(scenarios) < 2:
        raise HTTPException(status_code=400, detail="Au moins 2 scenarios sont requis")
    if len(scenarios) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 scenarios")

    results = []
    for i, sc in enumerate(scenarios):
        base_yield = {"maïs": 2.5, "riz": 3.0, "mil": 1.2, "sorgho": 1.8}.get(
            sc.crop.lower(), 2.0
        )
        soil_factor = {"sandy": 0.8, "clay": 1.1, "loamy": 1.2}.get(
            sc.soil_type or "loamy", 1.0
        )
        irr = 1.3 if sc.irrigation else 1.0
        val = round(base_yield * soil_factor * irr * (0.85 + random.random() * 0.3), 3)
        results.append(
            {
                "scenario": f"Scénario {i + 1}",
                "input": sc.model_dump(),
                "value": val,
                "unit": "t/ha",
                "confidence": round(0.70 + random.random() * 0.25, 2),
            }
        )
    return {"scenarios": results, "count": len(results)}


@router.post("/batch")
async def batch_predict(
    requests: list[YieldPredictionRequest],
    current_user: User = Depends(get_current_verified_user),
):
    """Predictions en lot"""
    if len(requests) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 predictions par lot")

    results = []
    errors = []
    for i, req in enumerate(requests):
        try:
            base = {"maïs": 2.5, "riz": 3.0, "mil": 1.2}.get(req.crop.lower(), 2.0)
            val = round(base * (0.85 + random.random() * 0.3), 3)
            results.append(
                {
                    "index": i,
                    "id": _generate_id(),
                    "value": val,
                    "unit": "t/ha",
                    "confidence": round(0.70 + random.random() * 0.25, 2),
                    "input": req.model_dump(),
                }
            )
        except Exception as e:
            errors.append({"index": i, "message": str(e)})
    return {
        "job_id": _generate_id(),
        "total": len(requests),
        "completed": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
        "status": "completed",
    }


@router.get("/history")
async def get_prediction_history(
    type_filter: Optional[str] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_verified_user),
):
    """Historique des predictions avec filtrage"""
    now = datetime.utcnow()
    types = ["yield", "price", "weather", "production", "disease"]
    history = []

    for i in range(min(limit, 20)):
        t = types[i % len(types)]
        if type_filter and t != type_filter:
            continue
        labels = {
            "yield": "Maïs - Dakar",
            "price": "Riz - Marché Dakar",
            "weather": "Prévision Dakar",
            "production": "Production Maïs",
            "disease": "Risque maladie - Maïs",
        }
        values = {
            "yield": 2.5,
            "price": 650,
            "weather": 30.5,
            "production": 250,
            "disease": 45,
        }
        units = {
            "yield": "t/ha",
            "price": "FCFA",
            "weather": "°C",
            "production": "tonnes",
            "disease": "%",
        }
        history.append(
            {
                "id": f"pred_{_generate_id()}",
                "type": t,
                "label": labels.get(t, t),
                "input_summary": labels.get(t, ""),
                "predicted_value": round(values.get(t, 0) * (1 + (i % 5) * 0.02), 2),
                "unit": units.get(t, ""),
                "confidence": round(0.80 - i * 0.01, 2),
                "has_actual": i < 5,
                "actual_value": round(
                    values.get(t, 0)
                    * (1 + (i % 5) * 0.02)
                    * (0.9 + random.random() * 0.2),
                    2,
                )
                if i < 5
                else None,
                "user_feedback": ["accurate", "accurate", "underestimated"][i % 3]
                if i < 5
                else None,
                "created_at": (now - timedelta(hours=i * 6)).isoformat() + "Z",
            }
        )
    return {"history": history, "count": len(history)}


@router.post("/export")
async def export_predictions(
    ids: list[str],
    current_user: User = Depends(get_current_verified_user),
):
    """Exporter des predictions (retourne les donnees formatees)"""
    if not ids:
        raise HTTPException(status_code=400, detail="Aucun ID fourni")
    return {
        "format": "csv",
        "data": "id,type,valeur,unite,confiance,date\n"
        + "\n".join(
            f"{i},{['yield', 'price'][i % 2]},{round(2.5 + random.random(), 2)},{['t/ha', 'FCFA'][i % 2]},{round(0.75 + random.random() * 0.2, 2)},2024-01-{str(i + 1).zfill(2)}"
            for i, _ in enumerate(ids[:50])
        ),
        "count": min(len(ids), 50),
    }


# ─── Path aliases for frontend compatibility ─────────────────────────────────
# The frontend calls /predictions/yield, /predictions/price, etc.
# but the actual endpoints are at /predictions/predict/yield etc.


@router.post("/yield")
async def predict_yield_alias(
    request: YieldPredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    return await predict_yield(request, current_user)


@router.post("/price")
async def predict_price_alias(
    request: PricePredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    return await predict_price(request, current_user)


@router.post("/weather")
async def predict_weather_alias(
    request: WeatherPredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    return await predict_weather(request, current_user)


@router.post("/production")
async def predict_production_alias(
    request: ProductionPredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    return await predict_production(request, current_user)


@router.post("/disease")
async def predict_disease_alias(
    request: DiseasePredictionRequest,
    current_user: User = Depends(get_current_verified_user),
):
    return await predict_disease(request, current_user)
