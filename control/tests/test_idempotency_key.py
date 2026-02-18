"""Unit tests for idempotency key generation."""
import pytest
from walstream_proto.models import ChangeRecordModel, Operation


class TestIdempotencyKey:
    """Test ChangeRecordModel.idempotency_key."""

    def test_key_with_explicit_pk_fields(self):
        """Key uses specified primary key fields."""
        record = ChangeRecordModel(
            lsn="0/AABB",
            commit_time=1000,
            table="public.users",
            operation=Operation.INSERT,
            new={"id": "42", "name": "alice"},
        )
        key = record.idempotency_key(primary_key_fields=["id"])
        assert key == "0/AABB:public.users:42"

    def test_key_with_composite_pk(self):
        """Key with multiple primary key fields is colon-separated."""
        record = ChangeRecordModel(
            lsn="0/CCDD",
            commit_time=2000,
            table="public.order_items",
            operation=Operation.INSERT,
            new={"order_id": "10", "item_id": "20", "qty": "5"},
        )
        key = record.idempotency_key(primary_key_fields=["order_id", "item_id"])
        assert key == "0/CCDD:public.order_items:10:20"

    def test_key_uses_old_for_delete(self):
        """DELETE uses old values, not new."""
        record = ChangeRecordModel(
            lsn="0/1234",
            commit_time=3000,
            table="public.events",
            operation=Operation.DELETE,
            old={"id": "99"},
            new={},
        )
        key = record.idempotency_key(primary_key_fields=["id"])
        assert key == "0/1234:public.events:99"

    def test_key_without_pk_fields_is_deterministic(self):
        """Fallback key (hash-based) is deterministic for same data."""
        record = ChangeRecordModel(
            lsn="0/5678",
            commit_time=4000,
            table="public.x",
            operation=Operation.INSERT,
            new={"a": "1", "b": "2"},
        )
        key1 = record.idempotency_key()
        key2 = record.idempotency_key()
        assert key1 == key2

    def test_different_lsn_different_key(self):
        """Same data at different LSN produces different keys."""
        kwargs = dict(
            commit_time=5000,
            table="public.x",
            operation=Operation.INSERT,
            new={"id": "1"},
        )
        k1 = ChangeRecordModel(lsn="0/A", **kwargs).idempotency_key(primary_key_fields=["id"])
        k2 = ChangeRecordModel(lsn="0/B", **kwargs).idempotency_key(primary_key_fields=["id"])
        assert k1 != k2

    def test_missing_pk_field_produces_empty_segment(self):
        """If a specified PK field is absent, the segment is empty string."""
        record = ChangeRecordModel(
            lsn="0/FF",
            commit_time=6000,
            table="public.x",
            operation=Operation.INSERT,
            new={"name": "test"},
        )
        key = record.idempotency_key(primary_key_fields=["id"])
        assert key == "0/FF:public.x:"
