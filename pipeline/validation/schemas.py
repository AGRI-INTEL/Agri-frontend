"""
Data validation schemas for the ETL pipeline using Pydantic.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date

class FAOProductionRecord(BaseModel):
    country_code: str = Field(alias='Area Code (M49)')
    country_name: str = Field(alias='Area')
    crop_code: int = Field(alias='Item Code')
    crop_name: str = Field(alias='Item')
    year: int = Field(alias='Year')
    value: Optional[float] = Field(alias='Value')
    unit: str = Field(alias='Unit')

class WeatherRecord(BaseModel):
    city: str
    country: str
    temperature: float
    humidity: float
    precipitation: float
    date: date
    lat: float
    lon: float

class WorldBankRecord(BaseModel):
    country_code: str
    country_name: str
    indicator: str
    year: int
    value: float
