"""Add user role column and audit_logs table.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-17 00:02:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- User role ---
    user_role_enum = postgresql.ENUM(
        "admin", "operator", "viewer", name="userrole", create_type=True,
    )
    user_role_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column("role", user_role_enum, nullable=False, server_default="viewer"),
    )

    # --- Audit logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("method", sa.String(10), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("status_code", sa.String(3), nullable=True),
    )

    op.create_index("idx_audit_logs_timestamp", "audit_logs", ["timestamp"])
    op.create_index("idx_audit_logs_user", "audit_logs", ["username"])
    op.create_index("idx_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_column("users", "role")
    op.execute("DROP TYPE IF EXISTS userrole")
