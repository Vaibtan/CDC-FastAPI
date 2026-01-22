"""Replay job management endpoints."""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.replay_job import ReplayJob, JobStatus
from app.api.deps import CurrentUser
from walstream_proto.models import (
    ReplayJobCreate,
    ReplayJobUpdate,
    ReplayJobResponse,
    ReplayJobListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=ReplayJobResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ReplayJobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    job_in: ReplayJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> ReplayJob:
    """
    Create a new replay job.

    The job will be created in PENDING status and can be started
    by updating its status to QUEUED.
    """
    job = ReplayJob(
        start_time=job_in.start_time,
        end_time=job_in.end_time,
        speed_factor=job_in.speed_factor,
        target_type=job_in.target_type,
        target_url=job_in.target_url,
        table_filter=job_in.table_filter,
        status=JobStatus.PENDING,
        created_by=current_user.username if current_user else None,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    logger.info("Created replay job %s", job.id)
    return job


@router.get("", response_model=ReplayJobListResponse)
@router.get("/", response_model=ReplayJobListResponse)
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ReplayJobListResponse:
    """
    List replay jobs with pagination and filtering.

    Supports filtering by status and pagination.
    """
    # Build query
    query = select(ReplayJob)
    count_query = select(func.count(ReplayJob.id))

    if status_filter:
        query = query.where(ReplayJob.status == status_filter)
        count_query = count_query.where(ReplayJob.status == status_filter)

    # Get total count
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    offset = (page - 1) * page_size
    query = query.order_by(ReplayJob.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return ReplayJobListResponse(
        items=[ReplayJobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/{job_id}", response_model=ReplayJobResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ReplayJob:
    """Get a specific replay job by ID."""
    result = await db.execute(select(ReplayJob).where(ReplayJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return job


@router.patch("/{job_id}", response_model=ReplayJobResponse)
async def update_job(
    job_id: UUID,
    job_in: ReplayJobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> ReplayJob:
    """
    Update a replay job.

    Can be used to:
    - Start a job (PENDING -> QUEUED)
    - Pause a job (RUNNING -> PAUSED)
    - Resume a job (PAUSED -> QUEUED)
    - Cancel a job (any non-terminal -> CANCELLED)
    - Update speed factor (while RUNNING or PAUSED)
    """
    result = await db.execute(select(ReplayJob).where(ReplayJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Validate status transitions
    if job_in.status:
        valid_transitions = {
            JobStatus.PENDING: {JobStatus.QUEUED, JobStatus.CANCELLED},
            JobStatus.QUEUED: {JobStatus.CANCELLED},
            JobStatus.RUNNING: {JobStatus.PAUSED, JobStatus.CANCELLED},
            JobStatus.PAUSED: {JobStatus.QUEUED, JobStatus.CANCELLED},
        }

        allowed = valid_transitions.get(job.status, set())
        if job_in.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition from {job.status} to {job_in.status}",
            )

        job.status = job_in.status
        if job_in.status == JobStatus.CANCELLED:
            job.completed_at = datetime.utcnow()

    if job_in.speed_factor is not None:
        if job.status not in (JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.PENDING):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot update speed factor in {job.status} state",
            )
        job.speed_factor = job_in.speed_factor

    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)

    logger.info("Updated replay job %s", job.id)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> None:
    """
    Delete a replay job.

    Only jobs in terminal states (COMPLETED, FAILED, CANCELLED) can be deleted.
    """
    result = await db.execute(select(ReplayJob).where(ReplayJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if not job.is_terminal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete job in {job.status} state. Cancel it first.",
        )

    await db.delete(job)
    await db.commit()

    logger.info("Deleted replay job %s", job_id)


@router.post("/{job_id}/start", response_model=ReplayJobResponse)
async def start_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> ReplayJob:
    """Convenience endpoint to start a PENDING job."""
    result = await db.execute(select(ReplayJob).where(ReplayJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status != JobStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not in PENDING state (current: {job.status})",
        )

    job.status = JobStatus.QUEUED
    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)

    logger.info("Started replay job %s", job.id)
    return job


@router.post("/{job_id}/pause", response_model=ReplayJobResponse)
async def pause_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> ReplayJob:
    """Convenience endpoint to pause a RUNNING job."""
    result = await db.execute(select(ReplayJob).where(ReplayJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status != JobStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not RUNNING (current: {job.status})",
        )

    job.status = JobStatus.PAUSED
    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)

    logger.info("Paused replay job %s", job.id)
    return job


@router.post("/{job_id}/resume", response_model=ReplayJobResponse)
async def resume_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> ReplayJob:
    """Convenience endpoint to resume a PAUSED job."""
    result = await db.execute(select(ReplayJob).where(ReplayJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status != JobStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not PAUSED (current: {job.status})",
        )

    job.status = JobStatus.QUEUED
    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)

    logger.info("Resumed replay job %s", job.id)
    return job


@router.post("/{job_id}/cancel", response_model=ReplayJobResponse)
async def cancel_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = None,
) -> ReplayJob:
    """Convenience endpoint to cancel a job."""
    result = await db.execute(select(ReplayJob).where(ReplayJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.is_terminal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is already in terminal state: {job.status}",
        )

    job.status = JobStatus.CANCELLED
    job.completed_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(job)

    logger.info("Cancelled replay job %s", job.id)
    return job
