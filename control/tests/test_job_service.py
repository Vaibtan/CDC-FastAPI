"""Unit tests for the job service layer."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.replay_job import ReplayJob, JobStatus
from app.services.job_service import (
    _transition_status,
    _VALID_TRANSITIONS,
    create_job,
    start_job,
    pause_job,
    resume_job,
    cancel_job,
    delete_job,
    get_job_or_404,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(
    status: JobStatus = JobStatus.PENDING,
    worker_id: str | None = None,
    lease_expires_at: datetime | None = None,
) -> ReplayJob:
    """Build a ReplayJob instance (not DB-backed)."""
    job = ReplayJob(
        id=uuid4(),
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow(),
        speed_factor=1.0,
        status=status,
        worker_id=worker_id,
        lease_expires_at=lease_expires_at,
    )
    return job


class _FakeSession:
    """Minimal mock of AsyncSession that records flush/delete calls."""

    def __init__(self):
        self.flushed = False
        self.deleted_items = []
        self.added_items = []

    def add(self, item):
        self.added_items.append(item)

    async def flush(self):
        self.flushed = True

    async def delete(self, item):
        self.deleted_items.append(item)


# ---------------------------------------------------------------------------
# _transition_status
# ---------------------------------------------------------------------------


class TestTransitionStatus:
    """Test the internal state machine."""

    @pytest.mark.parametrize(
        "src,dst",
        [
            (JobStatus.PENDING, JobStatus.QUEUED),
            (JobStatus.PENDING, JobStatus.CANCELLED),
            (JobStatus.QUEUED, JobStatus.CANCELLED),
            (JobStatus.RUNNING, JobStatus.PAUSED),
            (JobStatus.RUNNING, JobStatus.CANCELLED),
            (JobStatus.PAUSED, JobStatus.QUEUED),
            (JobStatus.PAUSED, JobStatus.CANCELLED),
        ],
    )
    def test_valid_transitions(self, src, dst):
        """All declared transitions should succeed."""
        job = _make_job(status=src, worker_id="w-1", lease_expires_at=datetime.utcnow())
        _transition_status(job, dst)
        assert job.status == dst

    @pytest.mark.parametrize(
        "src,dst",
        [
            (JobStatus.PENDING, JobStatus.RUNNING),
            (JobStatus.PENDING, JobStatus.COMPLETED),
            (JobStatus.QUEUED, JobStatus.RUNNING),
            (JobStatus.COMPLETED, JobStatus.RUNNING),
            (JobStatus.FAILED, JobStatus.RUNNING),
            (JobStatus.CANCELLED, JobStatus.QUEUED),
        ],
    )
    def test_invalid_transitions_raise(self, src, dst):
        """Invalid transitions raise HTTPException 400."""
        job = _make_job(status=src)
        with pytest.raises(HTTPException) as exc_info:
            _transition_status(job, dst)
        assert exc_info.value.status_code == 400

    def test_paused_clears_lease(self):
        """Transition to PAUSED clears worker_id and lease_expires_at."""
        job = _make_job(
            status=JobStatus.RUNNING,
            worker_id="w-1",
            lease_expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        _transition_status(job, JobStatus.PAUSED)
        assert job.worker_id is None
        assert job.lease_expires_at is None

    def test_cancelled_clears_lease_and_sets_completed_at(self):
        """Transition to CANCELLED clears lease and sets completed_at."""
        job = _make_job(
            status=JobStatus.RUNNING,
            worker_id="w-1",
            lease_expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        _transition_status(job, JobStatus.CANCELLED)
        assert job.worker_id is None
        assert job.lease_expires_at is None
        assert job.completed_at is not None


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


class TestCreateJob:
    @pytest.mark.asyncio
    async def test_creates_pending_job(self):
        db = _FakeSession()
        now = datetime.utcnow()
        job = await create_job(
            db,
            start_time=now - timedelta(hours=1),
            end_time=now,
            speed_factor=2.0,
            created_by="admin",
        )
        assert job.status == JobStatus.PENDING
        assert job.speed_factor == 2.0
        assert job.created_by == "admin"
        assert db.flushed


class TestStartJob:
    @pytest.mark.asyncio
    async def test_pending_to_queued(self):
        db = _FakeSession()
        job = _make_job(status=JobStatus.PENDING)
        result = await start_job(db, job)
        assert result.status == JobStatus.QUEUED

    @pytest.mark.asyncio
    async def test_non_pending_raises(self):
        db = _FakeSession()
        job = _make_job(status=JobStatus.RUNNING)
        with pytest.raises(HTTPException) as exc_info:
            await start_job(db, job)
        assert exc_info.value.status_code == 400


class TestPauseJob:
    @pytest.mark.asyncio
    async def test_running_to_paused(self):
        db = _FakeSession()
        job = _make_job(
            status=JobStatus.RUNNING,
            worker_id="w-1",
            lease_expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        result = await pause_job(db, job)
        assert result.status == JobStatus.PAUSED
        assert result.worker_id is None
        assert result.lease_expires_at is None

    @pytest.mark.asyncio
    async def test_non_running_raises(self):
        db = _FakeSession()
        job = _make_job(status=JobStatus.PENDING)
        with pytest.raises(HTTPException):
            await pause_job(db, job)


class TestResumeJob:
    @pytest.mark.asyncio
    async def test_paused_to_queued(self):
        db = _FakeSession()
        job = _make_job(status=JobStatus.PAUSED)
        result = await resume_job(db, job)
        assert result.status == JobStatus.QUEUED

    @pytest.mark.asyncio
    async def test_non_paused_raises(self):
        db = _FakeSession()
        job = _make_job(status=JobStatus.RUNNING)
        with pytest.raises(HTTPException):
            await resume_job(db, job)


class TestCancelJob:
    @pytest.mark.asyncio
    async def test_cancel_running(self):
        db = _FakeSession()
        job = _make_job(status=JobStatus.RUNNING, worker_id="w-1")
        result = await cancel_job(db, job)
        assert result.status == JobStatus.CANCELLED
        assert result.worker_id is None
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancel_terminal_raises(self):
        db = _FakeSession()
        job = _make_job(status=JobStatus.COMPLETED)
        with pytest.raises(HTTPException) as exc_info:
            await cancel_job(db, job)
        assert exc_info.value.status_code == 400


class TestDeleteJob:
    @pytest.mark.asyncio
    async def test_delete_terminal(self):
        db = _FakeSession()
        job = _make_job(status=JobStatus.COMPLETED)
        await delete_job(db, job)
        assert job in db.deleted_items

    @pytest.mark.asyncio
    async def test_delete_non_terminal_raises(self):
        db = _FakeSession()
        job = _make_job(status=JobStatus.RUNNING)
        with pytest.raises(HTTPException) as exc_info:
            await delete_job(db, job)
        assert exc_info.value.status_code == 400
