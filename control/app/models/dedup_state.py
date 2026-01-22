"""Deduplication state storage for idempotency."""
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Index

from app.database import Base


class ProcessedEvent(Base):
    """Tracks processed events for idempotency enforcement."""

    __tablename__ = "processed_events"
    __table_args__ = (
        Index("idx_processed_events_expires", "expires_at"),
        Index("idx_processed_events_job", "job_id"),
        {"schema": "walstream_dedup"},
    )

    idempotency_key = Column(String(255), primary_key=True)
    processed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    job_id = Column(String(36), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
