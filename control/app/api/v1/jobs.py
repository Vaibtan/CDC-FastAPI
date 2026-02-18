"""Replay job management endpoints."""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_read_db
from app.models.replay_job import ReplayJob, JobStatus
from app.api.deps import CurrentUser, OperatorUser
from app.services import job_service
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
    current_user: OperatorUser,
    db: AsyncSession = Depends(get_db),
) -> ReplayJob:
    """Create a new replay job (PENDING)."""
    job = await job_service.create_job(
        db,
        start_time=job_in.start_time,
        end_time=job_in.end_time,
        speed_factor=job_in.speed_factor,
        target_type=job_in.target_type,
        target_url=job_in.target_url,
        table_filter=job_in.table_filter,
        created_by=current_user.username,
    )
    logger.info("Created replay job %s", job.id)
    return job


@router.get("", response_model=ReplayJobListResponse)
@router.get("/", response_model=ReplayJobListResponse)
async def list_jobs(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_read_db),
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ReplayJobListResponse:
    """List replay jobs with pagination and filtering."""
    jobs, total = await job_service.list_jobs(
        db, status_filter=status_filter, page=page, page_size=page_size,
    )
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
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_read_db),
) -> ReplayJob:
    """Get a specific replay job by ID."""
    return await job_service.get_job_or_404(db, job_id)


@router.patch("/{job_id}", response_model=ReplayJobResponse)
async def update_job(
    job_id: UUID,
    job_in: ReplayJobUpdate,
    current_user: OperatorUser,
    db: AsyncSession = Depends(get_db),
) -> ReplayJob:
    """Update a replay job (status transition and/or speed factor)."""
    job = await job_service.get_job_or_404(db, job_id)
    job = await job_service.update_job(
        db, job, target_status=job_in.status, speed_factor=job_in.speed_factor,
    )
    logger.info("Updated replay job %s", job.id)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    current_user: OperatorUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a replay job (must be in terminal state)."""
    job = await job_service.get_job_or_404(db, job_id)
    await job_service.delete_job(db, job)
    logger.info("Deleted replay job %s", job_id)


@router.post("/{job_id}/start", response_model=ReplayJobResponse)
async def start_job(
    job_id: UUID,
    current_user: OperatorUser,
    db: AsyncSession = Depends(get_db),
) -> ReplayJob:
    """Start a PENDING job."""
    job = await job_service.get_job_or_404(db, job_id)
    job = await job_service.start_job(db, job)
    logger.info("Started replay job %s", job.id)
    return job


@router.post("/{job_id}/pause", response_model=ReplayJobResponse)
async def pause_job(
    job_id: UUID,
    current_user: OperatorUser,
    db: AsyncSession = Depends(get_db),
) -> ReplayJob:
    """Pause a RUNNING job."""
    job = await job_service.get_job_or_404(db, job_id)
    job = await job_service.pause_job(db, job)
    logger.info("Paused replay job %s", job.id)
    return job


@router.post("/{job_id}/resume", response_model=ReplayJobResponse)
async def resume_job(
    job_id: UUID,
    current_user: OperatorUser,
    db: AsyncSession = Depends(get_db),
) -> ReplayJob:
    """Resume a PAUSED job."""
    job = await job_service.get_job_or_404(db, job_id)
    job = await job_service.resume_job(db, job)
    logger.info("Resumed replay job %s", job.id)
    return job


@router.post("/{job_id}/cancel", response_model=ReplayJobResponse)
async def cancel_job(
    job_id: UUID,
    current_user: OperatorUser,
    db: AsyncSession = Depends(get_db),
) -> ReplayJob:
    """Cancel a non-terminal job."""
    job = await job_service.get_job_or_404(db, job_id)
    job = await job_service.cancel_job(db, job)
    logger.info("Cancelled replay job %s", job.id)
    return job
