"""Tests to ensure proto compatibility across versions."""
import pytest


class TestV1Compatibility:
    """Ensure v1 protos remain backward compatible."""

    def test_change_record_serialization_roundtrip(self):
        """ChangeRecord should serialize/deserialize correctly."""
        from walstream_proto.v1 import ChangeRecord

        original = ChangeRecord(
            lsn="0/1234567",
            commit_time=1704067200000,
            table="public.events",
            operation="INSERT",
            new={"id": "1", "name": "test"},
        )

        serialized = original.SerializeToString()
        restored = ChangeRecord()
        restored.ParseFromString(serialized)

        assert restored.lsn == original.lsn
        assert restored.commit_time == original.commit_time
        assert restored.table == original.table
        assert restored.operation == original.operation
        assert dict(restored.new) == dict(original.new)

    def test_old_serialized_data_still_parses(self):
        """Serialized data from older code should still parse."""
        from walstream_proto.v1 import ChangeRecord

        # Simulate old serialized data (minimal fields)
        old_record = ChangeRecord(
            lsn="0/ABC",
            commit_time=1000,
            table="test",
        )
        old_bytes = old_record.SerializeToString()

        # New code should parse it
        new_record = ChangeRecord()
        new_record.ParseFromString(old_bytes)

        assert new_record.lsn == "0/ABC"
        assert new_record.operation == ""  # Default for missing field

    def test_replay_request_with_all_fields(self):
        """ReplayRequest should handle all fields."""
        from walstream_proto.v1 import ReplayRequest, ChangeRecord

        event = ChangeRecord(
            lsn="0/123",
            commit_time=1704067200000,
            table="public.users",
            operation="UPDATE",
            old={"id": "1", "name": "old"},
            new={"id": "1", "name": "new"},
        )

        request = ReplayRequest(
            job_id="550e8400-e29b-41d4-a716-446655440000",
            event=event,
            virtual_time=1704067200000,
            original_time=1704067200000,
            speed_factor=2.0,
            idempotency_key="0/123:public.users:1",
        )

        serialized = request.SerializeToString()
        restored = ReplayRequest()
        restored.ParseFromString(serialized)

        assert restored.job_id == request.job_id
        assert restored.speed_factor == pytest.approx(2.0)
        assert restored.event.table == "public.users"


class TestPydanticModels:
    """Test Pydantic model functionality."""

    def test_change_record_model_idempotency_key(self):
        """Test idempotency key generation."""
        from walstream_proto.models import ChangeRecordModel, Operation

        record = ChangeRecordModel(
            lsn="0/123",
            commit_time=1704067200000,
            table="public.users",
            operation=Operation.INSERT,
            new={"id": "42", "name": "test"},
        )

        key = record.idempotency_key(primary_key_fields=["id"])
        assert key == "0/123:public.users:42"

    def test_replay_job_create_validation(self):
        """Test job creation validation."""
        from datetime import datetime, timedelta
        from walstream_proto.models import ReplayJobCreate

        now = datetime.utcnow()

        # Valid job
        job = ReplayJobCreate(
            start_time=now - timedelta(hours=1),
            end_time=now,
            speed_factor=2.0,
        )
        assert job.speed_factor == 2.0

        # Invalid: end before start
        with pytest.raises(ValueError, match="end_time must be after start_time"):
            ReplayJobCreate(
                start_time=now,
                end_time=now - timedelta(hours=1),
            )

    def test_replay_job_response_computed_fields(self):
        """Test computed fields in job response."""
        from datetime import datetime
        from uuid import uuid4
        from walstream_proto.models import ReplayJobResponse, JobStatus

        job = ReplayJobResponse(
            id=uuid4(),
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            speed_factor=1.0,
            target_type="grpc",
            target_url=None,
            status=JobStatus.RUNNING,
            events_total=100,
            events_processed=50,
            events_failed=5,
            events_skipped_dedup=2,
            error_message=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            completed_at=None,
        )

        assert job.progress_percent == 50.0
        assert job.is_terminal is False

        # Test terminal state
        job.status = JobStatus.COMPLETED
        assert job.is_terminal is True
