"""Tests for the startup DB revision guard.

The application should fail fast if the database is not at the expected
Alembic head revision.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database import EXPECTED_ALEMBIC_HEAD, check_db_revision


class TestMigrationGuard:
    """Test check_db_revision behavior."""

    @pytest.mark.asyncio
    async def test_correct_revision_passes(self):
        """No error when DB is at expected head."""
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: EXPECTED_ALEMBIC_HEAD

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_conn = AsyncMock()
        mock_conn.execute.return_value = mock_result

        with patch("app.database.engine") as mock_engine:
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
            await check_db_revision()

    @pytest.mark.asyncio
    async def test_wrong_revision_raises(self):
        """RuntimeError when DB revision doesn't match expected."""
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, idx: "old_revision_abc"

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_conn = AsyncMock()
        mock_conn.execute.return_value = mock_result

        with patch("app.database.engine") as mock_engine:
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(RuntimeError, match="revision mismatch"):
                await check_db_revision()

    @pytest.mark.asyncio
    async def test_no_alembic_table_raises(self):
        """RuntimeError when alembic_version table doesn't exist."""
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = Exception("relation does not exist")

        with patch("app.database.engine") as mock_engine:
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(RuntimeError, match="no alembic_version table"):
                await check_db_revision()

    @pytest.mark.asyncio
    async def test_empty_alembic_table_raises(self):
        """RuntimeError when alembic_version table is empty."""
        mock_result = MagicMock()
        mock_result.first.return_value = None

        mock_conn = AsyncMock()
        mock_conn.execute.return_value = mock_result

        with patch("app.database.engine") as mock_engine:
            mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(RuntimeError, match="table is empty"):
                await check_db_revision()
