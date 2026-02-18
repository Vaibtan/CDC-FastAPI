"""Integration-style tests for job lifecycle through the API.

These use the FastAPI test client with mocked DB + auth so they exercise
the full route → service → model path without external services.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models.replay_job import ReplayJob, JobStatus


def _make_payload(
    hours_ago: int = 2,
    speed: float = 1.0,
) -> dict:
    """Build a valid ReplayJobCreate payload."""
    now = datetime.utcnow()
    return {
        "start_time": (now - timedelta(hours=hours_ago)).isoformat(),
        "end_time": now.isoformat(),
        "speed_factor": speed,
    }


class TestJobCRUD:
    """Create, list, get, update, delete flow."""

    @pytest.mark.asyncio
    async def test_create_and_get(self, client: AsyncClient):
        # Create
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        assert resp.status_code == 201
        job = resp.json()
        job_id = job["id"]
        assert job["status"] == "pending"
        assert job["speed_factor"] == 1.0

        # Get by ID
        resp = await client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == job_id

    @pytest.mark.asyncio
    async def test_list_jobs(self, client: AsyncClient):
        resp = await client.get("/api/v1/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_update_speed_factor(self, client: AsyncClient):
        # Create
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        job_id = resp.json()["id"]

        # Update speed
        resp = await client.patch(
            f"/api/v1/jobs/{job_id}",
            json={"speed_factor": 5.0},
        )
        assert resp.status_code == 200
        assert resp.json()["speed_factor"] == 5.0

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client: AsyncClient):
        fake_id = str(uuid4())
        resp = await client.get(f"/api/v1/jobs/{fake_id}")
        assert resp.status_code == 404


class TestJobLifecycleTransitions:
    """Test the full state machine via API endpoints."""

    @pytest.mark.asyncio
    async def test_pending_start_pause_resume_cancel(self, client: AsyncClient):
        """PENDING -> QUEUED -> (can't pause because not RUNNING)."""
        # Create
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        job_id = resp.json()["id"]

        # Start (PENDING -> QUEUED)
        resp = await client.post(f"/api/v1/jobs/{job_id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

        # Cancel (QUEUED -> CANCELLED)
        resp = await client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cannot_start_non_pending(self, client: AsyncClient):
        """Start on a non-PENDING job should fail."""
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        job_id = resp.json()["id"]

        # Start
        await client.post(f"/api/v1/jobs/{job_id}/start")

        # Try start again (job is now QUEUED)
        resp = await client.post(f"/api/v1/jobs/{job_id}/start")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_pause_queued(self, client: AsyncClient):
        """Pause requires RUNNING state, not QUEUED."""
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        job_id = resp.json()["id"]
        await client.post(f"/api/v1/jobs/{job_id}/start")  # -> QUEUED

        resp = await client.post(f"/api/v1/jobs/{job_id}/pause")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_resume_non_paused(self, client: AsyncClient):
        """Resume requires PAUSED state."""
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        job_id = resp.json()["id"]

        resp = await client.post(f"/api/v1/jobs/{job_id}/resume")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_cancel_pending(self, client: AsyncClient):
        """Can cancel directly from PENDING."""
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        job_id = resp.json()["id"]

        resp = await client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_double_cancel_fails(self, client: AsyncClient):
        """Cannot cancel an already-cancelled job."""
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        job_id = resp.json()["id"]

        await client.post(f"/api/v1/jobs/{job_id}/cancel")
        resp = await client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_requires_terminal_state(self, client: AsyncClient):
        """Cannot delete a PENDING (non-terminal) job."""
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        job_id = resp.json()["id"]

        resp = await client.delete(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_after_cancel(self, client: AsyncClient):
        """Can delete a cancelled job."""
        resp = await client.post("/api/v1/jobs", json=_make_payload())
        job_id = resp.json()["id"]

        await client.post(f"/api/v1/jobs/{job_id}/cancel")
        resp = await client.delete(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_create_invalid_time_range(self, client: AsyncClient):
        """end_time before start_time should be rejected."""
        now = datetime.utcnow()
        payload = {
            "start_time": now.isoformat(),
            "end_time": (now - timedelta(hours=1)).isoformat(),
        }
        resp = await client.post("/api/v1/jobs", json=payload)
        assert resp.status_code == 422
