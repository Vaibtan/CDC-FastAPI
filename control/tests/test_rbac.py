"""Unit tests for RBAC enforcement."""
import pytest

from app.models.user import UserRole, role_at_least


class TestRoleHierarchy:
    """Test role_at_least helper."""

    def test_admin_meets_admin(self):
        assert role_at_least(UserRole.ADMIN, UserRole.ADMIN) is True

    def test_admin_meets_operator(self):
        assert role_at_least(UserRole.ADMIN, UserRole.OPERATOR) is True

    def test_admin_meets_viewer(self):
        assert role_at_least(UserRole.ADMIN, UserRole.VIEWER) is True

    def test_operator_meets_operator(self):
        assert role_at_least(UserRole.OPERATOR, UserRole.OPERATOR) is True

    def test_operator_meets_viewer(self):
        assert role_at_least(UserRole.OPERATOR, UserRole.VIEWER) is True

    def test_operator_not_admin(self):
        assert role_at_least(UserRole.OPERATOR, UserRole.ADMIN) is False

    def test_viewer_meets_viewer(self):
        assert role_at_least(UserRole.VIEWER, UserRole.VIEWER) is True

    def test_viewer_not_operator(self):
        assert role_at_least(UserRole.VIEWER, UserRole.OPERATOR) is False

    def test_viewer_not_admin(self):
        assert role_at_least(UserRole.VIEWER, UserRole.ADMIN) is False
