"""
Schemas for alerts
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid

class AlertBase(BaseModel):
    title: str
    message: str
    alert_type: str
    severity: str
    country_id: Optional[uuid.UUID] = None
    crop_id: Optional[uuid.UUID] = None

class AlertCreate(AlertBase):
    pass

class AlertResponse(AlertBase):
    id: uuid.UUID
    created_at: datetime
    is_read: bool

    class Config:
        from_attributes = True
