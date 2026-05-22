"""
Agricultural Data SQL Models for Staging and Indicators with improved validation and indexing
"""

import enum
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import (Boolean, Column, DateTime, Enum, Float, ForeignKey, Index, Integer,
                       String, Table, UniqueConstraint, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.models.sql.base import Base

class UnitType(str, enum.Enum):
    """Unit types for measurements"""
    TONNES = "tonnes"
    HECTARES = "hectares"
    KG_PER_HECTARE = "kg/ha"
    MM = "mm"  # For precipitation
    CELSIUS = "celsius"
    PERCENT = "percent"
    USD = "usd"

class StagingProduction(Base):
    """Staging table for agricultural production data"""
    __tablename__ = "staging_production"

    id = Column(Integer, primary_key=True)
    country_code = Column(String(3), nullable=False, index=True)
    country_name = Column(String(100), nullable=False)
    crop_code = Column(Integer, nullable=False)
    crop_name = Column(String(100), nullable=False)
    year = Column(Integer, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(Enum(UnitType), nullable=False)
    source = Column(String(100), nullable=True)
    metadata_ = Column(JSONB, nullable=True)
    quality_score = Column(Float, default=1.0)
    is_validated = Column(Integer, default=0)  # 0: non validé, 1: validé, -1: rejeté

    __table_args__ = (
        UniqueConstraint('country_code', 'crop_code', 'year', name='uix_production_country_crop_year'),
        Index('ix_production_search', 'country_code', 'crop_name', 'year'),
        {'comment': 'Données de production agricole en attente de validation'}
    )

class StagingWeather(Base):
    """Staging table for weather data with geospatial support"""
    __tablename__ = "staging_weather"

    id = Column(Integer, primary_key=True)
    city = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    precipitation = Column(Float, nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    elevation = Column(Float, nullable=True)
    weather_condition = Column(String(50), nullable=True)
    wind_speed = Column(Float, nullable=True)
    wind_direction = Column(Float, nullable=True)
    pressure = Column(Float, nullable=True)
    source = Column(String(100), nullable=True)
    quality_score = Column(Float, default=1.0)

    __table_args__ = (
        Index('ix_weather_location_date', 'city', 'country', 'date'),
        Index('ix_weather_coords', text('ll_to_earth(lat, lon)'), postgresql_using='gist'),
        {'comment': 'Données météorologiques avec support géospatial'}
    )

class IndicatorType(str, enum.Enum):
    """Types d'indicateurs économiques"""
    GDP = "gdp"
    INFLATION = "inflation"
    AGRICULTURAL_GDP = "agricultural_gdp"
    EMPLOYMENT = "employment"
    EXPORT = "export"
    IMPORT = "import"
    INVESTMENT = "investment"

class StagingEconomic(Base):
    """Staging table for economic indicators"""
    __tablename__ = "staging_economic"

    id = Column(Integer, primary_key=True)
    country_code = Column(String(3), nullable=False, index=True)
    country_name = Column(String(100), nullable=False)
    indicator = Column(Enum(IndicatorType), nullable=False)
    year = Column(Integer, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False)
    source = Column(String(100), nullable=True)
    confidence_interval = Column(JSONB, nullable=True)  # {low: float, high: float}
    is_estimated = Column(Integer, default=0)
    notes = Column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint('country_code', 'indicator', 'year', name='uix_economic_country_indicator_year'),
        Index('ix_economic_search', 'country_code', 'indicator', 'year'),
        {'comment': 'Indicateurs économiques agricoles'}
    )

class MalaboYieldIndicator(Base):
    __tablename__ = 'malabo_yield_indicators'
    id = Column(Integer, primary_key=True, autoincrement=True)
    country_name = Column(String)
    crop_name = Column(String)
    year = Column(Integer)
    production_tonnes = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Country(Base):
    __tablename__ = 'countries'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    code = Column(String(3), nullable=False, unique=True)

class Crop(Base):
    __tablename__ = 'crops'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    code = Column(Integer, nullable=True, unique=True)

class Production(Base):
    __tablename__ = 'production'
    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False, index=True)
    production_tonnes = Column(Float, nullable=False)
    yield_tonnes_per_ha = Column(Float, nullable=True)
    country_id = Column(Integer, ForeignKey('countries.id'), nullable=False)
    crop_id = Column(Integer, ForeignKey('crops.id'), nullable=False)

    country = relationship("Country")
    crop = relationship("Crop")

    __table_args__ = (
        UniqueConstraint('country_id', 'crop_id', 'year', name='uix_production_country_crop_year_final'),
    )

class Alert(Base):
    __tablename__ = 'alerts'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    alert_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    country_id = Column(Integer, ForeignKey('countries.id'), nullable=True)
    crop_id = Column(Integer, ForeignKey('crops.id'), nullable=True)

    user = relationship("User")

    __table_args__ = (
        Index('ix_alert_user_id', 'user_id'),
    )
