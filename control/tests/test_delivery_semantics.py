"""Tests for at-least-once delivery semantics.

These test the replay pipeline contracts:
- Replayer dedup: exists -> apply -> mark_processed
- Worker checkpoint: only advances on success or confirmed duplicate
- Worker retries: bounded retries before job failure
"""
import importlib.util
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.replay_job import ReplayJob, JobStatus
from app.services.replay_router import ReplayEvent

# ---------------------------------------------------------------------------
# Load replayer module directly (replayer/ is not a Python package).
# ---------------------------------------------------------------------------

_replayer_path = Path(__file__).resolve().parents[2] / "replayer" / "server.py"
_HAS_REPLAYER = False
try:
    _spec = importlib.util.spec_from_file_location("replayer_server", _replayer_path)
    _replayer_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_replayer_mod)
    _ReplayerService = _replayer_mod.ReplayerService
    _TargetApplier = _replayer_mod.TargetApplier
    _AsyncDedupStore = _replayer_mod.AsyncDedupStore
    _HAS_REPLAYER = True
except Exception:
    pass

# Proto types for replayer tests
_HAS_PROTO = False
try:
    from walstream_proto.v1 import ChangeRecord, ReplayRequest
    if not isinstance(ChangeRecord, MagicMock):
        _HAS_PROTO = True
except Exception:
    pass


# ---------------------------------------------------------------------------
# Replayer dedup semantics (unit-level)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_HAS_REPLAYER and _HAS_PROTO),
    reason="replayer deps or proto not available",
)
class TestReplayerDedupSemantics:
    """Verify the replayer's exists -> apply -> mark_processed flow."""

    @pytest.mark.asyncio
    async def test_new_event_applied_then_marked(self):
        """Non-duplicate event: exists=False -> apply -> mark_processed."""
        dedup = AsyncMock(spec=_AsyncDedupStore)
        dedup.exists.return_value = False

        target = AsyncMock(spec=_TargetApplier)
        target.apply.return_value = True

        service = _ReplayerService(target, dedup)
        event = ChangeRecord(
            lsn="0/100", commit_time=1000, table="public.t",
            operation="INSERT", new={"id": "1"},
        )
        request = ReplayRequest(job_id="job-1", event=event)

        response = await service.ReplayEvent(request, MagicMock())

        assert response.success is True
        assert response.was_duplicate is False
        dedup.exists.assert_called_once()
        target.apply.assert_called_once()
        dedup.mark_processed.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_event_not_applied(self):
        """Duplicate event: exists=True -> skip apply, no mark."""
        dedup = AsyncMock(spec=_AsyncDedupStore)
        dedup.exists.return_value = True

        target = AsyncMock(spec=_TargetApplier)

        service = _ReplayerService(target, dedup)
        event = ChangeRecord(
            lsn="0/200", commit_time=2000, table="public.t",
            operation="INSERT", new={"id": "2"},
        )
        request = ReplayRequest(job_id="job-1", event=event)

        response = await service.ReplayEvent(request, MagicMock())

        assert response.success is True
        assert response.was_duplicate is True
        target.apply.assert_not_called()
        dedup.mark_processed.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_apply_not_marked(self):
        """If apply fails, the event must NOT be marked as processed."""
        dedup = AsyncMock(spec=_AsyncDedupStore)
        dedup.exists.return_value = False

        target = AsyncMock(spec=_TargetApplier)
        target.apply.return_value = False

        service = _ReplayerService(target, dedup)
        event = ChangeRecord(
            lsn="0/300", commit_time=3000, table="public.t",
            operation="INSERT", new={"id": "3"},
        )
        request = ReplayRequest(job_id="job-1", event=event)

        response = await service.ReplayEvent(request, MagicMock())

        assert response.success is False
        assert response.was_duplicate is False
        dedup.mark_processed.assert_not_called()


# ---------------------------------------------------------------------------
# Worker checkpoint semantics
# ---------------------------------------------------------------------------


class TestWorkerCheckpointAdvancement:
    """Verify the worker only advances checkpoint on success."""

    def test_checkpoint_advances_on_success(self):
        """After successful replay, last_processed_id is updated."""
        from app.workers.job_worker import JobWorker

        job = ReplayJob(
            id=uuid4(),
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            speed_factor=1.0,
            status=JobStatus.RUNNING,
        )
        source = MagicMock()
        source.source_name.return_value = "redis"

        JobWorker._update_checkpoint(job, "12345-0", source)
        assert job.last_processed_id == "12345-0"

    def test_kafka_checkpoint_stored_per_partition(self):
        """Kafka events store checkpoint in JSON keyed by partition."""
        from app.workers.job_worker import JobWorker

        job = ReplayJob(
            id=uuid4(),
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            speed_factor=1.0,
            status=JobStatus.RUNNING,
            checkpoint={},
        )
        source = MagicMock()
        source.source_name.return_value = "kafka"

        JobWorker._update_checkpoint(job, "0:100", source)
        assert job.checkpoint == {"0": 100}
        assert job.last_processed_id == "0:100"

        # Second partition
        JobWorker._update_checkpoint(job, "1:200", source)
        assert job.checkpoint == {"0": 100, "1": 200}

    def test_kafka_checkpoint_updates_same_partition(self):
        """Later offset on same partition overwrites earlier."""
        from app.workers.job_worker import JobWorker

        job = ReplayJob(
            id=uuid4(),
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            speed_factor=1.0,
            status=JobStatus.RUNNING,
            checkpoint={"0": 50},
        )
        source = MagicMock()
        source.source_name.return_value = "kafka"

        JobWorker._update_checkpoint(job, "0:100", source)
        assert job.checkpoint["0"] == 100

    @pytest.mark.asyncio
    async def test_acquire_query_includes_expired_running_jobs(self):
        """Worker acquisition should reclaim RUNNING jobs with expired lease."""
        from app.workers.job_worker import JobWorker

        class _Result:
            def scalar_one_or_none(self):
                return None

        class _FakeDB:
            def __init__(self):
                self.statements = []

            async def execute(self, stmt):
                self.statements.append(stmt)
                return _Result()

            async def commit(self):
                return None

        fake_db = _FakeDB()

        @asynccontextmanager
        async def fake_db_context():
            yield fake_db

        worker = JobWorker.__new__(JobWorker)
        worker.worker_id = "worker-test"
        worker.current_job_id = None

        with patch("app.workers.job_worker.get_db_context", fake_db_context):
            result = await JobWorker._acquire_job(worker)

        assert result is None
        sql = str(fake_db.statements[0])
        assert "replay_jobs.status = :status_1" in sql
        assert "replay_jobs.status = :status_2" in sql
        assert "replay_jobs.lease_expires_at <" in sql


# ---------------------------------------------------------------------------
# Worker retry semantics
# ---------------------------------------------------------------------------


class TestWorkerRetries:
    """Verify bounded retries before job failure."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self):
        """If first attempt fails and second succeeds, return success."""
        from app.workers.job_worker import JobWorker

        worker = JobWorker.__new__(JobWorker)

        call_count = 0

        async def mock_replay(job, event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return False, False
            return True, False

        worker._replay_event = mock_replay

        job = MagicMock()
        event = ReplayEvent(
            message_id="0:1", payload=b"", commit_time_ms=1000,
            table="t", operation="INSERT",
        )

        with patch("app.workers.job_worker.settings") as mock_settings:
            mock_settings.max_event_retries = 3
            success, was_dup, attempts = await worker._replay_event_with_retries(job, event)

        assert success is True
        assert was_dup is False
        assert attempts == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_failure(self):
        """All retries fail -> return failure with total attempts."""
        from app.workers.job_worker import JobWorker

        worker = JobWorker.__new__(JobWorker)

        async def always_fail(job, event):
            return False, False

        worker._replay_event = always_fail

        job = MagicMock()
        event = ReplayEvent(
            message_id="0:1", payload=b"", commit_time_ms=1000,
            table="t", operation="INSERT",
        )

        with patch("app.workers.job_worker.settings") as mock_settings:
            mock_settings.max_event_retries = 2
            success, was_dup, attempts = await worker._replay_event_with_retries(job, event)

        assert success is False
        assert was_dup is False
        assert attempts == 3

    @pytest.mark.asyncio
    async def test_duplicate_skips_retry(self):
        """Duplicate detection on first attempt skips retries."""
        from app.workers.job_worker import JobWorker

        worker = JobWorker.__new__(JobWorker)

        async def return_dup(job, event):
            return True, True

        worker._replay_event = return_dup

        job = MagicMock()
        event = ReplayEvent(
            message_id="0:1", payload=b"", commit_time_ms=1000,
            table="t", operation="INSERT",
        )

        with patch("app.workers.job_worker.settings") as mock_settings:
            mock_settings.max_event_retries = 3
            success, was_dup, attempts = await worker._replay_event_with_retries(job, event)

        assert success is True
        assert was_dup is True
        assert attempts == 1
