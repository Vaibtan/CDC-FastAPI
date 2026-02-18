"""Event streaming and monitoring endpoints."""
import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, Settings
from app.database import get_read_db
from app.api.deps import CurrentUser, ws_authenticate
from walstream_proto.v1 import ChangeRecord
from walstream_proto.models import ChangeRecordModel, EventStreamMessage

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stream/stats")
async def get_stream_stats(
    current_user: CurrentUser,
    settings: Settings = Depends(lambda: get_settings()),
) -> dict:
    """
    Get Redis stream statistics.

    Returns current stream length, first/last entry IDs, and consumer groups.
    """
    try:
        redis_client = aioredis.from_url(settings.redis_url)

        # Get stream info
        stream_info = await redis_client.xinfo_stream(settings.redis_stream)
        groups_info = await redis_client.xinfo_groups(settings.redis_stream)

        await redis_client.close()

        return {
            "stream": settings.redis_stream,
            "length": stream_info.get("length", 0),
            "first_entry": stream_info.get("first-entry"),
            "last_entry": stream_info.get("last-entry"),
            "consumer_groups": [
                {
                    "name": g.get("name"),
                    "consumers": g.get("consumers"),
                    "pending": g.get("pending"),
                    "last_delivered_id": g.get("last-delivered-id"),
                }
                for g in groups_info
            ],
        }
    except Exception as e:
        logger.error(f"Error getting stream stats: {e}")
        return {
            "stream": settings.redis_stream,
            "error": str(e),
        }


@router.get("/recent")
async def get_recent_events(
    current_user: CurrentUser,
    count: int = Query(10, ge=1, le=100),
    table_filter: Optional[str] = Query(None),
    settings: Settings = Depends(lambda: get_settings()),
) -> list[dict]:
    """
    Get recent events from the Redis stream.

    Optionally filter by table name pattern.
    """
    try:
        redis_client = aioredis.from_url(settings.redis_url)

        # Use XREVRANGE to get most recent events
        events = await redis_client.xrevrange(
            settings.redis_stream,
            count=count * 2 if table_filter else count,  # Fetch more if filtering
        )

        await redis_client.close()

        result = []
        for message_id, data in events:
            msg_id = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
            table = data.get(b"table", b"").decode()

            # Apply table filter if specified
            if table_filter and table_filter not in table:
                continue

            # Parse the protobuf payload
            try:
                payload = data.get(b"payload", b"")
                record = ChangeRecord()
                record.ParseFromString(payload)
                model = ChangeRecordModel.from_protobuf(record)

                result.append({
                    "id": msg_id,
                    "event": model.model_dump(),
                })
            except Exception as e:
                logger.warning(f"Could not parse event {msg_id}: {e}")
                result.append({
                    "id": msg_id,
                    "table": table,
                    "operation": data.get(b"operation", b"").decode(),
                    "parse_error": str(e),
                })

            if len(result) >= count:
                break

        return result
    except Exception as e:
        logger.error(f"Error getting recent events: {e}")
        return []


@router.websocket("/ws")
async def websocket_event_stream(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_read_db),
    settings: Settings = Depends(lambda: get_settings()),
) -> None:
    """
    WebSocket endpoint for real-time event streaming.

    Clients can subscribe to live CDC events from the Redis stream.
    Requires ?token=<jwt> query parameter for authentication.
    """
    # Authenticate before accepting the connection
    try:
        user = await ws_authenticate(websocket, db)
    except Exception:
        return

    await websocket.accept()
    logger.info("WebSocket client connected")

    redis_client = None
    try:
        redis_client = aioredis.from_url(settings.redis_url)

        # Create a unique consumer group for this connection
        consumer_group = f"ws-{id(websocket)}"
        consumer_name = "ws-consumer"

        try:
            await redis_client.xgroup_create(
                settings.redis_stream,
                consumer_group,
                id="$",  # Only new messages
                mkstream=True,
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        # Stream events
        while True:
            try:
                # Read new messages
                messages = await redis_client.xreadgroup(
                    consumer_group,
                    consumer_name,
                    {settings.redis_stream: ">"},
                    count=10,
                    block=5000,  # 5 second timeout
                )

                if messages:
                    for stream_name, stream_messages in messages:
                        for message_id, data in stream_messages:
                            msg_id = message_id.decode() if isinstance(message_id, bytes) else str(message_id)

                            # Parse and send event
                            try:
                                payload = data.get(b"payload", b"")
                                record = ChangeRecord()
                                record.ParseFromString(payload)
                                model = ChangeRecordModel.from_protobuf(record)

                                event_msg = EventStreamMessage(
                                    event_type="change_event",
                                    payload={
                                        "id": msg_id,
                                        "event": model.model_dump(),
                                    },
                                )
                                await websocket.send_json(event_msg.model_dump(mode="json"))

                            except Exception as e:
                                logger.warning(f"Could not parse event {msg_id}: {e}")

                            # Acknowledge message
                            await redis_client.xack(
                                settings.redis_stream, consumer_group, message_id
                            )
                else:
                    # Send heartbeat
                    heartbeat = EventStreamMessage(
                        event_type="heartbeat",
                        payload={"timestamp": datetime.utcnow().isoformat()},
                    )
                    await websocket.send_json(heartbeat.model_dump(mode="json"))

            except WebSocketDisconnect:
                logger.info("WebSocket client disconnected")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket stream: {e}")
                await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if redis_client:
            # Cleanup consumer group
            try:
                await redis_client.xgroup_destroy(settings.redis_stream, consumer_group)
            except Exception:
                pass
            await redis_client.close()
        logger.info("WebSocket connection closed")
