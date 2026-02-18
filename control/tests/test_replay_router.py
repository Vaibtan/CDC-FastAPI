"""Unit tests for replay source routing and checkpoint parsing."""
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.replay_router import (
    KafkaReplaySource,
    RedisReplaySource,
    ReplaySourceRouter,
)


class TestReplaySourceRouter:
    """Test source selection logic."""

    def _make_router(self, threshold_ms: int = 3600000):
        redis_client = AsyncMock()
        kafka_source = MagicMock(spec=KafkaReplaySource)
        kafka_source.source_name.return_value = "kafka"

        with patch("app.services.replay_router.settings") as mock_settings:
            mock_settings.redis_replay_threshold_ms = threshold_ms
            mock_settings.redis_stream = "walstream:events"
            router = ReplaySourceRouter(redis_client, kafka_source)

        return router

    def test_recent_small_window_uses_redis(self):
        """Window within threshold and age within threshold -> Redis."""
        router = self._make_router(threshold_ms=3600000)
        now_ms = int(time.time() * 1000)
        # 30 minutes ago, 10-minute window
        start = now_ms - 1800000
        end = now_ms - 1200000

        source = router.get_source(start, end)
        assert source.source_name() == "redis"

    def test_old_data_uses_kafka(self):
        """Start time older than threshold -> Kafka."""
        router = self._make_router(threshold_ms=3600000)
        now_ms = int(time.time() * 1000)
        # 2 hours ago
        start = now_ms - 7200000
        end = now_ms - 3600001

        source = router.get_source(start, end)
        assert source.source_name() == "kafka"

    def test_large_window_uses_kafka(self):
        """Window larger than threshold -> Kafka."""
        router = self._make_router(threshold_ms=3600000)
        now_ms = int(time.time() * 1000)
        # Recent but 2-hour window
        start = now_ms - 7200000
        end = now_ms

        source = router.get_source(start, end)
        assert source.source_name() == "kafka"

    def test_get_source_by_name_redis(self):
        """get_source_by_name('redis') returns Redis source."""
        router = self._make_router()
        source = router.get_source_by_name("redis")
        assert source.source_name() == "redis"

    def test_get_source_by_name_kafka(self):
        """get_source_by_name('kafka') returns Kafka source."""
        router = self._make_router()
        source = router.get_source_by_name("kafka")
        assert source.source_name() == "kafka"

    def test_get_source_by_name_unknown_raises(self):
        """Unknown source name raises ValueError."""
        router = self._make_router()
        with pytest.raises(ValueError, match="Unknown replay source"):
            router.get_source_by_name("ftp")


class TestKafkaCheckpointParsing:
    """Test KafkaReplaySource._parse_checkpoint."""

    def test_json_format(self):
        """Parse JSON checkpoint: {"0": 100, "1": 200}."""
        cp = json.dumps({"0": 100, "1": 200})
        result = KafkaReplaySource._parse_checkpoint(cp)
        assert result == {0: 100, 1: 200}

    def test_single_partition_format(self):
        """Parse legacy 'partition:offset' format."""
        result = KafkaReplaySource._parse_checkpoint("3:456")
        assert result == {3: 456}

    def test_invalid_format_raises(self):
        """Unrecognized format raises ValueError."""
        with pytest.raises(ValueError, match="Unrecognized checkpoint format"):
            KafkaReplaySource._parse_checkpoint("not-a-checkpoint")

    def test_json_with_string_keys(self):
        """JSON keys are strings, parsed to int."""
        cp = '{"2": 999}'
        result = KafkaReplaySource._parse_checkpoint(cp)
        assert result == {2: 999}

    def test_empty_json_object(self):
        """Empty JSON object is valid (no partitions checkpointed)."""
        result = KafkaReplaySource._parse_checkpoint("{}")
        assert result == {}
