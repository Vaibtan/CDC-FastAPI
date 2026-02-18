"""User model for authentication and RBAC."""
from datetime import datetime
from enum import Enum as PyEnum
from uuid import uuid4

from sqlalchemy import Column, DateTime, Enum, String, Boolean
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class UserRole(str, PyEnum):
    """User role hierarchy: admin > operator > viewer."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


# Role hierarchy — higher index = more privilege
_ROLE_RANK = {UserRole.VIEWER: 0, UserRole.OPERATOR: 1, UserRole.ADMIN: 2}


def role_at_least(user_role: "UserRole", minimum: "UserRole") -> bool:
    """Return True if *user_role* meets or exceeds *minimum*."""
    return _ROLE_RANK.get(user_role, -1) >= _ROLE_RANK[minimum]


class User(Base):
    """User model for API authentication."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    role = Column(
        Enum(UserRole), nullable=False, server_default="viewer", default=UserRole.VIEWER
    )
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
