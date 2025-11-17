"Prediction API endpoints for ML models"

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import pandas as pd
import mlflow
import joblib
import os

from src.services.auth import get_current_verified_user
from api.models.sql.user import User

router = APIRouter()

# --- Model Loading ---

MODEL_NAME = "yield_prediction_model"

try:
    client = mlflow.tracking.MlflowClient()
    latest_version = client.get_model_version_by_alias(MODEL_NAME, "production")
    model_uri = latest_version.source
    
    yield_model = mlflow.xgboost.load_model(model_uri)
    
    # To load artifacts, we need to download them first
    artifact_path = client.download_artifacts(latest_version.run_id, "").replace("\\", "/")
    scaler = joblib.load(os.path.join(artifact_path, "scaler.pkl"))
    label_encoders = joblib.load(os.path.join(artifact_path, "label_encoders.pkl"))
    
    print(f"Successfully loaded model '{MODEL_NAME}' version {latest_version.version} from run {latest_version.run_id}")

except Exception as e:
    yield_model = None
    scaler = None
    label_encoders = None
    print(f"Error loading model: {e}")


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