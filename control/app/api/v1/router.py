"""Main API v1 router aggregating all endpoints."""
from fastapi import APIRouter

from app.api.v1 import jobs, health, auth, events

api_router = APIRouter()

# Include all sub-routers
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
