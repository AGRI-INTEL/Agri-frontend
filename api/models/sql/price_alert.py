"""
Price Alert SQL Model
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, String, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.models.sql.base import Base


class PriceAlertCondition(str, enum.Enum):
    ABOVE = "above"
    BELOW = "below"


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    crop = Column(String(100), nullable=False)
    market = Column(String(200), nullable=False)
    condition = Column(Enum(PriceAlertCondition, native_enum=False), nullable=False)
    threshold = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="FCFA")
    is_active = Column(Boolean, nullable=False, default=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", backref="price_alerts")

    __table_args__ = (
        Index("ix_price_alerts_user_id", "user_id"),
        Index("ix_price_alerts_crop", "crop"),
        Index("ix_price_alerts_active", "is_active"),
    )

    def __repr__(self):
        return f"<PriceAlert {self.crop} {self.condition} {self.threshold}>"
