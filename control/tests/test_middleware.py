"""Unit tests for rate-limit and audit middleware."""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.middleware.audit import _derive_action, _extract_resource
from app.middleware.rate_limit import _LUA_SCRIPT


# ---------------------------------------------------------------------------
# Audit: resource extraction from URL path
# ---------------------------------------------------------------------------


class TestExtractResource:
    def test_jobs_collection(self):
        t, i = _extract_resource("/api/v1/jobs")
        assert t == "replay_job"
        assert i is None

    def test_jobs_collection_trailing_slash(self):
        t, i = _extract_resource("/api/v1/jobs/")
        assert t == "replay_job"
        assert i is None

    def test_job_by_id(self):
        t, i = _extract_resource("/api/v1/jobs/abc-123")
        assert t == "replay_job"
        assert i == "abc-123"

    def test_job_action(self):
        t, i = _extract_resource("/api/v1/jobs/abc-123/start")
        assert t == "replay_job"
        assert i == "abc-123"

    def test_auth_register(self):
        t, i = _extract_resource("/api/v1/auth/register")
        assert t == "auth"
        assert i is None

    def test_events(self):
        t, i = _extract_resource("/api/v1/events/stream/stats")
        assert t == "events"
        assert i == "stream"

    def test_root_path(self):
        t, i = _extract_resource("/")
        assert t == "unknown"
        assert i is None


class TestDeriveAction:
    def test_job_create(self):
        action = _derive_action("POST", "/api/v1/jobs", "replay_job", None)
        assert action == "replay_job.create"

    def test_job_lifecycle_action(self):
        action = _derive_action(
            "POST", "/api/v1/jobs/abc-123/cancel", "replay_job", "abc-123"
        )
        assert action == "replay_job.cancel"

    def test_job_update(self):
        action = _derive_action("PATCH", "/api/v1/jobs/abc-123", "replay_job", "abc-123")
        assert action == "replay_job.update"

    def test_job_delete(self):
        action = _derive_action(
            "DELETE", "/api/v1/jobs/abc-123", "replay_job", "abc-123"
        )
        assert action == "replay_job.delete"

    def test_auth_token(self):
        action = _derive_action("POST", "/api/v1/auth/token", "auth", None)
        assert action == "auth.token"


# ---------------------------------------------------------------------------
# Rate limit Lua script correctness
# ---------------------------------------------------------------------------


class TestRateLimitLuaScript:
    """Verify the token-bucket Lua script logic (structure check only).

    The actual Redis execution is tested via integration tests; here we just
    validate the script string is well-formed.
    """

    def test_script_is_non_empty_string(self):
        assert isinstance(_LUA_SCRIPT, str)
        assert len(_LUA_SCRIPT) > 100

    def test_script_returns_allowed_flag(self):
        """Script should return {0|1, remaining}."""
        assert "return {1," in _LUA_SCRIPT
        assert "return {0," in _LUA_SCRIPT

    def test_script_uses_hmget_and_hmset(self):
        """Script should use HMGET/HMSET for bucket state."""
        assert "HMGET" in _LUA_SCRIPT
        assert "HMSET" in _LUA_SCRIPT

    def test_script_sets_expire(self):
        """Script should set an expiry on the bucket key."""
        assert "EXPIRE" in _LUA_SCRIPT
