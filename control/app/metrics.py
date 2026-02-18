"""Control-plane Prometheus metrics."""
import asyncio
import logging
from datetime import datetime

from prometheus_client import Gauge
from sqlalchemy import func, select

from app.database import get_read_db_context
from app.models.replay_job import ReplayJob, JobStatus

logger = logging.getLogger(__name__)

JOBS_ACTIVE = Gauge(
    "walstream_jobs_active",
    "Number of active replay jobs by state",
    ["state"],
)

JOB_LEASE_EXPIRED = Gauge(
    "walstream_job_lease_expired",
    "Number of running replay jobs with expired lease",
    ["state"],
)

# Initialize known label combinations so the metrics always exist.
JOBS_ACTIVE.labels(state="queued").set(0)
JOBS_ACTIVE.labels(state="running").set(0)
JOB_LEASE_EXPIRED.labels(state="running").set(0)


class JobMetricsPublisher:
    """Background publisher that refreshes job gauges from the database."""

    def __init__(self, refresh_interval_seconds: float = 15.0) -> None:
        self.refresh_interval_seconds = max(1.0, float(refresh_interval_seconds))
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start periodic metric refresh."""
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop periodic metric refresh."""
        if not self._task:
            return
        self._stop_event.set()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await self.refresh_once()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.refresh_interval_seconds,
                )
            except asyncio.TimeoutError:
                continue

    async def refresh_once(self) -> None:
        """Refresh all job-related gauges from the latest DB state."""
        try:
            async with get_read_db_context() as db:
                result = await db.execute(
                    select(ReplayJob.status, func.count(ReplayJob.id))
                    .where(ReplayJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
                    .group_by(ReplayJob.status)
                )

                counts = {"queued": 0, "running": 0}
                for status_value, count_value in result.all():
                    state = (
                        status_value.value
                        if isinstance(status_value, JobStatus)
                        else str(status_value)
                    )
                    if state in counts:
                        counts[state] = int(count_value)

                JOBS_ACTIVE.labels(state="queued").set(counts["queued"])
                JOBS_ACTIVE.labels(state="running").set(counts["running"])

                expired_running = await db.scalar(
                    select(func.count(ReplayJob.id)).where(
                        ReplayJob.status == JobStatus.RUNNING,
                        ReplayJob.lease_expires_at.is_not(None),
                        ReplayJob.lease_expires_at < datetime.utcnow(),
                    )
                )
                JOB_LEASE_EXPIRED.labels(state="running").set(int(expired_running or 0))
        except Exception:
            logger.debug("Failed to refresh job metrics", exc_info=True)
