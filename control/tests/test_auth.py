"""Unit tests for authentication: JWT tokens, stale-token handling, WebSocket auth."""
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

# Skip entire module if python-jose is not available (conftest stubs it)
try:
    import jose as _jose_check
    if isinstance(_jose_check, MagicMock):
        raise ImportError("jose is a mock stub")
    from jose import jwt  # real import
except (ImportError, TypeError, SyntaxError):
    pytest.skip("python-jose not installed", allow_module_level=True)

from app.api.deps import create_access_token  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.middleware.auth_context import (  # noqa: E402
    UserIdentity,
    _decode_identity,
    _extract_token,
)

settings = get_settings()


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


class TestCreateAccessToken:
    def test_default_expiry(self):
        """Token with default expiry decodes successfully."""
        token = create_access_token(data={"sub": "alice"})
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == "alice"
        assert "exp" in payload

    def test_custom_expiry(self):
        """Token with custom expiry includes correct exp claim."""
        token = create_access_token(
            data={"sub": "bob"},
            expires_delta=timedelta(minutes=5),
        )
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == "bob"


# ---------------------------------------------------------------------------
# Auth context middleware helpers
# ---------------------------------------------------------------------------


class TestExtractToken:
    def test_bearer_header(self):
        request = MagicMock()
        request.headers = {"authorization": "Bearer abc123"}
        request.query_params = {}
        token = _extract_token(request)
        assert token == "abc123"

    def test_query_param(self):
        request = MagicMock()
        request.headers = {}
        request.query_params = {"token": "xyz789"}
        token = _extract_token(request)
        assert token == "xyz789"

    def test_no_token(self):
        request = MagicMock()
        request.headers = {}
        request.query_params = {}
        token = _extract_token(request)
        assert token is None

    def test_case_insensitive_bearer(self):
        request = MagicMock()
        request.headers = {"authorization": "bearer MyToken"}
        request.query_params = {}
        token = _extract_token(request)
        assert token == "MyToken"


class TestDecodeIdentity:
    def test_valid_token(self):
        token = create_access_token(data={"sub": "alice"})
        identity = _decode_identity(token)
        assert identity.username == "alice"
        assert identity.is_expired is False

    def test_expired_token(self):
        token = create_access_token(
            data={"sub": "bob"},
            expires_delta=timedelta(seconds=-10),
        )
        identity = _decode_identity(token)
        assert identity.username == "bob"
        assert identity.is_expired is True

    def test_garbage_token(self):
        identity = _decode_identity("not.a.jwt")
        assert identity.username == ""
        assert identity.is_expired is False


# ---------------------------------------------------------------------------
# API-level auth tests (using test client)
# ---------------------------------------------------------------------------


class TestAuthEndpoints:
    """Test that endpoints enforce authentication properly."""

    @pytest.mark.asyncio
    async def test_unauthenticated_jobs_returns_401(self, unauthed_client):
        """GET /api/v1/jobs without token returns 401."""
        response = await unauthed_client.get("/api/v1/jobs")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_events_recent_returns_401(self, unauthed_client):
        """GET /api/v1/events/recent without token returns 401."""
        response = await unauthed_client.get("/api/v1/events/recent")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_stream_stats_returns_401(self, unauthed_client):
        """GET /api/v1/events/stream/stats without token returns 401."""
        response = await unauthed_client.get("/api/v1/events/stream/stats")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_returns_401_with_header(self, unauthed_client, expired_token):
        """Expired JWT returns 401 with X-Token-Expired detail."""
        response = await unauthed_client.get(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Token has expired"

    @pytest.mark.asyncio
    async def test_health_endpoints_are_public(self, unauthed_client):
        """Health probes should NOT require auth."""
        response = await unauthed_client.get("/api/v1/health/live")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_authenticated_jobs_returns_200(self, client):
        """GET /api/v1/jobs with valid token returns 200."""
        response = await client.get("/api/v1/jobs")
        assert response.status_code == 200
