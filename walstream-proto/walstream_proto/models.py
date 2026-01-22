"""Pydantic models for type-safe Python usage and REST API schemas."""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, computed_field


class Operation(str, Enum):
    """Database operation types captured by CDC."""

    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    TRUNCATE = "TRUNCATE"


class ChangeRecordModel(BaseModel):
    """Pydantic representation of ChangeRecord protobuf."""

    lsn: str = Field(description="Log Sequence Number from PostgreSQL")
    commit_time: int = Field(description="Unix timestamp in milliseconds")
    table: str = Field(description="Fully qualified table name (schema.table)")
    operation: Operation = Field(description="Type of database operation")
    old: dict[str, str] = Field(
        default_factory=dict, description="Previous row values (UPDATE/DELETE)"
    )
    new: dict[str, str] = Field(
        default_factory=dict, description="New row values (INSERT/UPDATE)"
    )

    @classmethod
    def from_protobuf(cls, pb) -> "ChangeRecordModel":
        """Create model from protobuf message."""
        return cls(
            lsn=pb.lsn,
            commit_time=pb.commit_time,
            table=pb.table,
            operation=Operation(pb.operation) if pb.operation else Operation.INSERT,
            old=dict(pb.old),
            new=dict(pb.new),
        )

    def to_protobuf(self):
        """Convert model to protobuf message."""
        from walstream_proto.v1 import ChangeRecord

        return ChangeRecord(
            lsn=self.lsn,
            commit_time=self.commit_time,
            table=self.table,
            operation=self.operation.value,
            old=self.old,
            new=self.new,
        )

    def idempotency_key(self, primary_key_fields: list[str] | None = None) -> str:
        """
        Generate idempotency key for deduplication.

        Format: {lsn}:{table}:{primary_key_values}
        """
        # Use 'new' for INSERT/UPDATE, 'old' for DELETE
        data = self.new if self.operation != Operation.DELETE else self.old

        if primary_key_fields:
            pk_values = ":".join(str(data.get(f, "")) for f in primary_key_fields)
        else:
            # Fallback: hash all values for deterministic key
            pk_values = str(hash(frozenset(data.items())))

        return f"{self.lsn}:{self.table}:{pk_values}"


class JobStatus(str, Enum):
    """Replay job status values."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplayJobCreate(BaseModel):
    """Schema for creating a new replay job."""

    start_time: datetime = Field(description="Start of the replay time window")
    end_time: datetime = Field(description="End of the replay time window")
    speed_factor: float = Field(
        default=1.0,
        ge=0.1,
        le=100.0,
        description="Speed multiplier for replay (0.1x to 100x)",
    )
    target_type: str = Field(
        default="grpc",
        pattern="^(grpc|http)$",
        description="Target type: grpc or http",
    )
    target_url: Optional[str] = Field(
        default=None, description="Custom target URL (optional)"
    )
    table_filter: Optional[str] = Field(
        default=None, description="Filter events by table pattern (e.g., 'public.users')"
    )

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v: datetime, info) -> datetime:
        """Ensure end_time is after start_time."""
        if info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class ReplayJobUpdate(BaseModel):
    """Schema for updating a replay job."""

    status: Optional[JobStatus] = Field(
        default=None, description="New status (for pause/resume/cancel)"
    )
    speed_factor: Optional[float] = Field(
        default=None,
        ge=0.1,
        le=100.0,
        description="Updated speed factor",
    )


class ReplayJobResponse(BaseModel):
    """Schema for replay job API responses."""

    id: UUID
    start_time: datetime
    end_time: datetime
    speed_factor: float
    target_type: str
    target_url: Optional[str]
    status: JobStatus
    events_total: int
    events_processed: int
    events_failed: int
    events_skipped_dedup: int = 0
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    replay_source: Optional[str] = Field(
        default=None, description="Source used: 'redis' or 'kafka'"
    )
    created_by: Optional[str] = None

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def progress_percent(self) -> float:
        """Calculate completion percentage."""
        if self.events_total > 0:
            return round((self.events_processed / self.events_total) * 100, 2)
        return 0.0

    @computed_field
    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        )


class ReplayJobListResponse(BaseModel):
    """Schema for paginated job list responses."""

    items: list[ReplayJobResponse]
    total: int
    page: int
    page_size: int
    pages: int


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(description="Overall status: healthy or unhealthy")
    version: str = Field(description="Application version")
    components: dict[str, str] = Field(
        default_factory=dict, description="Component status map"
    )


class EventStreamMessage(BaseModel):
    """WebSocket event stream message."""

    event_type: str = Field(description="Type: change_event, job_update, heartbeat")
    payload: dict = Field(description="Event-specific payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
