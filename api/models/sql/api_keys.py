"""
API Key SQL Model — persistent, hashed storage
"""

import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.models.sql.base import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    # SHA-256 of the raw key — never stored in plain text
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    # First 12 chars of the raw key for display ("agri_xxxx...")
    key_prefix = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<ApiKey {self.name} ({self.key_prefix}...)>"
