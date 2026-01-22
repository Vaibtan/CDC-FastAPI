"""Routes replay requests to Redis or Kafka based on time window."""
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from aiokafka import AIOKafkaConsumer, TopicPartition
import redis.asyncio as aioredis

from app.config import get_settings
from walstream_proto.v1 import ChangeRecord

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class ReplayEvent:
    """Unified event representation from any source."""

    message_id: str  # Redis stream ID or Kafka partition:offset
    payload: bytes  # Serialized ChangeRecord
    commit_time_ms: int
    table: str
    operation: str


class ReplaySource(ABC):
    """Abstract replay source interface."""

    @abstractmethod
    async def count_events(self, start_ms: int, end_ms: int) -> int:
        """Count events in time range (may be approximate for large ranges)."""
        pass

    @abstractmethod
    async def stream_events(
        self,
        start_ms: int,
        end_ms: int,
        checkpoint: Optional[str] = None,
    ) -> AsyncIterator[ReplayEvent]:
        """Stream events from checkpoint, yielding one at a time."""
        pass

    @abstractmethod
    def source_name(self) -> str:
        """Return source identifier."""
        pass

    async def close(self) -> None:
        """Cleanup resources. Override if needed."""
        pass


class RedisReplaySource(ReplaySource):
    """Replay from Redis stream (for recent/small windows)."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client
        self.stream = settings.redis_stream

    def source_name(self) -> str:
        return "redis"

    async def count_events(self, start_ms: int, end_ms: int) -> int:
        """Count via XRANGE (fine for small windows)."""
        events = await self.redis.xrange(
            self.stream,
            min=str(start_ms),
            max=str(end_ms),
        )
        return len(events)

    async def stream_events(
        self,
        start_ms: int,
        end_ms: int,
        checkpoint: Optional[str] = None,
    ) -> AsyncIterator[ReplayEvent]:
        """Stream events using cursor-based XRANGE."""
        cursor = checkpoint if checkpoint else str(start_ms)
        batch_size = 100

        while True:
            # Use exclusive start to avoid re-processing checkpoint
            events = await self.redis.xrange(
                self.stream,
                min=f"({cursor}" if checkpoint else cursor,
                max=str(end_ms),
                count=batch_size,
            )

            if not events:
                break

            for message_id, data in events:
                msg_id = (
                    message_id.decode()
                    if isinstance(message_id, bytes)
                    else str(message_id)
                )
                cursor = msg_id

                yield ReplayEvent(
                    message_id=msg_id,
                    payload=data.get(b"payload", b""),
                    commit_time_ms=int(data.get(b"time_ms", 0)),
                    table=data.get(b"table", b"").decode(),
                    operation=data.get(b"operation", b"").decode(),
                )

            if len(events) < batch_size:
                break

            # Reset checkpoint flag after first batch
            checkpoint = cursor


class KafkaReplaySource(ReplaySource):
    """Replay from Kafka using aiokafka (async-native, non-blocking)."""

    def __init__(self, bootstrap_servers: str, topic: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self._consumer: Optional[AIOKafkaConsumer] = None

    def source_name(self) -> str:
        return "kafka"

    async def _get_consumer(self, group_id: str) -> AIOKafkaConsumer:
        """Get or create consumer with unique group ID."""
        if not self._consumer:
            self._consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=group_id,
                enable_auto_commit=False,
                auto_offset_reset="earliest",
            )
            await self._consumer.start()
        return self._consumer

    async def count_events(self, start_ms: int, end_ms: int) -> int:
        """Approximate count using offset differences."""
        consumer = await self._get_consumer(f"count-{uuid.uuid4().hex[:8]}")

        try:
            partitions_info = await consumer.partitions_for_topic(self.topic)
            if not partitions_info:
                return 0

            partitions = [TopicPartition(self.topic, p) for p in partitions_info]

            # Get offsets for start timestamp
            timestamps = {tp: start_ms for tp in partitions}
            start_offsets = await consumer.offsets_for_times(timestamps)

            # Get offsets for end timestamp
            timestamps = {tp: end_ms for tp in partitions}
            end_offsets = await consumer.offsets_for_times(timestamps)

            total = 0
            for tp in partitions:
                s = start_offsets.get(tp)
                e = end_offsets.get(tp)
                if s and e:
                    total += max(0, e.offset - s.offset)

            return total
        except Exception as e:
            logger.warning("Error counting Kafka events: %s", e)
            return 0

    async def stream_events(
        self,
        start_ms: int,
        end_ms: int,
        checkpoint: Optional[str] = None,
    ) -> AsyncIterator[ReplayEvent]:
        """Stream events using async iteration (yields to event loop)."""
        consumer = await self._get_consumer(f"replay-{uuid.uuid4().hex[:8]}")

        try:
            partitions_info = await consumer.partitions_for_topic(self.topic)
            if not partitions_info:
                return

            partitions = [TopicPartition(self.topic, p) for p in partitions_info]
            consumer.assign(partitions)

            # Seek to checkpoint or timestamp
            if checkpoint:
                # Checkpoint format: {"0": 123, "1": 456}
                offsets = json.loads(checkpoint)
                for p_str, offset in offsets.items():
                    tp = TopicPartition(self.topic, int(p_str))
                    consumer.seek(tp, offset + 1)
            else:
                # Seek to start timestamp
                timestamps = {tp: start_ms for tp in partitions}
                offsets = await consumer.offsets_for_times(timestamps)
                for tp, offset_and_ts in offsets.items():
                    if offset_and_ts:
                        consumer.seek(tp, offset_and_ts.offset)

            # Async iteration - properly yields to event loop
            async for message in consumer:
                if message.timestamp > end_ms:
                    break

                record = ChangeRecord()
                record.ParseFromString(message.value)

                yield ReplayEvent(
                    message_id=f"{message.partition}:{message.offset}",
                    payload=message.value,
                    commit_time_ms=record.commit_time,
                    table=record.table,
                    operation=record.operation,
                )

        except Exception as e:
            logger.error("Error streaming Kafka events: %s", e)
            raise

    async def close(self) -> None:
        """Stop the consumer."""
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None


class ReplaySourceRouter:
    """Selects appropriate replay source based on time window."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        kafka_source: KafkaReplaySource,
    ) -> None:
        self.redis_source = RedisReplaySource(redis_client)
        self.kafka_source = kafka_source
        self.threshold_ms = settings.redis_replay_threshold_ms

    def get_source(self, start_time_ms: int, end_time_ms: int) -> ReplaySource:
        """
        Route to appropriate source:
        - Redis: Recent data (< threshold) AND small window (< threshold)
        - Kafka: Historical data OR large window
        """
        now_ms = int(time.time() * 1000)
        age_ms = now_ms - start_time_ms
        window_ms = end_time_ms - start_time_ms

        if age_ms < self.threshold_ms and window_ms < self.threshold_ms:
            logger.info("Using Redis source (age=%dms, window=%dms)", age_ms, window_ms)
            return self.redis_source
        else:
            logger.info("Using Kafka source (age=%dms, window=%dms)", age_ms, window_ms)
            return self.kafka_source

    async def close(self) -> None:
        """Cleanup resources."""
        await self.kafka_source.close()
