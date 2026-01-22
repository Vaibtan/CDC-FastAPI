"""
Simple Redis stream worker for WalStream CDC.

This is a basic worker implementation for demonstration and testing purposes.
For production use, prefer the job_worker in the control plane which provides
durable execution with checkpointing.
"""
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

import redis
import requests

from walstream_proto.v1 import ChangeRecord

# Configuration
REDIS_STREAM = os.getenv("REDIS_STREAM", "walstream:events")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TARGET_URL = os.getenv("TARGET_URL", "http://mock:8080/replay")
SPEED_FACTOR = float(os.getenv("SPEED_FACTOR", "2.0"))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("worker")


@dataclass
class TimingState:
    """Encapsulates timing state for speed-controlled replay."""

    base_real_time: Optional[float] = None
    base_event_time: Optional[int] = None


def replay_event(
    event: ChangeRecord,
    job_id: str,
    virtual_time: int,
    target_url: str = TARGET_URL,
) -> bool:
    """
    Replay a single event to the target endpoint.

    Args:
        event: The change record to replay.
        job_id: Identifier for the replay job.
        virtual_time: Computed virtual timestamp for the event.
        target_url: URL of the target replay endpoint.

    Returns:
        True if replay succeeded, False otherwise.
    """
    try:
        response = requests.post(
            target_url,
            json={
                "job_id": job_id,
                "event": {
                    "table": event.table,
                    "operation": event.operation,
                    "new": dict(event.new),
                    "time": virtual_time,
                },
            },
            timeout=10,
        )
        response.raise_for_status()
        logger.info(
            "Replayed %s on %s at virtual time %d",
            event.operation,
            event.table,
            virtual_time,
        )
        return True
    except requests.RequestException as e:
        logger.error("Failed to replay: %s", e)
        return False


def main() -> None:
    """Main entry point for the Redis stream worker."""
    redis_client = redis.from_url(REDIS_URL)
    last_id = "0-0"
    timing = TimingState()

    logger.info("Worker starting, consuming from %s", REDIS_STREAM)

    while True:
        streams = redis_client.xread({REDIS_STREAM: last_id}, count=1, block=1000)

        if not streams:
            time.sleep(0.1)
            continue

        stream_key, messages = streams[0]
        msg_id, fields = messages[0]
        last_id = msg_id

        payload = fields[b"payload"]
        event_time_ms = int(fields[b"time_ms"])

        event = ChangeRecord()
        event.ParseFromString(payload)

        # Initialize timing on first event
        if timing.base_real_time is None:
            timing.base_real_time = time.time() * 1000
            timing.base_event_time = event_time_ms

        # Calculate virtual time with speed control
        elapsed_event_ms = event_time_ms - timing.base_event_time
        virtual_time_ms = timing.base_real_time + (elapsed_event_ms / SPEED_FACTOR)

        # Wait if needed for speed-controlled replay
        now_ms = time.time() * 1000
        if virtual_time_ms > now_ms:
            time.sleep((virtual_time_ms - now_ms) / 1000)

        replay_event(event, job_id="demo", virtual_time=int(virtual_time_ms))


if __name__ == "__main__":
    main()