"""
Pydantic schemas for Price Alerts
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PriceAlertBase(BaseModel):
    crop: str = Field(..., min_length=1, max_length=100, description="Crop name (e.g. maïs, cacao)")
    market: str = Field(..., min_length=1, max_length=200, description="Market or city name")
    condition: str = Field(..., pattern="^(above|below)$")
    threshold: float = Field(..., gt=0, description="Threshold price value")
    currency: str = Field(default="FCFA", max_length=10)


class PriceAlertCreate(PriceAlertBase):
    pass


class PriceAlertUpdate(BaseModel):
    crop: Optional[str] = Field(None, min_length=1, max_length=100)
    market: Optional[str] = Field(None, min_length=1, max_length=200)
    condition: Optional[str] = Field(None, pattern="^(above|below)$")
    threshold: Optional[float] = Field(None, gt=0)
    currency: Optional[str] = Field(None, max_length=10)
    is_active: Optional[bool] = None


class PriceAlertResponse(PriceAlertBase):
    id: UUID
    user_id: UUID
    is_active: bool
    last_triggered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PriceAlertCheckResult(BaseModel):
    alert_id: UUID
    crop: str
    market: str
    condition: str
    threshold: float
    current_price: Optional[float] = None
    triggered: bool
    message: str
