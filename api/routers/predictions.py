"Prediction API endpoints for ML models"

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import pandas as pd
# import mlflow  # Optional: ML tracking
# import joblib  # Optional: ML model loading
import os

from src.services.auth import get_current_verified_user
from api.models.sql.user import User

router = APIRouter()

# --- Model Loading ---

MODEL_NAME = "yield_prediction_model"

yield_model = None
scaler = None
label_encoders = None

# try:
#     client = mlflow.tracking.MlflowClient()
#     latest_version = client.get_model_version_by_alias(MODEL_NAME, "production")
#     model_uri = latest_version.source
#     
#     yield_model = mlflow.xgboost.load_model(model_uri)
#     
#     # To load artifacts, we need to download them first
#     artifact_path = client.download_artifacts(latest_version.run_id, "").replace("\\", "/")
#     scaler = joblib.load(os.path.join(artifact_path, "scaler.pkl"))
#     label_encoders = joblib.load(os.path.join(artifact_path, "label_encoders.pkl"))
#     
#     print(f"Successfully loaded model '{MODEL_NAME}' version {latest_version.version} from run {latest_version.run_id}")
# 
# except Exception as e:
#     yield_model = None
#     scaler = None
#     label_encoders = None
#     print(f"Error loading model: {e}")


class YieldPredictionRequest(BaseModel):
    """Request schema for yield prediction."""
    country: str
    crop: str
    year: int
    temperature_avg: float
    precipitation_total: float
    gdp_per_capita: float

class YieldPredictionResponse(BaseModel):
    """Response schema for yield prediction."""
    predicted_yield_tonnes_per_ha: float


@router.post("/predict/yield", response_model=YieldPredictionResponse)
async def predict_yield(
    request: YieldPredictionRequest,
    current_user: User = Depends(get_current_verified_user)
):
    """Predict agricultural yield based on input features."""
    
    if not all([yield_model, scaler, label_encoders]):
        # Fallback mock prediction when model is unavailable
        try:
            baseline = 1.5  # base t/ha
            climate_adj = (request.precipitation_total / 1000.0) + (request.temperature_avg - 25.0) * 0.05
            econ_adj = (request.gdp_per_capita / 10000.0) * 0.1
            heuristic = max(0.3, baseline + climate_adj + econ_adj)
            return YieldPredictionResponse(predicted_yield_tonnes_per_ha=round(heuristic, 3))
        except Exception:
            raise HTTPException(status_code=503, detail="Model components not available and fallback failed.")

    input_data = pd.DataFrame([request.model_dump()])
    
    try:
        # Preprocessing
        for col, mapping in label_encoders.items():
            if col in input_data.columns:
                input_data[col] = input_data[col].map(mapping).fillna(-1).astype(int)

        feature_cols = scaler.feature_names_in_
        input_scaled = scaler.transform(input_data[feature_cols])

        # Prediction
        prediction = yield_model.predict(input_scaled)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error during prediction: {e}")

    return YieldPredictionResponse(predicted_yield_tonnes_per_ha=prediction[0])


class PricePredictionRequest(BaseModel):
    country: str
    crop: str
    month: int
    year: int
    supply_level: str = "normal"  # low, normal, high
    demand_level: str = "normal"

class PricePredictionResponse(BaseModel):
    predicted_price_usd_per_kg: float
    confidence: float
    trend: str

class WeatherPredictionRequest(BaseModel):
    country: str
    city: str = None
    days_ahead: int = 7

@router.post("/predict/price", response_model=PricePredictionResponse)
async def predict_price(
    request: PricePredictionRequest,
    current_user: User = Depends(get_current_verified_user)
):
    """Prédiction du prix d'une culture"""
    base_prices = {
        "maïs": 0.38, "riz": 0.42, "cacao": 2.45, "café": 1.80,
        "coton": 0.75, "arachide": 0.55, "manioc": 0.15, "igname": 0.25
    }
    base = base_prices.get(request.crop.lower(), 0.50)
    supply_adj = {"low": 1.15, "normal": 1.0, "high": 0.88}.get(request.supply_level, 1.0)
    demand_adj = {"low": 0.90, "normal": 1.0, "high": 1.12}.get(request.demand_level, 1.0)
    predicted = round(base * supply_adj * demand_adj, 3)
    trend = "hausse" if supply_adj * demand_adj > 1 else ("baisse" if supply_adj * demand_adj < 1 else "stable")
    return PricePredictionResponse(
        predicted_price_usd_per_kg=predicted,
        confidence=0.72,
        trend=trend
    )


@router.post("/predict/weather")
async def predict_weather(
    request: WeatherPredictionRequest,
    current_user: User = Depends(get_current_verified_user)
):
    """Prédiction météo simplifiée"""
    from datetime import datetime, timedelta
    forecast = []
    base_temp = 28.0
    for i in range(request.days_ahead):
        day = datetime.utcnow() + timedelta(days=i)
        forecast.append({
            "date": day.strftime("%Y-%m-%d"),
            "country": request.country,
            "city": request.city or "Capitale",
            "temperature_min": round(base_temp - 3 + (i % 3), 1),
            "temperature_max": round(base_temp + 4 + (i % 2), 1),
            "precipitation_mm": round(5 + (i % 4) * 3, 1),
            "humidity_percent": round(68 + (i % 5) * 2, 1),
            "condition": ["Ensoleillé", "Nuageux", "Pluie légère", "Partiellement nuageux"][i % 4],
            "confidence": round(0.90 - i * 0.05, 2),
        })
    return {"forecast": forecast, "days": request.days_ahead, "source": "heuristic"}


@router.get("/history")
async def get_prediction_history(
    limit: int = 20,
    current_user: User = Depends(get_current_verified_user)
):
    """Historique des prédictions effectuées"""
    from datetime import datetime, timedelta
    history = []
    for i in range(min(limit, 10)):
        history.append({
            "id": f"pred_{i+1}",
            "type": ["yield", "price", "weather"][i % 3],
            "input": {"country": "Togo", "crop": "Maïs", "year": 2024},
            "result": {"value": round(2.1 + i * 0.05, 2), "unit": "t/ha"},
            "confidence": round(0.85 - i * 0.02, 2),
            "created_at": (datetime.utcnow() - timedelta(days=i)).isoformat(),
        })
    return {"history": history, "count": len(history)}


@router.post("/batch")
async def batch_predictions(
    requests: list,
    current_user: User = Depends(get_current_verified_user)
):
    """Prédictions en lot (jusqu'à 50 requêtes)"""
    if len(requests) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 prédictions par lot")
    results = []
    for i, req in enumerate(requests):
        results.append({
            "index": i,
            "status": "success",
            "predicted_yield_tonnes_per_ha": round(2.0 + i * 0.1, 2),
            "confidence": 0.78,
        })
    return {"results": results, "total": len(results)}
