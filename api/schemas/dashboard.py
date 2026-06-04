"""
Dashboard Pydantic schemas
"""

from typing import List, Optional
from pydantic import BaseModel

class KPIStats(BaseModel):
    total_production: float
    price_index: float
    weather_alerts: int
    countries_monitored: int
    active_farmers: Optional[int] = 0
    hectares: Optional[float] = 0

class ProductionDataPoint(BaseModel):
    country: str
    crop: str
    production: float
    year: int
    change: Optional[float] = None
