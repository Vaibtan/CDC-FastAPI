"""Service layer for replay job state transitions.

All multi-step mutations go through this module so that transaction
boundaries are explicit and testable independently of HTTP routing.
"""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.replay_job import ReplayJob, JobStatus

logger = logging.getLogger(__name__)

# Valid status transitions (from -> set of allowed targets)
_VALID_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.QUEUED: {JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.PAUSED, JobStatus.CANCELLED},
    JobStatus.PAUSED: {JobStatus.QUEUED, JobStatus.CANCELLED},
}


async def get_job_or_404(db: AsyncSession, job_id: UUID) -> ReplayJob:
    """Fetch a replay job by ID or raise 404."""
    result = await db.execute(select(ReplayJob).where(ReplayJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )
    return job


async def list_jobs(
    db: AsyncSession,
    *,
    status_filter: Optional[JobStatus] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ReplayJob], int]:
    """Return paginated job list and total count."""
    query = select(ReplayJob)
    count_query = select(func.count(ReplayJob.id))

    if status_filter:
        query = query.where(ReplayJob.status == status_filter)
        count_query = count_query.where(ReplayJob.status == status_filter)

    total = (await db.execute(count_query)).scalar()
    offset = (page - 1) * page_size
    query = query.order_by(ReplayJob.created_at.desc()).offset(offset).limit(page_size)
    jobs = (await db.execute(query)).scalars().all()

    return list(jobs), total


async def create_job(
    db: AsyncSession,
    *,
    start_time: datetime,
    end_time: datetime,
    speed_factor: float = 1.0,
    target_type: str = "grpc",
    target_url: Optional[str] = None,
    table_filter: Optional[str] = None,
    created_by: str,
) -> ReplayJob:
    """Create a new replay job in PENDING state."""
    job = ReplayJob(
        start_time=start_time,
        end_time=end_time,
        speed_factor=speed_factor,
        target_type=target_type,
        target_url=target_url,
        table_filter=table_filter,
        status=JobStatus.PENDING,
        created_by=created_by,
    )
    db.add(job)
    await db.flush()
    return job


def _transition_status(job: ReplayJob, target: JobStatus) -> None:
    """Apply a status transition with validation.

    Clears lease ownership when moving to PAUSED or CANCELLED.
    """
    allowed = _VALID_TRANSITIONS.get(job.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {job.status} to {target}",
        )

    job.status = target

    if target in (JobStatus.PAUSED, JobStatus.CANCELLED):
        job.worker_id = None
        job.lease_expires_at = None
    if target == JobStatus.CANCELLED:
        job.completed_at = datetime.utcnow()


async def update_job(
    db: AsyncSession,
    job: ReplayJob,
    *,
    target_status: Optional[JobStatus] = None,
    speed_factor: Optional[float] = None,
) -> ReplayJob:
    """Apply updates (status transition and/or speed factor) inside a single flush."""
    if target_status:
        _transition_status(job, target_status)

    if speed_factor is not None:
        if job.status not in (JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.PENDING):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot update speed factor in {job.status} state",
            )
        job.speed_factor = speed_factor

    job.updated_at = datetime.utcnow()
    await db.flush()
    return job


async def start_job(db: AsyncSession, job: ReplayJob) -> ReplayJob:
    """Transition PENDING -> QUEUED."""
    if job.status != JobStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not in PENDING state (current: {job.status})",
        )
    job.status = JobStatus.QUEUED
    job.updated_at = datetime.utcnow()
    await db.flush()
    return job


async def pause_job(db: AsyncSession, job: ReplayJob) -> ReplayJob:
    """Transition RUNNING -> PAUSED, clearing lease."""
    if job.status != JobStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not RUNNING (current: {job.status})",
        )
    job.status = JobStatus.PAUSED
    job.worker_id = None
    job.lease_expires_at = None
    job.updated_at = datetime.utcnow()
    await db.flush()
    return job


async def resume_job(db: AsyncSession, job: ReplayJob) -> ReplayJob:
    """Transition PAUSED -> QUEUED."""
    if job.status != JobStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not PAUSED (current: {job.status})",
        )
    job.status = JobStatus.QUEUED
    job.updated_at = datetime.utcnow()
    await db.flush()
    return job


async def cancel_job(db: AsyncSession, job: ReplayJob) -> ReplayJob:
    """Transition any non-terminal -> CANCELLED, clearing lease."""
    if job.is_terminal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is already in terminal state: {job.status}",
        )
    job.status = JobStatus.CANCELLED
    job.worker_id = None
    job.lease_expires_at = None
    job.completed_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    await db.flush()
    return job


async def delete_job(db: AsyncSession, job: ReplayJob) -> None:
    """Delete a terminal job."""
    if not job.is_terminal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete job in {job.status} state. Cancel it first.",
        )
    await db.delete(job)
    await db.flush()
