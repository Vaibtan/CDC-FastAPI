"""
WalStream gRPC Replayer Service.

This service handles the actual replay of CDC events to target systems.
Key features:
- Centralized deduplication enforcement
- Pluggable target appliers (database, HTTP, etc.)
- Prometheus metrics
- Health checks
"""
import asyncio
import hashlib
import logging
import os
import signal
import sys
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import grpc
from grpc import aio as grpc_aio
from prometheus_client import Counter, Histogram, start_http_server

from walstream_proto.v1 import (
    ChangeRecord,
    ReplayRequest,
    ReplayResponse,
    ReplayerServicer,
    add_ReplayerServicer_to_server,
    HealthRequest,
    HealthResponse,
)

# ==========================================================================
# Configuration
# ==========================================================================

GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "9092"))

# Dedup database (PostgreSQL)
DEDUP_DATABASE_URL = os.getenv(
    "DEDUP_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/walstream_control",
)

# Target database (where events are replayed to)
TARGET_DATABASE_URL = os.getenv(
    "TARGET_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/walstream_target",
)

# Dedup TTL
DEDUP_TTL_DAYS = int(os.getenv("DEDUP_TTL_DAYS", "7"))

# ==========================================================================
# Logging
# ==========================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("replayer")

# ==========================================================================
# Prometheus Metrics
# ==========================================================================

EVENTS_REPLAYED = Counter(
    "walstream_events_replayed_total",
    "Total events successfully replayed",
    ["table", "operation"],
)

EVENTS_DUPLICATES = Counter(
    "walstream_events_duplicates_total",
    "Total duplicate events skipped",
)

EVENTS_FAILED = Counter(
    "walstream_events_failed_total",
    "Total events that failed to replay",
    ["error_type"],
)

REPLAY_LATENCY = Histogram(
    "walstream_replay_latency_seconds",
    "Time to replay a single event",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)


# ==========================================================================
# Target Appliers
# ==========================================================================


class TargetApplier(ABC):
    """Abstract interface for applying events to target systems."""

    @abstractmethod
    async def apply(self, event: ChangeRecord) -> bool:
        """
        Apply the event to the target system.
        Returns True on success, False on failure.
        """
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to target."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connection to target."""
        pass


class PostgreSQLTargetApplier(TargetApplier):
    """Applies events to a PostgreSQL database."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create connection pool."""
        self._pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10,
        )
        logger.info("Connected to target PostgreSQL database")

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()

    async def apply(self, event: ChangeRecord) -> bool:
        """Apply event to target database."""
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self._pool.acquire() as conn:
                if event.operation == "INSERT":
                    await self._apply_insert(conn, event)
                elif event.operation == "UPDATE":
                    await self._apply_update(conn, event)
                elif event.operation == "DELETE":
                    await self._apply_delete(conn, event)
                elif event.operation == "TRUNCATE":
                    await self._apply_truncate(conn, event)
                else:
                    logger.warning("Unknown operation: %s", event.operation)
                    return False

            return True
        except Exception as e:
            logger.error(
                "Failed to apply %s on %s: %s", event.operation, event.table, e
            )
            return False

    async def _apply_insert(
        self, conn: asyncpg.Connection, event: ChangeRecord
    ) -> None:
        """Apply INSERT operation."""
        if not event.new:
            return

        columns = list(event.new.keys())
        values = list(event.new.values())
        placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
        column_names = ", ".join(f'"{c}"' for c in columns)

        # Use ON CONFLICT DO NOTHING for idempotency
        query = f"""
            INSERT INTO {event.table} ({column_names})
            VALUES ({placeholders})
            ON CONFLICT DO NOTHING
        """
        await conn.execute(query, *values)

    async def _apply_update(
        self, conn: asyncpg.Connection, event: ChangeRecord
    ) -> None:
        """Apply UPDATE operation."""
        if not event.new or not event.old:
            return

        # Build SET clause from new values
        set_parts = []
        values = []
        idx = 1
        for col, val in event.new.items():
            set_parts.append(f'"{col}" = ${idx}')
            values.append(val)
            idx += 1

        # Build WHERE clause from old values (identity columns)
        where_parts = []
        for col, val in event.old.items():
            where_parts.append(f'"{col}" = ${idx}')
            values.append(val)
            idx += 1

        query = f"""
            UPDATE {event.table}
            SET {", ".join(set_parts)}
            WHERE {" AND ".join(where_parts)}
        """
        await conn.execute(query, *values)

    async def _apply_delete(
        self, conn: asyncpg.Connection, event: ChangeRecord
    ) -> None:
        """Apply DELETE operation."""
        if not event.old:
            return

        # Build WHERE clause from old values
        where_parts = []
        values = []
        for idx, (col, val) in enumerate(event.old.items(), 1):
            where_parts.append(f'"{col}" = ${idx}')
            values.append(val)

        query = f"""
            DELETE FROM {event.table}
            WHERE {" AND ".join(where_parts)}
        """
        await conn.execute(query, *values)

    async def _apply_truncate(
        self, conn: asyncpg.Connection, event: ChangeRecord
    ) -> None:
        """Apply TRUNCATE operation."""
        query = f"TRUNCATE TABLE {event.table}"
        await conn.execute(query)


class LoggingTargetApplier(TargetApplier):
    """Debug applier that just logs events."""

    async def connect(self) -> None:
        logger.info("Logging target applier initialized")

    async def close(self) -> None:
        pass

    async def apply(self, event: ChangeRecord) -> bool:
        logger.info(
            f"[DRY-RUN] {event.operation} on {event.table}: "
            f"old={dict(event.old)}, new={dict(event.new)}"
        )
        return True


# ==========================================================================
# Dedup Store
# ==========================================================================


class AsyncDedupStore:
    """Async deduplication store using PostgreSQL."""

    def __init__(self, database_url: str, ttl_days: int = 7) -> None:
        self.database_url = database_url
        self.ttl_days = ttl_days
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create connection pool and ensure schema exists."""
        self._pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10,
        )

        # Ensure dedup schema and table exist
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE SCHEMA IF NOT EXISTS walstream_dedup")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS walstream_dedup.processed_events (
                    idempotency_key VARCHAR(255) PRIMARY KEY,
                    processed_at TIMESTAMPTZ DEFAULT NOW(),
                    job_id VARCHAR(36),
                    expires_at TIMESTAMPTZ NOT NULL
                )
            """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_processed_events_expires
                ON walstream_dedup.processed_events(expires_at)
            """
            )

        logger.info("Dedup store initialized")

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()

    async def exists(self, idempotency_key: str) -> bool:
        """
        Check if an event has already been processed.

        Returns True if the key exists and hasn't expired.
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT 1 FROM walstream_dedup.processed_events
                    WHERE idempotency_key = $1 AND expires_at > NOW()
                    """,
                    idempotency_key,
                )
                return row is not None
        except Exception as e:
            logger.error("Dedup exists check error: %s", e)
            raise

    async def mark_processed(
        self, idempotency_key: str, job_id: Optional[str] = None
    ) -> None:
        """
        Mark an event as processed. Should only be called after successful apply.
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        expires_at = datetime.now(timezone.utc) + timedelta(days=self.ttl_days)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO walstream_dedup.processed_events
                    (idempotency_key, job_id, expires_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (idempotency_key) DO UPDATE
                SET
                    processed_at = NOW(),
                    job_id = EXCLUDED.job_id,
                    expires_at = EXCLUDED.expires_at
                """,
                idempotency_key,
                job_id,
                expires_at,
            )

    async def check_and_mark(
        self, idempotency_key: str, job_id: Optional[str] = None
    ) -> tuple[bool, bool]:
        """
        Atomically check if event is processed and mark it if not.

        Returns: (was_new, success)
        - was_new: True if this is a new event (not a duplicate)
        - success: True if the operation completed successfully

        NOTE: Kept for backward compatibility (e.g. health checks).
        The ReplayEvent method uses exists() + mark_processed() separately
        to avoid data loss on apply failure.
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized")

        expires_at = datetime.now(timezone.utc) + timedelta(days=self.ttl_days)

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """
                    INSERT INTO walstream_dedup.processed_events
                        (idempotency_key, job_id, expires_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (idempotency_key) DO NOTHING
                """,
                    idempotency_key,
                    job_id,
                    expires_at,
                )

                was_new = result == "INSERT 0 1"
                return (was_new, True)

        except Exception as e:
            logger.error("Dedup check_and_mark error: %s", e)
            return (False, False)

    async def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count of deleted rows."""
        if not self._pool:
            return 0

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM walstream_dedup.processed_events
                    WHERE expires_at < NOW()
                """
                )
                count = int(result.split()[-1])
                if count > 0:
                    logger.info("Cleaned up %d expired dedup entries", count)
                return count
        except Exception as e:
            logger.error("Dedup cleanup error: %s", e)
            return 0


# ==========================================================================
# gRPC Replayer Service
# ==========================================================================


class ReplayerService(ReplayerServicer):
    """gRPC Replayer service implementation."""

    def __init__(
        self,
        target_applier: TargetApplier,
        dedup_store: AsyncDedupStore,
    ) -> None:
        self.target_applier = target_applier
        self.dedup_store = dedup_store

    async def ReplayEvent(
        self, request: ReplayRequest, context: grpc_aio.ServicerContext
    ) -> ReplayResponse:
        """
        Replay a single event with at-least-once semantics.

        Deduplication flow (unbundled to prevent data loss):
        1. Compute idempotency key from event
        2. Check if already processed (exists only, no mark)
        3. If new, apply to target
        4. Mark as processed ONLY on successful apply
        """
        start_time = time.time()

        try:
            event = request.event

            # Compute idempotency key
            if request.idempotency_key:
                idemp_key = request.idempotency_key
            else:
                idemp_key = self._compute_idempotency_key(event)

            # 1. Check only (no mark)
            try:
                already_processed = await self.dedup_store.exists(idemp_key)
            except Exception:
                EVENTS_FAILED.labels(error_type="dedup_error").inc()
                return ReplayResponse(
                    success=False,
                    message="Deduplication check failed",
                    was_duplicate=False,
                )

            if already_processed:
                EVENTS_DUPLICATES.inc()
                return ReplayResponse(
                    success=True,
                    message="duplicate_skipped",
                    was_duplicate=True,
                )

            # 2. Apply to target
            applied = await self.target_applier.apply(event)

            # 3. Mark only on success
            if applied:
                await self.dedup_store.mark_processed(idemp_key, request.job_id)
                EVENTS_REPLAYED.labels(
                    table=event.table, operation=event.operation
                ).inc()
                REPLAY_LATENCY.observe(time.time() - start_time)
                return ReplayResponse(
                    success=True,
                    message="applied",
                    was_duplicate=False,
                )
            else:
                EVENTS_FAILED.labels(error_type="apply_error").inc()
                return ReplayResponse(
                    success=False,
                    message="Failed to apply event to target",
                    was_duplicate=False,
                )

        except Exception as e:
            logger.error("ReplayEvent error: %s", e, exc_info=True)
            EVENTS_FAILED.labels(error_type="unknown").inc()
            return ReplayResponse(
                success=False,
                message=str(e)[:200],
                was_duplicate=False,
            )

    async def Health(
        self, request: HealthRequest, context: grpc_aio.ServicerContext
    ) -> HealthResponse:
        """Health check endpoint."""
        components = {}

        # Check dedup store
        try:
            await self.dedup_store.check_and_mark("health_check_probe", None)
            components["dedup_store"] = "healthy"
        except Exception as e:
            components["dedup_store"] = "unhealthy: %s" % str(e)[:50]

        # Check target applier (if PostgreSQL)
        if isinstance(self.target_applier, PostgreSQLTargetApplier):
            try:
                if self.target_applier._pool:
                    async with self.target_applier._pool.acquire() as conn:
                        await conn.execute("SELECT 1")
                    components["target"] = "healthy"
                else:
                    components["target"] = "unhealthy: pool not initialized"
            except Exception as e:
                components["target"] = "unhealthy: %s" % str(e)[:50]
        else:
            components["target"] = "healthy"

        overall_healthy = all("unhealthy" not in v for v in components.values())

        return HealthResponse(healthy=overall_healthy, components=components)

    def _compute_idempotency_key(self, event: ChangeRecord) -> str:
        """
        Compute idempotency key from event.
        Format: {lsn}:{table}:{pk_hash}
        """
        # Use new for INSERT/UPDATE, old for DELETE
        data = dict(event.new) if event.new else dict(event.old)

        # Create a deterministic hash of the data
        data_str = ":".join(f"{k}={v}" for k, v in sorted(data.items()))
        pk_hash = hashlib.md5(data_str.encode()).hexdigest()[:16]

        return f"{event.lsn}:{event.table}:{pk_hash}"


# ==========================================================================
# Server
# ==========================================================================


class ReplayerServer:
    """gRPC server wrapper with lifecycle management."""

    def __init__(
        self,
        port: int = GRPC_PORT,
        target_type: str = "postgresql",
    ) -> None:
        self.port = port
        self.target_type = target_type
        self._server: Optional[grpc_aio.Server] = None
        self._target_applier: Optional[TargetApplier] = None
        self._dedup_store: Optional[AsyncDedupStore] = None

    async def start(self) -> None:
        """Start the gRPC server."""
        logger.info("Starting WalStream Replayer...")

        # Start metrics server
        start_http_server(METRICS_PORT)
        logger.info("Metrics available on port %d", METRICS_PORT)

        # Initialize dedup store
        self._dedup_store = AsyncDedupStore(DEDUP_DATABASE_URL, DEDUP_TTL_DAYS)
        await self._dedup_store.connect()

        # Initialize target applier
        if self.target_type == "postgresql":
            self._target_applier = PostgreSQLTargetApplier(TARGET_DATABASE_URL)
        else:
            self._target_applier = LoggingTargetApplier()
        await self._target_applier.connect()

        # Create gRPC server
        self._server = grpc_aio.server()

        # Add service
        service = ReplayerService(self._target_applier, self._dedup_store)
        add_ReplayerServicer_to_server(service, self._server)

        # Start listening
        self._server.add_insecure_port(f"[::]:{self.port}")
        await self._server.start()

        logger.info("Replayer gRPC server started on port %d", self.port)

        # Start background cleanup task
        asyncio.create_task(self._cleanup_loop())

        # Wait for termination
        await self._server.wait_for_termination()

    async def stop(self) -> None:
        """Stop the server gracefully."""
        logger.info("Stopping Replayer server...")

        if self._server:
            await self._server.stop(grace=5.0)

        if self._target_applier:
            await self._target_applier.close()

        if self._dedup_store:
            await self._dedup_store.close()

        logger.info("Replayer server stopped")

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired dedup entries."""
        while True:
            await asyncio.sleep(3600)  # Run every hour
            if self._dedup_store:
                await self._dedup_store.cleanup_expired()


async def serve() -> None:
    """Main entry point."""
    server = ReplayerServer()

    # Setup signal handlers
    loop = asyncio.get_event_loop()

    def shutdown():
        asyncio.create_task(server.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown)
        except NotImplementedError:
            # Windows
            pass

    await server.start()


def main() -> None:
    """CLI entry point."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
