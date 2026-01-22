"""Deduplication store for idempotency enforcement."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.models.dedup_state import ProcessedEvent

settings = get_settings()
logger = logging.getLogger(__name__)


class DedupStore:
    """
    Deduplication store using PostgreSQL for durability.

    Provides atomic check-and-mark operations for idempotency enforcement.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.ttl_seconds = settings.dedup_ttl_seconds

    async def exists(self, idempotency_key: str) -> bool:
        """
        Check if an event has already been processed.

        Returns True if the key exists and hasn't expired.
        """
        result = await self.db.execute(
            select(ProcessedEvent).where(
                ProcessedEvent.idempotency_key == idempotency_key
            )
        )
        event = result.scalar_one_or_none()

        if event is None:
            return False

        # Check expiration
        if event.expires_at < datetime.utcnow():
            # Expired - clean it up
            await self.db.delete(event)
            return False

        return True

    async def mark_processed(
        self,
        idempotency_key: str,
        job_id: Optional[str] = None,
    ) -> bool:
        """
        Mark an event as processed (idempotent operation).

        Uses PostgreSQL upsert to handle concurrent calls safely.
        Returns True if this was a new entry, False if already existed.
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=self.ttl_seconds)

        # Use INSERT ... ON CONFLICT DO NOTHING for atomicity
        stmt = (
            insert(ProcessedEvent)
            .values(
                idempotency_key=idempotency_key,
                processed_at=now,
                job_id=job_id,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        # rowcount > 0 means we inserted (new entry)
        return result.rowcount > 0

    async def check_and_mark(
        self,
        idempotency_key: str,
        job_id: Optional[str] = None,
    ) -> tuple[bool, bool]:
        """
        Atomic check-and-mark operation.

        Returns: (was_new, success)
        - was_new: True if this is a new event (not a duplicate)
        - success: True if the operation completed successfully
        """
        try:
            # Try to insert - will fail if already exists
            was_new = await self.mark_processed(idempotency_key, job_id)
            return (was_new, True)
        except Exception as e:
            logger.error(f"Error in check_and_mark: {e}")
            return (False, False)

    async def cleanup_expired(self, batch_size: int = 1000) -> int:
        """
        Clean up expired entries.

        Should be called periodically by a background task.
        Returns the number of deleted entries.
        """
        now = datetime.utcnow()

        result = await self.db.execute(
            delete(ProcessedEvent)
            .where(ProcessedEvent.expires_at < now)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired dedup entries")

        return deleted
