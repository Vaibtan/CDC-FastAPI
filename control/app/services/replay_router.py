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

    @staticmethod
    def _parse_checkpoint(checkpoint: str) -> dict[int, int]:
        """Parse a Kafka checkpoint string into {partition: offset} map.

        Supports two formats:
        - JSON map: '{"0": 123, "1": 456}'
        - Single partition:offset: '0:123'
        """
        try:
            parsed = json.loads(checkpoint)
            return {int(k): int(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, AttributeError):
            # Fallback: "partition:offset" format
            if ":" in checkpoint:
                parts = checkpoint.split(":", 1)
                return {int(parts[0]): int(parts[1])}
            raise ValueError(f"Unrecognized checkpoint format: {checkpoint}")

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

            if checkpoint:
                offsets = self._parse_checkpoint(checkpoint)

                # Seek checkpointed partitions past their saved offset
                for partition, offset in offsets.items():
                    tp = TopicPartition(self.topic, partition)
                    if tp in partitions:
                        consumer.seek(tp, offset + 1)

                # Seek remaining (non-checkpointed) partitions to start_ms
                uncheckpointed = [
                    tp for tp in partitions if tp.partition not in offsets
                ]
                if uncheckpointed:
                    ts_map = {tp: start_ms for tp in uncheckpointed}
                    ts_offsets = await consumer.offsets_for_times(ts_map)
                    for tp, offset_and_ts in ts_offsets.items():
                        if offset_and_ts:
                            consumer.seek(tp, offset_and_ts.offset)
                        else:
                            # No offset >= start_ms for this partition, so there are
                            # no records in-range. Move to end to avoid replaying old data.
                            end_offsets = await consumer.end_offsets([tp])
                            consumer.seek(tp, end_offsets[tp])
            else:
                # No checkpoint — seek all partitions to start timestamp
                timestamps = {tp: start_ms for tp in partitions}
                offsets = await consumer.offsets_for_times(timestamps)
                for tp, offset_and_ts in offsets.items():
                    if offset_and_ts:
                        consumer.seek(tp, offset_and_ts.offset)
                    else:
                        # No offset >= start_ms for this partition, so there are
                        # no records in-range. Move to end to avoid replaying old data.
                        end_offsets = await consumer.end_offsets([tp])
                        consumer.seek(tp, end_offsets[tp])

            # Snapshot high-water marks at replay start so bounded replays can
            # terminate even if producers keep writing to the topic.
            end_offsets = await consumer.end_offsets(partitions)
            if not isinstance(end_offsets, dict):
                end_offsets = {}

            completed_partitions: set[int] = set()

            async def mark_completed_if_at_end(tp: TopicPartition) -> None:
                partition_end = end_offsets.get(tp)
                if not isinstance(partition_end, int):
                    return
                try:
                    position = await consumer.position(tp)
                except Exception:
                    return
                if isinstance(position, int) and position >= partition_end:
                    completed_partitions.add(tp.partition)

            # Partitions with no records in-range may already be at end.
            for tp in partitions:
                await mark_completed_if_at_end(tp)

            if len(completed_partitions) == len(partitions):
                return

            # Async iteration - properly yields to event loop.
            # Do NOT break on the first out-of-range message, because Kafka is
            # ordered per-partition (not globally by timestamp).
            async for message in consumer:
                tp = TopicPartition(self.topic, message.partition)

                if message.partition in completed_partitions:
                    continue

                if message.timestamp is not None and message.timestamp > end_ms:
                    completed_partitions.add(message.partition)
                else:
                    record = ChangeRecord()
                    record.ParseFromString(message.value)

                    yield ReplayEvent(
                        message_id=f"{message.partition}:{message.offset}",
                        payload=message.value,
                        commit_time_ms=record.commit_time,
                        table=record.table,
                        operation=record.operation,
                    )

                await mark_completed_if_at_end(tp)

                if len(completed_partitions) == len(partitions):
                    break

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

    def get_source_by_name(self, name: str) -> ReplaySource:
        """Return the source matching a previously-stored replay_source name.

        Used on job resume to avoid cross-source checkpoint confusion.
        """
        if name == "redis":
            return self.redis_source
        if name == "kafka":
            return self.kafka_source
        raise ValueError(f"Unknown replay source: {name}")

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
