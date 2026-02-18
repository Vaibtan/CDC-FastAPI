"""Unit tests for wal2json v2 parsing."""
import importlib
import sys
from pathlib import Path

import pytest

# ingestor/ is not a Python package (no __init__.py) — load the module directly
_ingestor_path = Path(__file__).resolve().parents[2] / "ingestor" / "ingestor.py"
_spec = importlib.util.spec_from_file_location("ingestor_mod", _ingestor_path)
_ingestor_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ingestor_mod)
parse_wal2json_v2 = _ingestor_mod.parse_wal2json_v2


class TestParseWal2jsonV2:
    """Test the ingestor's WAL parser."""

    def test_insert_columns_format(self):
        """Parse INSERT with columns array (wal2json v2 standard)."""
        payload = {
            "timestamp": "2024-01-15 10:30:00.123456+00",
            "change": [
                {
                    "kind": "I",
                    "schema": "public",
                    "table": "events",
                    "columns": [
                        {"name": "id", "type": "integer", "value": 1},
                        {"name": "name", "type": "text", "value": "test"},
                    ],
                }
            ],
        }
        records = parse_wal2json_v2(payload, lsn=1234)
        assert len(records) == 1

        r = records[0]
        assert r.table == "public.events"
        assert r.operation == "INSERT"
        assert dict(r.new) == {"id": "1", "name": "test"}
        assert dict(r.old) == {}

    def test_update_with_identity(self):
        """Parse UPDATE with identity array for old values."""
        payload = {
            "timestamp": "2024-01-15T10:30:00",
            "change": [
                {
                    "kind": "U",
                    "schema": "public",
                    "table": "users",
                    "columns": [
                        {"name": "id", "type": "integer", "value": 1},
                        {"name": "name", "type": "text", "value": "new_name"},
                    ],
                    "identity": [
                        {"name": "id", "type": "integer", "value": 1},
                    ],
                }
            ],
        }
        records = parse_wal2json_v2(payload, lsn=5678)

        r = records[0]
        assert r.operation == "UPDATE"
        assert dict(r.new) == {"id": "1", "name": "new_name"}
        assert dict(r.old) == {"id": "1"}

    def test_delete_with_oldkeys(self):
        """Parse DELETE with oldkeys format."""
        payload = {
            "timestamp": "2024-01-15 10:30:00+00",
            "change": [
                {
                    "kind": "D",
                    "schema": "public",
                    "table": "events",
                    "oldkeys": {
                        "keynames": ["id"],
                        "keyvalues": [42],
                    },
                }
            ],
        }
        records = parse_wal2json_v2(payload, lsn=9999)

        r = records[0]
        assert r.operation == "DELETE"
        assert dict(r.old) == {"id": "42"}
        assert dict(r.new) == {}

    def test_truncate(self):
        """Parse TRUNCATE operation."""
        payload = {
            "timestamp": "2024-01-15 10:30:00+00",
            "change": [
                {
                    "kind": "T",
                    "schema": "public",
                    "table": "events",
                }
            ],
        }
        records = parse_wal2json_v2(payload, lsn=100)

        r = records[0]
        assert r.operation == "TRUNCATE"

    def test_multiple_changes_in_single_payload(self):
        """One WAL message can contain multiple changes."""
        payload = {
            "timestamp": "2024-01-15 10:30:00+00",
            "change": [
                {
                    "kind": "I",
                    "schema": "public",
                    "table": "a",
                    "columns": [{"name": "id", "type": "int", "value": 1}],
                },
                {
                    "kind": "I",
                    "schema": "public",
                    "table": "b",
                    "columns": [{"name": "id", "type": "int", "value": 2}],
                },
            ],
        }
        records = parse_wal2json_v2(payload, lsn=200)
        assert len(records) == 2
        assert records[0].table == "public.a"
        assert records[1].table == "public.b"

    def test_columnnames_columnvalues_format(self):
        """Parse alternative format with columnnames/columnvalues arrays."""
        payload = {
            "timestamp": "2024-01-15 10:30:00+00",
            "change": [
                {
                    "kind": "I",
                    "schema": "public",
                    "table": "events",
                    "columnnames": ["id", "name"],
                    "columnvalues": [1, "test"],
                }
            ],
        }
        records = parse_wal2json_v2(payload, lsn=300)
        assert dict(records[0].new) == {"id": "1", "name": "test"}

    def test_missing_timestamp_uses_current_time(self):
        """Empty timestamp falls back to current time."""
        payload = {
            "change": [
                {
                    "kind": "I",
                    "schema": "public",
                    "table": "events",
                    "columns": [{"name": "id", "type": "int", "value": 1}],
                }
            ],
        }
        records = parse_wal2json_v2(payload, lsn=400)
        assert records[0].commit_time > 0

    def test_none_values_skipped(self):
        """Columns with None values are excluded from the record."""
        payload = {
            "timestamp": "2024-01-15 10:30:00+00",
            "change": [
                {
                    "kind": "I",
                    "schema": "public",
                    "table": "events",
                    "columns": [
                        {"name": "id", "type": "int", "value": 1},
                        {"name": "nullable_col", "type": "text", "value": None},
                    ],
                }
            ],
        }
        records = parse_wal2json_v2(payload, lsn=500)
        assert "nullable_col" not in dict(records[0].new)

    def test_lsn_is_string(self):
        """LSN is stored as string in the record."""
        payload = {
            "timestamp": "2024-01-15 10:30:00+00",
            "change": [
                {
                    "kind": "I",
                    "schema": "public",
                    "table": "events",
                    "columns": [{"name": "id", "type": "int", "value": 1}],
                }
            ],
        }
        records = parse_wal2json_v2(payload, lsn=0xABCDEF)
        assert records[0].lsn == str(0xABCDEF)

    def test_empty_change_array(self):
        """Payload with empty change array returns no records."""
        payload = {"timestamp": "2024-01-15 10:30:00+00", "change": []}
        records = parse_wal2json_v2(payload, lsn=600)
        assert records == []
