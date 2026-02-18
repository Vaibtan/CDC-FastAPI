"""Initial schema — users, replay_jobs, processed_events.

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-02-17 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- Replay Jobs ---
    job_status_enum = postgresql.ENUM(
        "pending", "queued", "running", "paused",
        "completed", "failed", "cancelled",
        name="jobstatus",
        create_type=True,
    )

    op.create_table(
        "replay_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Time range
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        # Configuration
        sa.Column("speed_factor", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("target_type", sa.String(20), server_default="grpc"),
        sa.Column("target_url", sa.String(255), nullable=True),
        sa.Column("table_filter", sa.String(255), nullable=True),
        # Status
        sa.Column("status", job_status_enum, nullable=False, server_default="pending"),
        sa.Column("events_total", sa.Integer(), server_default="0"),
        sa.Column("events_processed", sa.Integer(), server_default="0"),
        sa.Column("events_failed", sa.Integer(), server_default="0"),
        sa.Column("events_skipped_dedup", sa.Integer(), server_default="0"),
        # Replay source
        sa.Column("replay_source", sa.String(20), nullable=True),
        # Error tracking
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_count", sa.Integer(), server_default="0"),
        # Checkpoint
        sa.Column("checkpoint", postgresql.JSON(), nullable=True),
        sa.Column("last_processed_id", sa.String(255), nullable=True),
        sa.Column("last_processed_time", sa.DateTime(timezone=True), nullable=True),
        # Worker lease
        sa.Column("worker_id", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Audit
        sa.Column("created_by", sa.String(100), nullable=True),
        # Constraints
        sa.CheckConstraint("end_time > start_time", name="check_time_range"),
        sa.CheckConstraint("speed_factor > 0", name="check_speed_factor"),
    )

    op.create_index("idx_replay_jobs_status", "replay_jobs", ["status"])
    op.create_index("idx_replay_jobs_lease", "replay_jobs", ["status", "lease_expires_at"])
    op.create_index("idx_replay_jobs_created", "replay_jobs", ["created_at"])

    # --- Dedup schema + table ---
    op.execute("CREATE SCHEMA IF NOT EXISTS walstream_dedup")

    op.create_table(
        "processed_events",
        sa.Column("idempotency_key", sa.String(255), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("job_id", sa.String(36), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        schema="walstream_dedup",
    )

    op.create_index(
        "idx_processed_events_expires",
        "processed_events",
        ["expires_at"],
        schema="walstream_dedup",
    )
    op.create_index(
        "idx_processed_events_job",
        "processed_events",
        ["job_id"],
        schema="walstream_dedup",
    )


def downgrade() -> None:
    op.drop_table("processed_events", schema="walstream_dedup")
    op.execute("DROP SCHEMA IF EXISTS walstream_dedup")
    op.drop_table("replay_jobs")
    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.drop_table("users")
