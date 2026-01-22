"""
Durable job worker with lease-based execution.

Features:
- Survives restarts via checkpoint/resume
- Lease-based ownership prevents duplicate execution
- Automatic lease renewal during execution
- Graceful shutdown with checkpoint save
"""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

import grpc
import redis.asyncio as aioredis
from sqlalchemy import select, update, and_

from app.config import get_settings
from app.database import get_db_context
from app.models.replay_job import ReplayJob, JobStatus
from app.services.replay_router import (
    ReplaySourceRouter,
    KafkaReplaySource,
    ReplayEvent,
)
from walstream_proto.v1 import ChangeRecord, ReplayRequest, ReplayerStub

settings = get_settings()
logger = logging.getLogger(__name__)


class JobWorker:
    """
    Durable job worker that processes replay jobs.

    Execution model:
    1. Poll for QUEUED jobs with expired/no lease
    2. Acquire lease (atomic UPDATE ... WHERE)
    3. Execute with periodic lease renewal
    4. Checkpoint progress periodically
    5. On completion/failure, release lease and update status
    """

    def __init__(self, worker_id: Optional[str] = None) -> None:
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.running = False
        self.current_job_id: Optional[str] = None
        self.grpc_channel = None
        self.grpc_stub = None
        self.source_router: Optional[ReplaySourceRouter] = None
        self._redis_client: Optional[aioredis.Redis] = None

    async def start(self) -> None:
        """Start the worker loop."""
        logger.info("Starting job worker: %s", self.worker_id)
        self.running = True

        # Initialize dependencies
        await self._init_dependencies()

        # Start lease renewal task
        renewal_task = asyncio.create_task(self._lease_renewal_loop())

        try:
            while self.running:
                try:
                    job = await self._acquire_job()
                    if job:
                        await self._execute_job(job)
                    else:
                        await asyncio.sleep(settings.job_poll_interval_seconds)
                except Exception as e:
                    logger.error("Worker error: %s", e, exc_info=True)
                    await asyncio.sleep(settings.job_poll_interval_seconds)
        finally:
            renewal_task.cancel()
            try:
                await renewal_task
            except asyncio.CancelledError:
                pass
            await self._cleanup()

    async def stop(self) -> None:
        """Stop the worker gracefully."""
        logger.info("Stopping worker: %s", self.worker_id)
        self.running = False

    async def _init_dependencies(self) -> None:
        """Initialize gRPC and source router (aiokafka for async Kafka)."""
        self._redis_client = aioredis.from_url(settings.redis_url)

        # KafkaReplaySource uses aiokafka internally
        kafka_source = KafkaReplaySource(settings.kafka_broker, settings.kafka_topic)
        self.source_router = ReplaySourceRouter(self._redis_client, kafka_source)

        # gRPC channel to replayer
        target = f"{settings.replayer_host}:{settings.replayer_port}"
        self.grpc_channel = grpc.aio.insecure_channel(target)
        self.grpc_stub = ReplayerStub(self.grpc_channel)

    async def _cleanup(self) -> None:
        """Cleanup resources."""
        if self.source_router:
            await self.source_router.close()
        if self.grpc_channel:
            await self.grpc_channel.close()
        if self._redis_client:
            await self._redis_client.close()

    async def _acquire_job(self) -> Optional[ReplayJob]:
        """
        Attempt to acquire a queued job using atomic lease.

        Uses optimistic locking: UPDATE ... WHERE status=QUEUED AND (no lease OR expired lease)
        """
        async with get_db_context() as db:
            now = datetime.utcnow()
            lease_until = now + timedelta(seconds=settings.job_lease_duration_seconds)

            # Atomic acquire: find and lock in one statement
            result = await db.execute(
                update(ReplayJob)
                .where(
                    and_(
                        ReplayJob.status == JobStatus.QUEUED,
                        (ReplayJob.lease_expires_at.is_(None))
                        | (ReplayJob.lease_expires_at < now),
                    )
                )
                .values(
                    worker_id=self.worker_id,
                    lease_expires_at=lease_until,
                    status=JobStatus.RUNNING,
                    started_at=now,
                )
                .returning(ReplayJob.id)
            )
            job_id = result.scalar_one_or_none()

            if job_id:
                await db.commit()
                # Re-fetch full job
                result = await db.execute(
                    select(ReplayJob).where(ReplayJob.id == job_id)
                )
                job = result.scalar_one()
                self.current_job_id = str(job.id)
                logger.info("Acquired job %s", job.id)
                return job

            return None

    async def _execute_job(self, job: ReplayJob) -> None:
        """Execute a replay job with speed control and checkpointing."""
        try:
            start_ms = int(job.start_time.timestamp() * 1000)
            end_ms = int(job.end_time.timestamp() * 1000)

            # Select replay source
            source = self.source_router.get_source(start_ms, end_ms)

            async with get_db_context() as db:
                # Update replay source
                job = await db.get(ReplayJob, job.id)
                job.replay_source = source.source_name()

                # Count events if not already counted
                if job.events_total == 0:
                    job.events_total = await source.count_events(start_ms, end_ms)

                await db.commit()

            # Initialize timing for speed control
            replay_start_real = time.time()
            first_event_time: Optional[int] = None

            checkpoint_counter = 0
            checkpoint_interval = 100

            # Get checkpoint from job
            checkpoint = job.last_processed_id

            async for event in source.stream_events(start_ms, end_ms, checkpoint):
                if not self.running:
                    await self._checkpoint_job(job.id, event.message_id, JobStatus.PAUSED)
                    return

                # Initialize timing reference
                if first_event_time is None:
                    first_event_time = event.commit_time_ms

                # Speed-controlled timing
                await self._wait_for_virtual_time(
                    event.commit_time_ms,
                    first_event_time,
                    replay_start_real,
                    job.speed_factor,
                )

                # Process event
                success, was_dup = await self._replay_event(job, event)

                # Update counters
                async with get_db_context() as db:
                    job = await db.get(ReplayJob, job.id)
                    if success:
                        if was_dup:
                            job.events_skipped_dedup += 1
                        else:
                            job.events_processed += 1
                    else:
                        job.events_failed += 1

                    job.last_processed_id = event.message_id
                    job.last_processed_time = datetime.utcnow()

                    checkpoint_counter += 1
                    if checkpoint_counter >= checkpoint_interval:
                        await db.commit()
                        checkpoint_counter = 0

            # Completed
            await self._complete_job(job.id, JobStatus.COMPLETED)

        except Exception as e:
            logger.error("Job %s failed: %s", job.id, e, exc_info=True)
            await self._fail_job(job.id, str(e))

    async def _wait_for_virtual_time(
        self,
        event_time_ms: int,
        first_event_time: int,
        replay_start_real: float,
        speed_factor: float,
    ) -> None:
        """Wait until the appropriate wall-clock time based on speed factor."""
        original_elapsed_ms = event_time_ms - first_event_time
        replay_elapsed_ms = original_elapsed_ms / speed_factor
        target_real_time = replay_start_real + (replay_elapsed_ms / 1000)

        now = time.time()
        if target_real_time > now:
            await asyncio.sleep(target_real_time - now)

    async def _replay_event(
        self, job: ReplayJob, event: ReplayEvent
    ) -> tuple[bool, bool]:
        """
        Send event to Replayer (dedup is handled centrally by Replayer).
        Returns: (success, was_duplicate)
        """
        record = ChangeRecord()
        record.ParseFromString(event.payload)

        try:
            request = ReplayRequest(
                job_id=str(job.id),
                event=record,
                virtual_time=record.commit_time,
                speed_factor=job.speed_factor,
            )
            response = await self.grpc_stub.ReplayEvent(
                request, timeout=settings.replayer_timeout_seconds
            )
            # Replayer handles dedup check and marking - trust its response
            return response.success, response.was_duplicate
        except grpc.RpcError as e:
            logger.error("gRPC error replaying event: %s", e)
            return False, False

    async def _lease_renewal_loop(self) -> None:
        """Periodically renew lease on current job."""
        while self.running:
            await asyncio.sleep(settings.job_heartbeat_interval_seconds)

            if self.current_job_id:
                try:
                    await self._renew_lease(self.current_job_id)
                except Exception as e:
                    logger.error("Failed to renew lease: %s", e)

    async def _renew_lease(self, job_id: str) -> None:
        """Extend lease on current job."""
        async with get_db_context() as db:
            now = datetime.utcnow()
            lease_until = now + timedelta(seconds=settings.job_lease_duration_seconds)

            await db.execute(
                update(ReplayJob)
                .where(
                    and_(
                        ReplayJob.id == job_id,
                        ReplayJob.worker_id == self.worker_id,
                    )
                )
                .values(lease_expires_at=lease_until)
            )
            await db.commit()

    async def _checkpoint_job(
        self, job_id: str, last_id: str, status: JobStatus
    ) -> None:
        """Save checkpoint for resumability."""
        async with get_db_context() as db:
            job = await db.get(ReplayJob, job_id)
            job.last_processed_id = last_id
            job.last_processed_time = datetime.utcnow()
            job.status = status
            job.worker_id = None
            job.lease_expires_at = None
            await db.commit()

        self.current_job_id = None
        logger.info("Checkpointed job %s at %s", job_id, last_id)

    async def _complete_job(self, job_id, status: JobStatus) -> None:
        """Mark job as completed."""
        async with get_db_context() as db:
            job = await db.get(ReplayJob, job_id)
            job.status = status
            job.completed_at = datetime.utcnow()
            job.worker_id = None
            job.lease_expires_at = None
            await db.commit()

        self.current_job_id = None
        logger.info("Completed job %s", job_id)

    async def _fail_job(self, job_id, error: str) -> None:
        """Mark job as failed."""
        async with get_db_context() as db:
            job = await db.get(ReplayJob, job_id)
            job.status = JobStatus.FAILED
            job.error_message = error[:1000]  # Truncate long errors
            job.error_count += 1
            job.worker_id = None
            job.lease_expires_at = None
            await db.commit()

        self.current_job_id = None
        logger.error("Failed job %s: %s", job_id, error)
