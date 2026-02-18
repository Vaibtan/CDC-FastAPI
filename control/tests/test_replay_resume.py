"""Tests for replay resume semantics across sources.

Matrix:
- Redis checkpoint -> RedisReplaySource resumes at correct offset
- Kafka single-partition checkpoint -> KafkaReplaySource seeks past offset
- Kafka multi-partition checkpoint -> each partition seeks independently
- Sparse partition checkpoint -> uncheckpointed partitions seek by timestamp
- Kafka range-boundary -> partitions with no in-range offset seek to end
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.replay_router import (
    KafkaReplaySource,
    RedisReplaySource,
    ReplaySourceRouter,
)

# Check if aiokafka is a real import (not a MagicMock stub)
try:
    from aiokafka import TopicPartition
    _HAS_AIOKAFKA = not isinstance(TopicPartition, MagicMock)
except (ImportError, TypeError):
    _HAS_AIOKAFKA = False


class TestRedisResume:
    """Redis checkpoint resume behavior."""

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self):
        """Redis uses exclusive range start on resume."""
        redis = AsyncMock()
        redis.xrange = AsyncMock(return_value=[])

        source = RedisReplaySource(redis)

        events = [e async for e in source.stream_events(1000, 9000, checkpoint="5000-0")]

        redis.xrange.assert_called_once()
        call_args = redis.xrange.call_args
        # Exclusive start uses "(" prefix
        min_arg = call_args.kwargs.get("min") or call_args[1][1]
        assert min_arg.startswith("(")

    @pytest.mark.asyncio
    async def test_no_checkpoint_starts_from_begin(self):
        """Without checkpoint, Redis starts from start_ms."""
        redis = AsyncMock()
        redis.xrange = AsyncMock(return_value=[])

        source = RedisReplaySource(redis)

        events = [e async for e in source.stream_events(1000, 9000)]
        redis.xrange.assert_called_once()


class TestKafkaCheckpointParsing:
    """Test checkpoint format parsing."""

    def test_json_multi_partition(self):
        cp = json.dumps({"0": 100, "1": 200, "2": 300})
        result = KafkaReplaySource._parse_checkpoint(cp)
        assert result == {0: 100, 1: 200, 2: 300}

    def test_legacy_single_partition(self):
        result = KafkaReplaySource._parse_checkpoint("0:456")
        assert result == {0: 456}

    def test_empty_json(self):
        result = KafkaReplaySource._parse_checkpoint("{}")
        assert result == {}

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            KafkaReplaySource._parse_checkpoint("garbage")


@pytest.mark.skipif(not _HAS_AIOKAFKA, reason="aiokafka not installed")
class TestKafkaResumeSeek:
    """Test Kafka partition seek behavior on resume."""

    @pytest.mark.asyncio
    async def test_checkpointed_partitions_seek_past_offset(self):
        """Checkpointed partitions should seek to offset + 1."""
        consumer = AsyncMock()
        consumer.partitions_for_topic = AsyncMock(return_value={0, 1})
        consumer.assign = MagicMock()

        seek_calls = {}

        def mock_seek(tp, offset):
            seek_calls[tp.partition] = offset

        consumer.seek = mock_seek
        consumer.offsets_for_times = AsyncMock(return_value={})

        # Make the consumer async-iterable but immediately stop
        async def empty_iter():
            return
            yield  # noqa: unreachable — makes it a generator

        consumer.__aiter__ = lambda self: empty_iter()

        source = KafkaReplaySource("localhost:9092", "test-topic")
        source._consumer = consumer

        checkpoint = json.dumps({"0": 100, "1": 200})
        events = []
        async for e in source.stream_events(1000, 9000, checkpoint=checkpoint):
            events.append(e)

        assert seek_calls.get(0) == 101
        assert seek_calls.get(1) == 201

    @pytest.mark.asyncio
    async def test_uncheckpointed_partitions_seek_by_timestamp(self):
        """Partitions without a checkpoint seek by start_ms timestamp."""
        consumer = AsyncMock()
        consumer.partitions_for_topic = AsyncMock(return_value={0, 1, 2})
        consumer.assign = MagicMock()

        seek_calls = {}

        def mock_seek(tp, offset):
            seek_calls[tp.partition] = offset

        consumer.seek = mock_seek

        tp2 = TopicPartition("test-topic", 2)
        offset_and_ts = MagicMock()
        offset_and_ts.offset = 50
        consumer.offsets_for_times = AsyncMock(return_value={tp2: offset_and_ts})

        async def empty_iter():
            return
            yield

        consumer.__aiter__ = lambda self: empty_iter()

        source = KafkaReplaySource("localhost:9092", "test-topic")
        source._consumer = consumer

        checkpoint = json.dumps({"0": 100})
        events = []
        async for e in source.stream_events(5000, 9000, checkpoint=checkpoint):
            events.append(e)

        assert seek_calls.get(0) == 101
        assert seek_calls.get(2) == 50

    @pytest.mark.asyncio
    async def test_no_offset_at_timestamp_seeks_to_end(self):
        """If offsets_for_times returns None, partition seeks to end."""
        consumer = AsyncMock()
        consumer.partitions_for_topic = AsyncMock(return_value={0})
        consumer.assign = MagicMock()

        seek_calls = {}

        def mock_seek(tp, offset):
            seek_calls[tp.partition] = offset

        consumer.seek = mock_seek

        tp0 = TopicPartition("test-topic", 0)
        consumer.offsets_for_times = AsyncMock(return_value={tp0: None})
        consumer.end_offsets = AsyncMock(return_value={tp0: 999})

        async def empty_iter():
            return
            yield

        consumer.__aiter__ = lambda self: empty_iter()

        source = KafkaReplaySource("localhost:9092", "test-topic")
        source._consumer = consumer

        events = []
        async for e in source.stream_events(5000, 9000, checkpoint=None):
            events.append(e)

        assert seek_calls.get(0) == 999

    @pytest.mark.asyncio
    async def test_out_of_range_partition_does_not_stop_other_partitions(self):
        """A >end message in one partition must not truncate other partitions."""
        from walstream_proto.v1 import ChangeRecord

        consumer = AsyncMock()
        consumer.partitions_for_topic = AsyncMock(return_value={0, 1})
        consumer.assign = MagicMock()
        consumer.seek = MagicMock()

        tp0 = TopicPartition("test-topic", 0)
        tp1 = TopicPartition("test-topic", 1)

        off0 = MagicMock()
        off0.offset = 0
        off1 = MagicMock()
        off1.offset = 0
        consumer.offsets_for_times = AsyncMock(return_value={tp0: off0, tp1: off1})
        consumer.end_offsets = AsyncMock(return_value={tp0: 1, tp1: 1})

        position_map = {0: 0, 1: 0}

        async def mock_position(tp):
            value = position_map[tp.partition]
            position_map[tp.partition] = 1
            return value

        consumer.position = mock_position

        out_record = ChangeRecord(
            lsn="0/10", commit_time=9500, table="public.t", operation="INSERT"
        )
        in_record = ChangeRecord(
            lsn="0/11", commit_time=8000, table="public.t", operation="INSERT"
        )

        msg_out = MagicMock(
            partition=0,
            offset=0,
            timestamp=9500,
            value=out_record.SerializeToString(),
        )
        msg_in = MagicMock(
            partition=1,
            offset=0,
            timestamp=8000,
            value=in_record.SerializeToString(),
        )

        async def iter_messages():
            yield msg_out
            yield msg_in

        consumer.__aiter__ = lambda self: iter_messages()

        source = KafkaReplaySource("localhost:9092", "test-topic")
        source._consumer = consumer

        events = []
        async for event in source.stream_events(5000, 9000, checkpoint=None):
            events.append(event)

        assert len(events) == 1
        assert events[0].message_id == "1:0"
        assert events[0].commit_time_ms == 8000


class TestSourcePinnedResume:
    """Jobs reuse their original replay_source on resume."""

    def test_router_returns_pinned_source(self):
        """get_source_by_name returns the stored source type."""
        redis_client = AsyncMock()
        kafka_source = MagicMock(spec=KafkaReplaySource)
        kafka_source.source_name.return_value = "kafka"

        with patch("app.services.replay_router.settings") as mock_settings:
            mock_settings.redis_replay_threshold_ms = 3600000
            mock_settings.redis_stream = "walstream:events"
            router = ReplaySourceRouter(redis_client, kafka_source)

        assert router.get_source_by_name("kafka").source_name() == "kafka"
        assert router.get_source_by_name("redis").source_name() == "redis"
