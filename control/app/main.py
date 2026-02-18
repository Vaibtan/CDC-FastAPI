"""
WalStream Control Plane - FastAPI Application.

This is the main entry point for the FastAPI application that provides:
- REST API for job management
- WebSocket for real-time event streaming
- Health check endpoints
- Authentication and authorization
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.config import get_settings
from app.database import check_db_revision, close_db
from app.api.v1.router import api_router
from app.metrics import JobMetricsPublisher
from app.middleware.auth_context import AuthContextMiddleware
from app.middleware.audit import AuditMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

settings = get_settings()
job_metrics_publisher = JobMetricsPublisher(settings.job_metrics_refresh_interval_seconds)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager for startup/shutdown."""
    # Startup
    logger.info("Starting WalStream Control Plane...")
    await check_db_revision()
    logger.info("Database revision verified")
    await job_metrics_publisher.start()
    logger.info("Background job metrics publisher started")

    yield

    # Shutdown
    logger.info("Shutting down WalStream Control Plane...")
    await job_metrics_publisher.stop()
    await close_db()
    logger.info("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="WalStream CDC Control Plane API",
    version="1.0.0",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth context — decode JWT early so audit and other middleware can see
# the caller identity; also flags expired tokens via X-Token-Expired header.
app.add_middleware(AuthContextMiddleware)

# Audit logging for mutations (POST/PATCH/PUT/DELETE)
app.add_middleware(AuditMiddleware)

# Per-IP rate limiting (token-bucket, backed by Redis)
app.add_middleware(
    RateLimitMiddleware,
    capacity=settings.rate_limit_capacity,
    refill_rate=settings.rate_limit_refill_rate,
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include API router
app.include_router(api_router, prefix=settings.api_v1_prefix)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# Root endpoint
@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with basic service info."""
    return {
        "service": settings.app_name,
        "version": "1.0.0",
        "docs": f"{settings.api_v1_prefix}/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }


def create_app() -> FastAPI:
    """Factory function for creating the app (useful for testing)."""
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
