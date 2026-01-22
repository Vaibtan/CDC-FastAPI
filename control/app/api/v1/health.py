"""Health check endpoints."""
import logging
from typing import Any

from fastapi import APIRouter, Depends
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, Settings
from app.database import get_db
from walstream_proto.models import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse)
async def health_check(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(lambda: get_settings()),
) -> HealthResponse:
    """
    Check health of all service components.

    Returns overall health status and individual component statuses.
    """
    components: dict[str, str] = {}
    overall_healthy = True

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        components["database"] = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        components["database"] = f"unhealthy: {str(e)[:50]}"
        overall_healthy = False

    # Check Redis
    try:
        redis_client = aioredis.from_url(settings.redis_url)
        await redis_client.ping()
        await redis_client.close()
        components["redis"] = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        components["redis"] = f"unhealthy: {str(e)[:50]}"
        overall_healthy = False

    # Check Kafka (basic connectivity)
    try:
        from aiokafka import AIOKafkaProducer

        producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_broker)
        await producer.start()
        await producer.stop()
        components["kafka"] = "healthy"
    except Exception as e:
        logger.warning(f"Kafka health check failed: {e}")
        components["kafka"] = f"unhealthy: {str(e)[:50]}"
        # Kafka being unhealthy doesn't fail overall health
        # as the control plane can still accept jobs

    return HealthResponse(
        status="healthy" if overall_healthy else "unhealthy",
        version="1.0.0",
        components=components,
    )


@router.get("/live")
async def liveness() -> dict[str, str]:
    """Kubernetes liveness probe - checks if process is running."""
    return {"status": "alive"}


@router.get("/ready")
async def readiness(
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Kubernetes readiness probe - checks if service can handle requests."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"status": "not_ready", "reason": str(e)[:100]}
