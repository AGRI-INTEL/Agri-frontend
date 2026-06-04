"""
Schemas Pydantic pour les indicateurs agricoles
"""

from typing import Optional, List, Any
from uuid import UUID
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict

class IndicatorBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    sector: str
    unit: str
    value: float
    period: str
    year: int

class IndicatorResponse(IndicatorBase):
    id: str
    last_updated: datetime
    trend: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True)

class IndicatorHistory(BaseModel):
    date: date
    value: float
    period: str
