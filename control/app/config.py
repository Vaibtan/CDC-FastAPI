"""Application configuration using Pydantic Settings."""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "WalStream Control"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database (Control Plane)
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/walstream_control"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_stream: str = "walstream:events"
    redis_replay_threshold_ms: int = 3600000  # 1 hour

    # Kafka
    kafka_broker: str = "localhost:9092"
    kafka_topic: str = "walstream.archive"
    kafka_consumer_group: str = "walstream-replay"

    # gRPC Replayer
    replayer_host: str = "localhost"
    replayer_port: int = 50051
    replayer_timeout_seconds: int = 30

    # Job Worker
    job_worker_count: int = 4
    job_poll_interval_seconds: float = 1.0
    job_heartbeat_interval_seconds: float = 10.0
    job_lease_duration_seconds: int = 300  # 5 minutes

    # Deduplication
    dedup_ttl_seconds: int = 604800  # 7 days

    # Security
    secret_key: str = "change-me-in-production-use-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Metrics
    metrics_port: int = 9091

    # Logging
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
