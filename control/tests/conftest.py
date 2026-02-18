"""Shared fixtures for control plane tests.

These fixtures provide test clients and mock dependencies so tests run
without external services. Integration-level fixtures that need the full
app are guarded behind dependency checks.
"""
import asyncio
import sys
from datetime import datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Ensure missing optional deps don't crash pure unit tests.
# The app modules need jose, passlib, prometheus_client, aiokafka, alembic.
# We stub them only if they are genuinely absent so that environments with
# all deps installed also work.
# ---------------------------------------------------------------------------

_STUBBED_PACKAGES: set[str] = set()

_OPTIONAL_STUBS = {
    "jose": ["jose", "jose.jwt"],
    "passlib": ["passlib", "passlib.context"],
    "prometheus_client": ["prometheus_client"],
    "aiokafka": ["aiokafka"],
    "alembic": ["alembic", "alembic.context"],
    "asyncpg": ["asyncpg"],
    "grpc": ["grpc", "grpc.aio"],
}

for _pkg, _modules in _OPTIONAL_STUBS.items():
    try:
        __import__(_pkg)
    except (ImportError, SyntaxError):
        _STUBBED_PACKAGES.add(_pkg)
        for _mod in _modules:
            sys.modules[_mod] = MagicMock()


def _has_real(pkg: str) -> bool:
    """Return True if *pkg* is a real import (not stubbed)."""
    return pkg not in _STUBBED_PACKAGES


# In-memory SQLite is the default integration-test backend.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# Now safe to import app modules ------------------------------------------
from app.database import Base, get_db, get_read_db
from app.api.deps import get_current_user, create_access_token
from app.models.user import User, UserRole

# Strip PostgreSQL-specific schema from ProcessedEvent for SQLite compat
from app.models.dedup_state import ProcessedEvent
if TEST_DATABASE_URL.startswith("sqlite"):
    ProcessedEvent.__table__.schema = None


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# In-memory aiosqlite engine for integration tests
# ---------------------------------------------------------------------------

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a shared test engine with all tables."""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Transactional session that rolls back after each test."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Test users
# ---------------------------------------------------------------------------


def _make_user(
    username: str = "testuser",
    role: UserRole = UserRole.OPERATOR,
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid4(),
        username=username,
        email=f"{username}@test.local",
        hashed_password="not-a-real-hash",
        is_active=is_active,
        is_superuser=role == UserRole.ADMIN,
        role=role,
    )
    return user


@pytest.fixture
def test_user() -> User:
    return _make_user()


@pytest.fixture
def admin_user() -> User:
    return _make_user(username="admin", role=UserRole.ADMIN)


@pytest.fixture
def viewer_user() -> User:
    return _make_user(username="viewer", role=UserRole.VIEWER)


@pytest.fixture
def test_token(test_user: User) -> str:
    """Valid JWT for test_user (requires python-jose)."""
    if not _has_real("jose"):
        pytest.skip("python-jose not installed")
    return create_access_token(
        data={"sub": test_user.username},
        expires_delta=timedelta(hours=1),
    )


@pytest.fixture
def expired_token(test_user: User) -> str:
    """Expired JWT for test_user (requires python-jose)."""
    if not _has_real("jose"):
        pytest.skip("python-jose not installed")
    return create_access_token(
        data={"sub": test_user.username},
        expires_delta=timedelta(seconds=-1),
    )


# ---------------------------------------------------------------------------
# FastAPI test client with dependency overrides
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, test_user: User) -> AsyncGenerator:
    """AsyncClient with overridden DB and auth deps."""
    from httpx import ASGITransport, AsyncClient as HC
    from app.main import app

    async def _override_get_db():
        yield db_session

    async def _override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_read_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user

    async with HC(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthed_client(db_session: AsyncSession) -> AsyncGenerator:
    """AsyncClient with DB override but NO auth override."""
    from httpx import ASGITransport, AsyncClient as HC
    from app.main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_read_db] = _override_get_db

    async with HC(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
