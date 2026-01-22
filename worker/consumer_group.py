"""
Parallel Kafka Consumer Group for WalStream CDC.

This module provides parallel consumption of CDC events from Kafka
using a consumer group pattern with multiple threads.
"""
import logging
import sys
import threading
import time

from kafka import KafkaConsumer
import redis

from walstream_proto.v1 import ChangeRecord

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("consumer_group")


class ParallelConsumer:
    """Manages multiple Kafka consumers in a consumer group."""

    def __init__(
        self,
        group_id: str,
        num_consumers: int = 3,
        kafka_topic: str = "walstream.archive",
        kafka_servers: str = "kafka:9092",
        redis_url: str = "redis://redis:6379/0",
    ):
        self.group_id = group_id
        self.num_consumers = num_consumers
        self.kafka_topic = kafka_topic
        self.kafka_servers = kafka_servers
        self.redis = redis.from_url(redis_url)
        self.consumers: list[threading.Thread] = []
        self._shutdown = threading.Event()

    def process_message(self, message, consumer_id: int) -> None:
        """Process a single Kafka message."""
        try:
            event = ChangeRecord()
            event.ParseFromString(message.value)

            logger.info(
                "[consumer-%d] Processing: %s@%d",
                consumer_id,
                event.table,
                event.commit_time,
            )

            # Simulate processing time based on table
            if "users" in event.table:
                time.sleep(0.2)
            else:
                time.sleep(0.05)

            # Track progress in Redis
            self.redis.hincrby(
                f"consumer:{self.group_id}:progress",
                f"consumer_{consumer_id}",
                1,
            )

        except Exception as e:
            logger.error("[consumer-%d] Error: %s", consumer_id, e)

    def start_consumer(self, consumer_id: int) -> None:
        """Start a single consumer thread."""
        consumer = KafkaConsumer(
            self.kafka_topic,
            bootstrap_servers=[self.kafka_servers],
            group_id=self.group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=None,
        )

        logger.info("[consumer-%d] Started in group %s", consumer_id, self.group_id)

        try:
            for message in consumer:
                if self._shutdown.is_set():
                    break
                self.process_message(message, consumer_id)
        finally:
            consumer.close()
            logger.info("[consumer-%d] Stopped", consumer_id)

    def start_all(self) -> None:
        """Start all consumer threads."""
        for i in range(self.num_consumers):
            thread = threading.Thread(
                target=self.start_consumer,
                args=(i,),
                name=f"consumer-{self.group_id}-{i}",
            )
            thread.daemon = True
            self.consumers.append(thread)
            thread.start()

    def stop_all(self) -> None:
        """Signal all consumers to stop."""
        self._shutdown.set()
        for thread in self.consumers:
            thread.join(timeout=5.0)

    def get_progress(self) -> dict[bytes, bytes]:
        """Get progress for all consumers in the group."""
        return self.redis.hgetall(f"consumer:{self.group_id}:progress")


def main() -> None:
    """Main entry point for running consumer groups."""
    analytics_consumers = ParallelConsumer("analytics-group", num_consumers=2)
    backup_consumers = ParallelConsumer("backup-group", num_consumers=1)

    logger.info("Starting analytics consumer group (2 consumers)...")
    analytics_consumers.start_all()

    logger.info("Starting backup consumer group (1 consumer)...")
    backup_consumers.start_all()

    try:
        while True:
            time.sleep(5)
            logger.info("Analytics progress: %s", analytics_consumers.get_progress())
            logger.info("Backup progress: %s", backup_consumers.get_progress())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        analytics_consumers.stop_all()
        backup_consumers.stop_all()


if __name__ == "__main__":
    main()
