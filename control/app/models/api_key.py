"""API key model for service-to-service authentication."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, String, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ApiKey(Base):
    """API key for internal service authentication."""

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    key_hash = Column(String(255), unique=True, nullable=False)
    service_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_api_keys_hash", "key_hash"),
    )
