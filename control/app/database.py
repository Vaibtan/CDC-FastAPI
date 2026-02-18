"""Database configuration and session management."""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Expected Alembic head — update when adding new migrations.
EXPECTED_ALEMBIC_HEAD = "c3d4e5f6a7b8"

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Session factory — write path (auto-commit on success)
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Session factory — read-only path (no implicit commit)
async_read_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions (write path)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_read_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for read-only database sessions (no auto-commit)."""
    async with async_read_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_read_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Read-only DB context manager for internal/background tasks."""
    async with async_read_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions (for use outside FastAPI deps)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_revision() -> None:
    """Verify the database is at the expected Alembic head revision.

    Fails fast on startup if migrations haven't been applied, preventing
    the app from running against a stale schema.
    """
    async with engine.connect() as conn:
        try:
            result = await conn.execute(
                text("SELECT version_num FROM alembic_version")
            )
            row = result.first()
        except Exception:
            # alembic_version table doesn't exist — DB has never been migrated
            raise RuntimeError(
                "Database has no alembic_version table. "
                "Run 'alembic upgrade head' before starting the application."
            )

        if row is None:
            raise RuntimeError(
                "alembic_version table is empty. "
                "Run 'alembic upgrade head' before starting the application."
            )

        current = row[0]
        if current != EXPECTED_ALEMBIC_HEAD:
            raise RuntimeError(
                f"Database revision mismatch: DB is at '{current}', "
                f"app expects '{EXPECTED_ALEMBIC_HEAD}'. "
                "Run 'alembic upgrade head' to apply pending migrations."
            )

        logger.info("Database revision verified: %s", current)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
