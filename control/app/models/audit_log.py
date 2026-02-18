"""Audit log model for tracking mutations."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, JSON, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class AuditLog(Base):
    """Immutable log of user-initiated mutations."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Who
    user_id = Column(UUID(as_uuid=True), nullable=True)
    username = Column(String(100), nullable=True)

    # What
    action = Column(String(50), nullable=False)  # e.g. "job.create", "job.cancel"
    resource_type = Column(String(50), nullable=False)  # e.g. "replay_job"
    resource_id = Column(String(255), nullable=True)

    # Context
    detail = Column(JSON, nullable=True)  # request body / diff snapshot
    ip_address = Column(String(45), nullable=True)

    # HTTP info
    method = Column(String(10), nullable=True)
    path = Column(Text, nullable=True)
    status_code = Column(String(3), nullable=True)

    __table_args__ = (
        Index("idx_audit_logs_timestamp", "timestamp"),
        Index("idx_audit_logs_user", "username"),
        Index("idx_audit_logs_resource", "resource_type", "resource_id"),
    )
