"""
AgriIntel360 - Main ETL Pipeline
DAG for collecting, transforming, and loading agricultural data.
"""

import pandas as pd
import requests
import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable

from pipeline.config import (
    FAO_COUNTRY_CODES,
    OPENWEATHER_CAPITALS,
    WORLD_BANK_INDICATORS,
    FAO_API_URLS
)
from pipeline.validation.schemas import (
    FAOProductionRecord,
    WeatherRecord,
    WorldBankRecord
)
from pydantic import ValidationError

from pipeline.dags.malabo_aggregation import aggregate_malabo_indicators

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- DAG Configuration ---
default_args = {
    'owner': 'agriintel360',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'agri_data_pipeline',
    default_args=default_args,
    description='Complete agricultural data pipeline for AgriIntel360',
    schedule_interval='@daily',
    catchup=False,
    max_active_runs=1,
)

# --- Airflow Variables & Connections ---
DATABASE_URL = Variable.get("DATABASE_URL", default_var="postgresql://admin:password@postgres:5432/agriintel360")
FAO_API_KEY = Variable.get("FAO_API_KEY", default_var=None)
OPENWEATHER_API_KEY = Variable.get("OPENWEATHER_API_KEY", default_var=None)


# --- Extraction Tasks ---

def extract_fao_data(**context):
    """Extracts agricultural data from FAOSTAT."""
    logger.info("🌾 Starting FAO data extraction...")
    
    extracted_data = {}
    country_codes_str = ','.join(map(str, FAO_COUNTRY_CODES.values()))
    current_year = datetime.now().year
    
    for data_type, url in FAO_API_URLS.items():
        try:
            params = {
                'area': country_codes_str,
                'year': f'{current_year-5}:{current_year}',
                'format': 'json',
                'page_size': 2000
            }
            if FAO_API_KEY:
                params['api_key'] = FAO_API_KEY
            
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()
            
            data = response.json().get('data', [])
            extracted_data[data_type] = data
            logger.info(f"  ✅ Success: Extracted {len(data)} records for '{data_type}'.")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"  ❌ HTTP Error extracting FAO '{data_type}': {e}")
            extracted_data[data_type] = []
        except Exception as e:
            logger.error(f"  ❌ General Error extracting FAO '{data_type}': {e}")
            extracted_data[data_type] = []
            
    context['task_instance'].xcom_push(key='fao_data', value=extracted_data)
    return True

def extract_weather_data(**context):
    """Extracts weather data from OpenWeatherMap or generates mock data."""
    logger.info("🌤️ Starting weather data extraction...")
    weather_data = []

    if not OPENWEATHER_API_KEY:
        logger.warning("  ⚠️ OPENWEATHER_API_KEY not found. Generating mock weather data.")
        for city, coords in OPENWEATHER_CAPITALS.items():
            weather_data.append({
                'city': city, 'country': coords['country'],
                'temperature': 28 + (hash(city) % 5), 'humidity': 70 + (hash(city) % 20),
                'precipitation': (hash(city) % 50) / 10, 'date': datetime.now().date(),
                'lat': coords['lat'], 'lon': coords['lon']
            })
    else:
        for city, coords in OPENWEATHER_CAPITALS.items():
            try:
                params = {
                    'lat': coords['lat'], 'lon': coords['lon'],
                    'appid': OPENWEATHER_API_KEY, 'units': 'metric'
                }
                response = requests.get("http://api.openweathermap.org/data/2.5/weather", params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                weather_data.append({
                    'city': city, 'country': coords['country'],
                    'temperature': data['main']['temp'], 'humidity': data['main']['humidity'],
                    'precipitation': data.get('rain', {}).get('1h', 0),
                    'date': datetime.now().date(), 'lat': coords['lat'], 'lon': coords['lon']
                })
            except requests.exceptions.RequestException as e:
                logger.error(f"  ❌ HTTP Error for weather in {city}: {e}")
            except Exception as e:
                logger.error(f"  ❌ General Error for weather in {city}: {e}")

    logger.info(f"  ✅ Extracted {len(weather_data)} weather records.")
    context['task_instance'].xcom_push(key='weather_data', value=weather_data)
    return True

def extract_world_bank_data(**context):
    """Extracts economic data from the World Bank."""
    logger.info("🏛️ Starting World Bank data extraction...")
    wb_data = []
    country_iso_codes = ';'.join(FAO_COUNTRY_CODES.keys())
    current_year = datetime.now().year

    for code, name in WORLD_BANK_INDICATORS.items():
        try:
            url = f"http://api.worldbank.org/v2/country/{country_iso_codes}/indicator/{code}"
            params = {
                'format': 'json', 'date': f'{current_year-10}:{current_year}', 'per_page': 1000
            }
            response = requests.get(url, params=params, timeout=45)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and len(data) > 1:
                for item in data[1]:
                    if item.get('value') is not None:
                        wb_data.append({
                            'country_code': item['country']['id'], 'country_name': item['country']['value'],
                            'indicator': name, 'year': item['date'], 'value': item['value']
                        })
        except requests.exceptions.RequestException as e:
            logger.error(f"  ❌ HTTP Error for World Bank indicator {name}: {e}")
        except Exception as e:
            logger.error(f"  ❌ General Error for World Bank indicator {name}: {e}")

    logger.info(f"  ✅ Extracted {len(wb_data)} World Bank records.")
    context['task_instance'].xcom_push(key='wb_data', value=wb_data)
    return True

# --- Transformation & Validation Task ---

def transform_and_validate_data(**context):
    """Transforms and validates the extracted data using Pydantic models."""
    logger.info("🔄 Starting data transformation and validation...")
    
    fao_data = context['task_instance'].xcom_pull(key='fao_data', task_ids='extract_fao_data') or {}
    weather_data = context['task_instance'].xcom_pull(key='weather_data', task_ids='extract_weather_data') or []
    wb_data = context['task_instance'].xcom_pull(key='wb_data', task_ids='extract_world_bank_data') or []

    validated_data = {'production': [], 'weather': [], 'economic': []}

    # Validate and transform FAO data
    if fao_data.get('production_crops'):
        for record in fao_data['production_crops']:
            try:
                validated_record = FAOProductionRecord.model_validate(record).model_dump()
                validated_data['production'].append(validated_record)
            except ValidationError as e:
                logger.warning(f"  ⚠️ FAO validation error: {e.errors()}")
        df_prod = pd.DataFrame(validated_data['production'])
        logger.info(f"  ✅ Validated and transformed {len(df_prod)} production records.")
        context['task_instance'].xcom_push(key='production_df', value=df_prod.to_json())

    # Validate and transform Weather data
    if weather_data:
        for record in weather_data:
            try:
                validated_record = WeatherRecord.model_validate(record).model_dump()
                validated_data['weather'].append(validated_record)
            except ValidationError as e:
                logger.warning(f"  ⚠️ Weather validation error: {e.errors()}")
        df_weather = pd.DataFrame(validated_data['weather'])
        logger.info(f"  ✅ Validated and transformed {len(df_weather)} weather records.")
        context['task_instance'].xcom_push(key='weather_df', value=df_weather.to_json())

    # Validate and transform World Bank data
    if wb_data:
        for record in wb_data:
            try:
                validated_record = WorldBankRecord.model_validate(record).model_dump()
                validated_data['economic'].append(validated_record)
            except ValidationError as e:
                logger.warning(f"  ⚠️ World Bank validation error: {e.errors()}")
        df_economic = pd.DataFrame(validated_data['economic'])
        logger.info(f"  ✅ Validated and transformed {len(df_economic)} economic records.")
        context['task_instance'].xcom_push(key='economic_df', value=df_economic.to_json())

    return True

# --- Loading Task ---

def load_data_to_staging(**context):
    """Loads transformed data into staging tables in PostgreSQL."""
    logger.info("💾 Starting data loading to staging tables...")
    engine = create_engine(DATABASE_URL)
    
    ti = context['task_instance']
    datasets = {
        'staging_production': ti.xcom_pull(key='production_df', task_ids='transform_and_validate_data'),
        'staging_weather': ti.xcom_pull(key='weather_df', task_ids='transform_and_validate_data'),
        'staging_economic': ti.xcom_pull(key='economic_df', task_ids='transform_and_validate_data'),
    }

    for table_name, json_data in datasets.items():
        if json_data:
            try:
                df = pd.read_json(json_data)
                df.to_sql(table_name, engine, if_exists='append', index=False)
                logger.info(f"  ✅ Successfully loaded {len(df)} records into '{table_name}'.")
            except Exception as e:
                logger.error(f"  ❌ Error loading data into '{table_name}': {e}", exc_info=True)
                # Depending on requirements, you might want to fail the task here
    
    return True

# --- ML Task ---

def run_ml_predictions(**context):
    """Executes ML prediction models (simulation)."""
    logger.info("🤖 Running ML predictions...")
    # This is a placeholder for a real ML model execution task.
    # In a real pipeline, this would trigger a separate ML pipeline or script.
    logger.info("  ✅ ML predictions simulated successfully.")
    return True


# --- Task Definitions ---

extract_fao_task = PythonOperator(
    task_id='extract_fao_data',
    python_callable=extract_fao_data,
    dag=dag,
)

extract_weather_task = PythonOperator(
    task_id='extract_weather_data',
    python_callable=extract_weather_data,
    dag=dag,
)

extract_wb_task = PythonOperator(
    task_id='extract_world_bank_data',
    python_callable=extract_world_bank_data,
    dag=dag,
)

transform_task = PythonOperator(
    task_id='transform_and_validate_data',
    python_callable=transform_and_validate_data,
    dag=dag,
)

load_task = PythonOperator(
    task_id='load_data_to_staging',
    python_callable=load_data_to_staging,
    dag=dag,
)

ml_predictions_task = PythonOperator(
    task_id='run_ml_predictions',
    python_callable=run_ml_predictions,
    dag=dag,
)

malabo_aggregation_task = PythonOperator(
    task_id='aggregate_malabo_indicators',
    python_callable=aggregate_malabo_indicators,
    dag=dag,
)

# --- DAG Dependencies ---
[extract_fao_task, extract_weather_task, extract_wb_task] >> transform_task >> load_task >> malabo_aggregation_task >> ml_predictions_task
