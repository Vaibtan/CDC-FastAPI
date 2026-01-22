"""
WalStream Ingestor - Captures PostgreSQL WAL changes with retention policies.

This module implements the core CDC (Change Data Capture) functionality,
reading from PostgreSQL logical replication and dual-writing to Redis
and Kafka for different consumption patterns.
"""
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Optional

import psycopg2
import redis
from kafka import KafkaProducer
from kafka.errors import KafkaError
from psycopg2.extras import LogicalReplicationConnection
from prometheus_client import Counter, Histogram, Gauge, start_http_server

from walstream_proto.v1 import ChangeRecord

# ==========================================================================
# Configuration
# ==========================================================================

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_USER = os.getenv("POSTGRES_USER", "repluser")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "replpass")
POSTGRES_DB = os.getenv("POSTGRES_DB", "walstreamdb")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "walstream.archive")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_STREAM = os.getenv("REDIS_STREAM", "walstream:events")
REDIS_STREAM_MAXLEN = int(os.getenv("REDIS_STREAM_MAXLEN", "100000"))

REPLICATION_SLOT = os.getenv("REPLICATION_SLOT", "walstream_slot")
TABLES_FILTER = os.getenv("TABLES_FILTER", "public.*")

METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

# ==========================================================================
# Logging
# ==========================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingestor")

# ==========================================================================
# Prometheus Metrics
# ==========================================================================

EVENTS_INGESTED = Counter(
    "walstream_events_ingested_total",
    "Total events ingested from PostgreSQL WAL",
    ["table", "operation"],
)

EVENTS_PUBLISHED_REDIS = Counter(
    "walstream_events_published_redis_total", "Events published to Redis stream"
)

EVENTS_PUBLISHED_KAFKA = Counter(
    "walstream_events_published_kafka_total", "Events published to Kafka"
)

INGEST_ERRORS = Counter(
    "walstream_ingest_errors_total", "Total ingestion errors", ["error_type"]
)

REDIS_STREAM_LENGTH = Gauge(
    "walstream_redis_stream_length", "Current Redis stream length"
)

WAL_LAG_BYTES = Gauge("walstream_wal_lag_bytes", "WAL replication lag in bytes")

INGEST_LATENCY = Histogram(
    "walstream_ingest_latency_seconds",
    "Time from WAL commit to publish complete",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ==========================================================================
# WAL Parsing
# ==========================================================================

ACTION_MAP: dict[str, str] = {
    "I": "INSERT",
    "U": "UPDATE",
    "D": "DELETE",
    "T": "TRUNCATE",
}


def parse_wal2json_v2(payload: dict, lsn: int) -> list[ChangeRecord]:
    """
    Parse wal2json format-version 2 payload into ChangeRecord messages.

    wal2json format-version 2 structure:
    {
        "action": "I",
        "timestamp": "2024-01-15 10:30:00.123456+00",
        "schema": "public",
        "table": "events",
        "columns": [
            {"name": "id", "type": "integer", "value": 1},
            {"name": "name", "type": "text", "value": "test"}
        ],
        "identity": [
            {"name": "id", "type": "integer", "value": 1}
        ]
    }

    Returns a list because one WAL message can contain multiple changes.
    """
    records: list[ChangeRecord] = []

    # Parse timestamp
    timestamp_str = payload.get("timestamp", "")
    try:
        if timestamp_str:
            # Handle both space and T separator, with or without timezone
            ts = timestamp_str.replace(" ", "T")
            # Remove timezone info for parsing if present
            if "+" in ts:
                ts = ts.split("+")[0]
            elif "-" in ts and ts.count("-") > 2:
                # Handle negative timezone offset
                parts = ts.rsplit("-", 1)
                if len(parts[1]) <= 5:  # Timezone offset like "00:00"
                    ts = parts[0]
            dt = datetime.fromisoformat(ts)
            commit_time_ms = int(dt.timestamp() * 1000)
        else:
            commit_time_ms = int(time.time() * 1000)
    except ValueError as e:
        logger.warning("Could not parse timestamp '%s': %s", timestamp_str, e)
        commit_time_ms = int(time.time() * 1000)

    # Process each change in the payload
    for change in payload.get("change", []):
        action = change.get("kind", change.get("action", ""))
        operation = ACTION_MAP.get(action, action)

        schema = change.get("schema", "public")
        table = change.get("table", "unknown")

        old_values: dict[str, str] = {}
        new_values: dict[str, str] = {}

        # Extract new values (INSERT, UPDATE)
        # Format 1: columns array with objects
        if "columns" in change:
            for col in change.get("columns", []):
                col_name = col.get("name", "")
                col_value = col.get("value")
                if col_value is not None:
                    new_values[col_name] = str(col_value)
        # Format 2: columnnames and columnvalues arrays
        elif "columnnames" in change and "columnvalues" in change:
            names = change.get("columnnames", [])
            values = change.get("columnvalues", [])
            for name, value in zip(names, values):
                if value is not None:
                    new_values[name] = str(value)

        # Extract old values (UPDATE, DELETE)
        # Format 1: identity array with objects
        if "identity" in change:
            for col in change.get("identity", []):
                col_name = col.get("name", "")
                col_value = col.get("value")
                if col_value is not None:
                    old_values[col_name] = str(col_value)
        # Format 2: oldkeys object with keynames and keyvalues
        elif "oldkeys" in change:
            old_keys = change.get("oldkeys", {})
            names = old_keys.get("keynames", [])
            values = old_keys.get("keyvalues", [])
            for name, value in zip(names, values):
                if value is not None:
                    old_values[name] = str(value)

        record = ChangeRecord(
            lsn=str(lsn),
            commit_time=commit_time_ms,
            table=f"{schema}.{table}",
            operation=operation,
            old=old_values,
            new=new_values,
        )

        records.append(record)

    return records


# ==========================================================================
# Ingestor Class
# ==========================================================================


class Ingestor:
    """Main ingestor managing connections and event processing."""

    def __init__(self) -> None:
        self.redis_client: Optional[redis.Redis] = None
        self.kafka_producer: Optional[KafkaProducer] = None
        self.pg_conn = None
        self.pg_cursor = None
        self.running = False
        self._event_count = 0

    def connect_redis(self) -> None:
        """Establish Redis connection with retry."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                self.redis_client = redis.from_url(REDIS_URL)
                self.redis_client.ping()
                logger.info("Connected to Redis")
                return
            except redis.ConnectionError as e:
                logger.warning(
                    "Redis attempt %d/%d failed: %s", attempt + 1, max_retries, e
                )
                INGEST_ERRORS.labels(error_type="redis_connection").inc()
                time.sleep(2**attempt)
        raise ConnectionError("Could not connect to Redis after retries")

    def connect_kafka(self) -> None:
        """Establish Kafka producer with idempotence enabled."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                self.kafka_producer = KafkaProducer(
                    bootstrap_servers=[KAFKA_BROKER],
                    value_serializer=None,  # We serialize protobuf ourselves
                    acks="all",
                    retries=3,
                    max_in_flight_requests_per_connection=1,
                    enable_idempotence=True,  # Prevents duplicates from retries
                )
                logger.info("Connected to Kafka")
                return
            except KafkaError as e:
                logger.warning(
                    "Kafka attempt %d/%d failed: %s", attempt + 1, max_retries, e
                )
                INGEST_ERRORS.labels(error_type="kafka_connection").inc()
                time.sleep(2**attempt)
        raise ConnectionError("Could not connect to Kafka after retries")

    def connect_postgres(self) -> None:
        """Establish PostgreSQL replication connection."""
        self.pg_conn = psycopg2.connect(
            host=POSTGRES_HOST,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            dbname=POSTGRES_DB,
            connection_factory=LogicalReplicationConnection,
        )
        self.pg_cursor = self.pg_conn.cursor()

        try:
            self.pg_cursor.create_replication_slot(
                REPLICATION_SLOT, output_plugin="wal2json"
            )
            logger.info("Created replication slot: %s", REPLICATION_SLOT)
        except psycopg2.ProgrammingError as e:
            if "already exists" in str(e):
                logger.info("Replication slot %s already exists", REPLICATION_SLOT)
            else:
                raise

        logger.info("Connected to PostgreSQL")

    def publish_to_redis(self, record: ChangeRecord) -> str:
        """Publish ChangeRecord to Redis Stream with MAXLEN trimming."""
        serialized = record.SerializeToString()

        message_id = self.redis_client.xadd(
            REDIS_STREAM,
            {
                "payload": serialized,
                "time_ms": str(record.commit_time),
                "table": record.table,
                "operation": record.operation,
            },
            maxlen=REDIS_STREAM_MAXLEN,
            approximate=True,  # Use ~ for better performance
        )

        EVENTS_PUBLISHED_REDIS.inc()

        # Update stream length gauge periodically (every 100 events)
        self._event_count += 1
        if self._event_count % 100 == 0:
            try:
                length = self.redis_client.xlen(REDIS_STREAM)
                REDIS_STREAM_LENGTH.set(length)
            except redis.RedisError:
                pass  # Non-critical metric update

        return message_id.decode() if isinstance(message_id, bytes) else str(message_id)

    def publish_to_kafka(self, record: ChangeRecord) -> None:
        """Publish ChangeRecord to Kafka topic."""
        serialized = record.SerializeToString()

        future = self.kafka_producer.send(
            KAFKA_TOPIC,
            value=serialized,
            key=record.table.encode("utf-8"),
        )
        # Wait for send to complete (synchronous for guaranteed ordering)
        future.get(timeout=10)
        EVENTS_PUBLISHED_KAFKA.inc()

    def process_message(self, msg) -> bool:
        """Process a single replication message."""
        start_time = time.time()

        try:
            # Acknowledge the message position
            msg.cursor.send_feedback(flush_lsn=msg.data_start)

            # Parse WAL payload
            payload = json.loads(msg.payload)
            records = parse_wal2json_v2(payload, msg.data_start)

            for record in records:
                EVENTS_INGESTED.labels(
                    table=record.table, operation=record.operation
                ).inc()

                # Dual-write to both destinations
                redis_id = self.publish_to_redis(record)
                self.publish_to_kafka(record)

                logger.info(
                    "Ingested: %s on %s (LSN: %s, Redis: %s)",
                    record.operation,
                    record.table,
                    record.lsn,
                    redis_id,
                )

            INGEST_LATENCY.observe(time.time() - start_time)
            return True

        except json.JSONDecodeError as e:
            INGEST_ERRORS.labels(error_type="json_parse").inc()
            logger.error("JSON parse error: %s", e)
            return False
        except Exception as e:
            INGEST_ERRORS.labels(error_type="unknown").inc()
            logger.error("Error processing message: %s", e, exc_info=True)
            return False

    def start(self) -> None:
        """Start the ingestor."""
        logger.info("Starting WalStream Ingestor...")

        # Start metrics server
        start_http_server(METRICS_PORT)
        logger.info("Metrics available on port %d", METRICS_PORT)

        # Connect to all services
        self.connect_redis()
        self.connect_kafka()
        self.connect_postgres()

        # Configure wal2json options
        options = {
            "format-version": "2",
            "include-xids": "1",
            "include-timestamp": "1",
            "include-schemas": "1",
            "include-types": "1",
            "add-tables": TABLES_FILTER,
        }

        self.pg_cursor.start_replication(
            slot_name=REPLICATION_SLOT,
            options=options,
            decode=True,
        )

        logger.info("Started replication from slot: %s", REPLICATION_SLOT)
        self.running = True

        # Main consumption loop
        self.pg_cursor.consume_stream(self.process_message)

    def stop(self) -> None:
        """Stop the ingestor gracefully."""
        logger.info("Stopping ingestor...")
        self.running = False

        if self.kafka_producer:
            self.kafka_producer.flush()
            self.kafka_producer.close()

        if self.pg_cursor:
            self.pg_cursor.close()
        if self.pg_conn:
            self.pg_conn.close()

        logger.info("Ingestor stopped")


def main() -> None:
    """Main entry point."""
    ingestor = Ingestor()

    def signal_handler(sig, frame) -> None:
        logger.info("Received signal %s", sig)
        ingestor.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            ingestor.start()
        except KeyboardInterrupt:
            ingestor.stop()
            break
        except Exception as e:
            logger.error("Ingestor crashed: %s", e, exc_info=True)
            INGEST_ERRORS.labels(error_type="crash").inc()
            time.sleep(5)


if __name__ == "__main__":
    main()
