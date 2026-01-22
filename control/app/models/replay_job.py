"""SQLAlchemy models for replay jobs with durable execution."""
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    Index,
    CheckConstraint,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class JobStatus(str, PyEnum):
    """Replay job status values."""

    PENDING = "pending"
    QUEUED = "queued"  # In job queue, waiting for worker
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplayJob(Base):
    """Replay job with durable execution support."""

    __tablename__ = "replay_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Time range for replay
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    # Configuration
    speed_factor = Column(Float, default=1.0, nullable=False)
    target_type = Column(String(20), default="grpc")
    target_url = Column(String(255), nullable=True)
    table_filter = Column(String(255), nullable=True)

    # Status
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    events_total = Column(Integer, default=0)
    events_processed = Column(Integer, default=0)
    events_failed = Column(Integer, default=0)
    events_skipped_dedup = Column(Integer, default=0)

    # Replay source (determined at runtime)
    replay_source = Column(String(20), nullable=True)  # "redis" or "kafka"

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_count = Column(Integer, default=0)

    # Checkpoint for resumability (per-partition JSON for Kafka)
    checkpoint = Column(JSON, nullable=True)  # {"0": 1234, "1": 5678}
    last_processed_id = Column(String(255), nullable=True)  # Redis ID or formatted offset
    last_processed_time = Column(DateTime(timezone=True), nullable=True)

    # Worker lease (for durable execution)
    worker_id = Column(String(100), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by = Column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_replay_jobs_status", "status"),
        Index("idx_replay_jobs_lease", "status", "lease_expires_at"),
        Index("idx_replay_jobs_created", "created_at"),
        CheckConstraint("end_time > start_time", name="check_time_range"),
        CheckConstraint("speed_factor > 0", name="check_speed_factor"),
    )

    @property
    def progress_percent(self) -> float:
        """Calculate completion percentage."""
        if self.events_total > 0:
            return round((self.events_processed / self.events_total) * 100, 2)
        return 0.0

    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        )
