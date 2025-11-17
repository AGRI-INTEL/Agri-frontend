"""
AgriIntel360 - Yield Prediction Model Training Pipeline
Uses XGBoost, MLflow for tracking, and GridSearchCV for hyperparameter tuning.
"""

import pandas as pd
import numpy as np
import joblib
import logging
from datetime import datetime
import warnings
import matplotlib.pyplot as plt
import os

from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import mean_squared_error, r2_score
from sqlalchemy import create_engine
import xgboost as xgb

import mlflow
import mlflow.xgboost
import shap

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

MODEL_NAME = "yield_prediction_model"

class YieldPredictionModel:
    """Agricultural Yield Prediction Model"""
    
    def __init__(self, db_url, experiment_name="Yield_Prediction"):
        self.db_url = db_url
        self.engine = create_engine(self.db_url)
        self.model = None
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.feature_columns = []
        self.target_column = 'yield_tonnes_per_ha'
        mlflow.set_experiment(experiment_name)
        
    def fetch_data(self):
        """Fetches training data from the database."""
        logging.info("Fetching data from the database...")
        # This query joins different staging tables to create a feature set.
        # In a real-world scenario, this would be more complex and might involve a dedicated feature store.
        # For this example, we assume some data has been loaded into these tables.
        query = """
            SELECT 
                p.country_name as country,
                p.crop_name as crop,
                p.year,
                p.production_tonnes,
                w.temperature_celsius as temperature_avg,
                w.precipitation_mm as precipitation_total,
                e.value as gdp_per_capita
            FROM staging_production p
            LEFT JOIN staging_weather w ON p.country_name = w.city AND p.year = EXTRACT(YEAR FROM w.date)
            LEFT JOIN staging_economic e ON p.country_name = e.country_name AND p.year = e.year
            WHERE e.indicator = 'gdp_current_usd' AND p.unit = 'tonnes'
            LIMIT 1000;
        """
        try:
            df = pd.read_sql(query, self.engine)
            if df.empty:
                logging.warning("No data fetched from the database. Using sample fallback data.")
                return self.get_fallback_data()

            logging.info(f"Successfully fetched {len(df)} records.")
            # Simple data cleaning and feature engineering for the example
            df['yield_tonnes_per_ha'] = df['production_tonnes'] / 1000 # Simplified
            return df
        except Exception as e:
            logging.error(f"Error fetching data: {e}. Using sample fallback data.")
            return self.get_fallback_data()

    def get_fallback_data(self):
        """Generates sample data if the database is empty."""
        data = {
            'country': ['Togo', 'Ghana', 'Nigeria', 'Togo', 'Ghana', 'Nigeria'] * 10,
            'crop': ['Maize', 'Rice', 'Cassava', 'Maize', 'Rice', 'Cassava'] * 10,
            'year': [2020, 2020, 2020, 2021, 2021, 2021] * 10,
            'production_tonnes': np.random.randint(1000, 5000, 60),
            'temperature_avg': np.random.uniform(25, 30, 60),
            'precipitation_total': np.random.uniform(800, 1500, 60),
            'gdp_per_capita': np.random.uniform(500, 2500, 60)
        }
        df = pd.DataFrame(data)
        df['yield_tonnes_per_ha'] = df['production_tonnes'] / np.random.uniform(500, 800, 60)
        return df

    def prepare_data(self, df):
        """Prepares data for training."""
        logging.info("Preparing data...")
        df_clean = df.dropna(subset=[self.target_column])
        
        # Encode categorical variables
        for col in ['country', 'crop']:
            df_clean[col] = pd.Categorical(df_clean[col])
            self.label_encoders[col] = dict(zip(df_clean[col].cat.categories, range(len(df_clean[col].cat.categories))))
            df_clean[col] = df_clean[col].cat.codes
            
        self.feature_columns = ['year', 'temperature_avg', 'precipitation_total', 'gdp_per_capita', 'country', 'crop']
        X = df_clean[self.feature_columns]
        y = df_clean[self.target_column]
        
        logging.info(f"Data prepared: {X.shape[0]} samples, {X.shape[1]} features")
        return X, y

    def train(self, df):
        """Trains the model with hyperparameter tuning and MLflow tracking."""
        logging.info("Starting model training...")
        X, y = self.prepare_data(df)
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        with mlflow.start_run() as run:
            run_id = run.info.run_id
            logging.info(f"MLflow run started (Run ID: {run_id})")
            mlflow.log_param("train_test_split_random_state", 42)

            # Hyperparameter tuning with GridSearchCV
            param_grid = {
                'max_depth': [3, 5],
                'learning_rate': [0.05, 0.1],
                'n_estimators': [100],
                'subsample': [0.7]
            }
            
            xgb_reg = xgb.XGBRegressor(objective='reg:squarederror', random_state=42)
            
            grid_search = GridSearchCV(estimator=xgb_reg, param_grid=param_grid, cv=3, 
                                       scoring='neg_mean_squared_error', verbose=1, n_jobs=-1)
            
            grid_search.fit(X_train_scaled, y_train)
            
            self.model = grid_search.best_estimator_
            logging.info(f"Best hyperparameters: {grid_search.best_params_}")
            mlflow.log_params(grid_search.best_params_)

            # Final evaluation
            y_pred = self.model.predict(X_test_scaled)
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))
            r2 = r2_score(y_test, y_pred)
            
            logging.info(f"Test Set RMSE: {rmse:.3f}")
            logging.info(f"Test Set R2: {r2:.3f}")
            mlflow.log_metric("test_rmse", rmse)
            mlflow.log_metric("test_r2", r2)

            # Log model and artifacts
            logging.info("Logging model and artifacts to MLflow...")
            model_info = mlflow.xgboost.log_model(
                xgb_model=self.model,
                artifact_path="model",
                registered_model_name=MODEL_NAME
            )

            # Save and log scaler and encoders
            joblib.dump(self.scaler, "scaler.pkl")
            joblib.dump(self.label_encoders, "label_encoders.pkl")
            mlflow.log_artifact("scaler.pkl")
            mlflow.log_artifact("label_encoders.pkl")

            # Transition model to Production
            logging.info(f"Transitioning model version {model_info.version} to Production...")
            client = mlflow.tracking.MlflowClient()
            client.transition_model_version_stage(
                name=MODEL_NAME,
                version=model_info.version,
                stage="Production"
            )
            logging.info("Model successfully transitioned to Production.")
            logging.info("Model training completed successfully.")


if __name__ == "__main__":
    DB_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/agriintel360")
    MLFLOW_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    
    logging.info(f"Connecting to Database: {DB_URL}")
    logging.info(f"Connecting to MLflow: {MLFLOW_URI}")
    
    mlflow.set_tracking_uri(MLFLOW_URI)
    
    model_pipeline = YieldPredictionModel(db_url=DB_URL)
    training_data = model_pipeline.fetch_data()
    
    if not training_data.empty:
        model_pipeline.train(training_data)
    else:
        logging.error("Training aborted due to lack of data.")
