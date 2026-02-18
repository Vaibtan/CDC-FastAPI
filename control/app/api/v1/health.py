"""Health check endpoints."""
import logging

from fastapi import APIRouter, Depends, Response
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, Settings
from app.database import get_read_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
@router.get("/")
async def health_check(
    response: Response,
    db: AsyncSession = Depends(get_read_db),
    settings: Settings = Depends(lambda: get_settings()),
) -> dict:
    """
    Check health of all service components.

    Returns overall health status, a components map (detailed), and flat
    top-level keys (postgres, redis, kafka) for frontend compatibility.
    """
    components: dict[str, str] = {}
    overall_healthy = True

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        components["database"] = "healthy"
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        components["database"] = f"unhealthy: {str(e)[:50]}"
        overall_healthy = False

    # Check Redis
    try:
        redis_client = aioredis.from_url(settings.redis_url)
        await redis_client.ping()
        await redis_client.close()
        components["redis"] = "healthy"
    except Exception as e:
        logger.error("Redis health check failed: %s", e)
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
        logger.warning("Kafka health check failed: %s", e)
        components["kafka"] = f"unhealthy: {str(e)[:50]}"
        # Kafka being unhealthy doesn't fail overall health
        # as the control plane can still accept jobs

    if not overall_healthy:
        response.status_code = 503

    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "version": "1.0.0",
        "components": components,
        # Flat keys for frontend compatibility
        "postgres": components.get("database", "unknown"),
        "redis": components.get("redis", "unknown"),
        "kafka": components.get("kafka", "unknown"),
    }


@router.get("/live")
async def liveness() -> dict[str, str]:
    """Kubernetes liveness probe - checks if process is running."""
    return {"status": "alive"}


@router.get("/ready")
async def readiness(
    response: Response,
    db: AsyncSession = Depends(get_read_db),
) -> dict[str, str]:
    """Kubernetes readiness probe - checks if service can handle requests."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        logger.error("Readiness check failed: %s", e)
        response.status_code = 503
        return {"status": "not_ready", "reason": str(e)[:100]}
