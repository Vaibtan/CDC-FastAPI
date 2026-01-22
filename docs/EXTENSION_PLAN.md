# WalStream CDC Extension Plan

## Executive Summary

This document provides a comprehensive, incremental roadmap for extending and improving the WalStream CDC (Change Data Capture) system. The plan addresses critical bugs, architectural improvements, scalability concerns, security requirements, and feature additions while maintaining system stability at every step.

**Key Objectives:**
1. Replace Django control panel with FastAPI
2. Fix critical bugs in existing components
3. Establish proper protobuf packaging with versioning strategy
4. Define precise delivery semantics (at-least-once with idempotency)
5. Implement scalable replay architecture (Kafka for history, Redis for live tail)
6. Add security/authentication as first-class concern
7. Implement comprehensive observability with actionable alerting

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Target Architecture](#2-target-architecture)
3. [Design Decisions & Delivery Semantics](#3-design-decisions--delivery-semantics)
4. [Critical Implementation Notes](#4-critical-implementation-notes)
5. [Implementation Phases](#5-implementation-phases)
6. [Security & Authentication](#6-security--authentication)
7. [Observability, Metrics & Alerting](#7-observability-metrics--alerting)
8. [Testing Strategy](#8-testing-strategy)
9. [Developer Experience](#9-developer-experience)
10. [Appendix](#10-appendix)

---

## 1. Current State Analysis

### 1.1 Architecture Overview (As-Is)

```
+-------------------+     +-------------------+     +-------------------+
|   PostgreSQL      |---->|    Ingestor       |---->|  Redis Stream     |
| (WAL/wal2json)    |     |                   |     |walstream:      |
+-------------------+     |                   |     |events             |
                          |                   |     +---------+---------+
                          |                   |               |
                          |                   |     +---------v---------+
                          |                   |---->|     Kafka         |
                          +-------------------+     |walstream.      |
                                                    |archive            |
                                                    +---------+---------+
                                                              |
+-------------------+     +-------------------+               |
|  Django Admin     |---->|  gRPC Replayer    |<--------------+
| (Control Panel)   |     |                   |
+-------------------+     +-------------------+
                                  ^
                                  |
                          +-------+-------+
                          |    Worker     |
                          | (HTTP replay) |
                          +---------------+
```

### 1.2 Component Analysis

| Component | Location | Purpose | Issues Found |
|-----------|----------|---------|--------------|
| Ingestor | `ingestor/ingestor.py` | Captures WAL changes, publishes to Redis/Kafka | Missing `operation`, `old`, `new` fields from wal2json |
| Worker (main) | `worker/main.py` | Consumes Redis, replays via HTTP | Uses hardcoded SPEED_FACTOR, HTTP-only target |
| Worker (consumer_group) | `worker/consumer_group.py` | Kafka consumer groups | Threading bugs: double append, double start |
| Replayer | `replayer/server.py` | gRPC service for event replay | Minimal implementation, no actual replay logic |
| Control | `control/` | Django admin for replay jobs | speed_factor unused, missing `replay` app in INSTALLED_APPS |
| DB Init | `db/init.sql` | Database initialization | Syntax errors, typos |
| Proto | `proto/walstream.proto` | Data contract definitions | No generated pb2 files in repo |

### 1.3 Critical Bugs Identified

#### Bug 1: Incomplete ChangeRecord Population (ingestor.py:63-73)
```python
# CURRENT - Missing fields
record = ChangeRecord(
    lsn=str(msg.data_start),
    commit_time=commit_time * 1000,
    table=change["table"]
    # MISSING: operation, old, new
)
```

#### Bug 2: Threading Bugs (consumer_group.py:74-79)
```python
# CURRENT - Double append and double start
self.consumers.append(thread)
thread.start()
self.consumers.append(thread)  # BUG: appended twice
thread.start()                  # BUG: started twice (will crash)
```

#### Bug 3: Redis Hash Key Mismatch (consumer_group.py:39 vs 84)
```python
# Writing to:
self.redis.hincrby(f"consumer:{self.group_id}:progress", ...)
# Reading from:
self.redis.hgetall(f"consumer : {self.group_id}:progress")  # BUG: extra spaces
```

#### Bug 4: speed_factor Not Applied (control/replay/admin.py:66)
```python
# CURRENT - Just uses commit_time directly
virtual_time=change_record.commit_time  # speed_factor ignored!
```

#### Bug 5: db/init.sql Syntax Errors
```sql
-- CURRENT (broken)
CREATE TABLE events {  -- Should be parentheses
    id SERIAL PRIMARY KEY,
    ...
}                      -- Missing semicolon
CREATE USER repluser WITH REPLICATION LOGIN PASSWORKD 'replpass';  -- Typo: PASSWORKD
```

#### Bug 6: replay app not in INSTALLED_APPS (control/walstream/settings.py)
```python
INSTALLED_APPS = [
    # ...
    # MISSING: 'replay',
]
```

### 1.4 Architectural Gaps (Critical)

| Gap | Current State | Risk |
|-----|--------------|------|
| Redis as replay source | Plan uses XRANGE for replay | Memory exhaustion on large windows |
| No retention policy | Unbounded stream growth | Redis OOM, data loss |
| Vague delivery semantics | "at-least-once" mentioned | Duplicates without dedup strategy |
| No authentication | Open control plane | Security vulnerability |
| BackgroundTasks for jobs | Not durable across restarts | Lost jobs on deploy |
| No proto versioning | Breaking changes during migration | Service incompatibility |

---

## 2. Target Architecture

### 2.1 Architecture Overview (To-Be)

```
+===========================================================================+
|                              INFRASTRUCTURE                                |
|  +----------+  +----------+  +----------+  +------------+  +------------+ |
|  |PostgreSQL|  |  Redis   |  |  Kafka   |  | Prometheus |  |Alertmanager| |
|  |   +WAL   |  | (Buffer) |  | (Archive)|  |            |  |            | |
|  +----+-----+  +----+-----+  +----+-----+  +-----+------+  +------------+ |
+========|============|============|==============|=========================+
         |            |            |              |
         v            |            |              |
+---------------+     |            |              |
|   Ingestor    |-----+------------+              |
|  (Enhanced)   |                                 |
|  - WAL decode |<--------------------------------+ (metrics)
|  - Full event |
|    extraction |
+---------------+
         |
         | Dual-write (Redis + Kafka)
         |
    +----+----+---------------------------+
    |         |                           |
    v         v                           v
+-------+ +--------+              +---------------+
| Redis | | Kafka  |              | Job Worker    |
|Stream | | Topic  |              | (Dedicated    |
|       | |        |              |  Process)     |
+---+---+ +---+----+              +-------+-------+
    |         |                           |
    |         |         +-----------------+
    |         |         |
    v         v         v
+---------------------------------------+
|           Replay Router               |
|  - Redis for live tail (<1 hour)      |
|  - Kafka for historical (>1 hour)     |
+-------------------+-------------------+
                    |
                    v
+---------------------------------------+
|           gRPC Replayer               |
|  - Idempotency enforcement            |
|  - Deduplication state store          |
|  - Pluggable targets                  |
+---------------------------------------+

+---------------------------------------+
|         FastAPI Control Plane         |
|  - REST API (primary)                 |
|  - WebSocket (live events only)       |
|  - JWT authentication                 |
|  - Audit logging                      |
+---------------------------------------+
         |
         v
+---------------------------------------+
|       Next.js Dashboard (Optional)    |
|  - Real-time event visualization      |
|  - Job management UI                  |
|  - Alert dashboard                    |
+---------------------------------------+
```

### 2.2 Data Flow with Clear Boundaries

```
PostgreSQL WAL
      |
      v (wal2json)
+-------------+
|  Ingestor   |--+--> Redis Stream (LIVE BUFFER)
+-------------+  |         |
                 |         | MAXLEN ~100K events
                 |         | TTL: ~1 hour equivalent
                 |         | Use case: Live tail, small window replay
                 |         |
                 |         v
                 |    +------------------+
                 |    | Real-time Worker | --> gRPC Replayer
                 |    | (Redis consumer) |     (with dedup)
                 |    +------------------+
                 |
                 +--> Kafka Topic (DURABLE ARCHIVE)
                           |
                           | retention.ms: 7 days (configurable)
                           | Use case: Historical replay, audit, analytics
                           |
                           v
                     +------------------+
                     |  Replay Worker   | --> gRPC Replayer
                     | (Kafka consumer) |     (with dedup)
                     +------------------+
```

### 2.3 Service Responsibilities (Clarified)

| Service | Primary Responsibility | Data Source | API Surface |
|---------|----------------------|-------------|-------------|
| **Ingestor** | WAL capture, dual-publish | PostgreSQL WAL | Internal only |
| **FastAPI Control** | Job management, auth, audit | PostgreSQL (control DB) | REST (primary), WebSocket (live events) |
| **Job Worker** | Durable job execution | Redis (job queue) | Internal only |
| **Replay Worker** | Speed-controlled replay | Kafka OR Redis (routed) | Internal only |
| **Replayer** | Event application with dedup | gRPC requests | gRPC only |

### 2.4 API Surface Decision

**Decision: REST is the primary control API. gRPC is internal only.**

| Interface | Purpose | Consumers |
|-----------|---------|-----------|
| REST `/api/v1/*` | Job CRUD, metrics, health | Dashboard, CLI, external integrations |
| WebSocket `/ws/events` | Live event stream only | Dashboard (optional) |
| gRPC `Replayer` | Internal replay execution | Job Worker, Replay Worker |
| gRPC `Ingestor` | **Removed** - not needed | N/A |

**Rationale:**
- REST is easier to debug, document, and secure
- gRPC adds value for high-throughput internal RPCs (replayer)
- WebSocket only for real-time UI updates (not critical path)
- Reduces API surface maintenance burden

---

## 3. Design Decisions & Delivery Semantics

### 3.1 Delivery Guarantee: At-Least-Once with Idempotent Application

**Precise Definition:**
> Every event captured from PostgreSQL WAL will be delivered to the target system at least once. Duplicate deliveries are safe because the Replayer enforces idempotency using a deduplication state store keyed by `(lsn, table, primary_key)`.

**Where Deduplication Lives: The Replayer**

```
+----------------+     +------------------+     +---------------+
| Replay Worker  | --> |    Replayer      | --> | Target System |
| (may retry)    |     | (dedup check)    |     | (database)    |
+----------------+     +--------+---------+     +---------------+
                                |
                                v
                       +------------------+
                       | Dedup State Store|
                       | (Redis Hash or   |
                       |  PostgreSQL)     |
                       +------------------+
```

**Idempotency Key Format:**
```
idempotency_key = f"{lsn}:{table}:{primary_key_hash}"
```

**Deduplication Flow:**
```python
async def replay_event(self, request: ReplayRequest) -> ReplayResponse:
    # 1. Compute idempotency key
    event = request.event
    pk_hash = hash_primary_key(event.new or event.old)
    idemp_key = f"{event.lsn}:{event.table}:{pk_hash}"

    # 2. Check if already processed
    if await self.dedup_store.exists(idemp_key):
        logger.info(f"Duplicate detected, skipping: {idemp_key}")
        return ReplayResponse(success=True, message="duplicate_skipped")

    # 3. Apply to target (with transaction)
    try:
        await self.apply_to_target(event)

        # 4. Mark as processed (with TTL for storage bounds)
        await self.dedup_store.set(idemp_key, ttl=DEDUP_TTL_SECONDS)

        return ReplayResponse(success=True)
    except Exception as e:
        # Don't mark as processed - allow retry
        return ReplayResponse(success=False, message=str(e))
```

**Dedup Store Options:**

| Store | Pros | Cons | Recommendation |
|-------|------|------|----------------|
| Redis Hash | Fast, simple | Memory-bound, not durable | Dev/small scale |
| PostgreSQL | Durable, queryable | Slower, connection overhead | Production |
| RocksDB (embedded) | Fast, durable | Operational complexity | High-throughput |

**Recommended: PostgreSQL for production** (same DB as control plane, with separate schema)

```sql
CREATE TABLE walstream_dedup.processed_events (
    idempotency_key VARCHAR(255) PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    job_id UUID,
    -- Auto-cleanup via pg_partman or scheduled job
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);

CREATE INDEX idx_processed_events_expires ON walstream_dedup.processed_events(expires_at);
```

### 3.2 Replay Source Selection: Redis vs Kafka

**Decision Matrix:**

| Replay Window | Source | Rationale |
|---------------|--------|-----------|
| Live tail (last N events) | Redis XREAD | Low latency, already buffered |
| < 1 hour | Redis XRANGE | Small window, fast |
| >= 1 hour | Kafka consumer | Scalable, doesn't load into memory |
| > 7 days | Not supported | Beyond retention, require archive restore |

**Router Implementation:**

```python
class ReplaySourceRouter:
    """Routes replay requests to appropriate source based on time window."""

    REDIS_THRESHOLD_MS = 60 * 60 * 1000  # 1 hour in milliseconds

    async def get_replay_source(
        self,
        start_time_ms: int,
        end_time_ms: int
    ) -> ReplaySource:
        window_ms = end_time_ms - start_time_ms
        now_ms = int(time.time() * 1000)
        age_ms = now_ms - start_time_ms

        # Live tail or recent small window -> Redis
        if age_ms < self.REDIS_THRESHOLD_MS and window_ms < self.REDIS_THRESHOLD_MS:
            return RedisReplaySource(self.redis_client)

        # Historical or large window -> Kafka
        return KafkaReplaySource(self.kafka_consumer)
```

### 3.3 Retention & Backpressure Policies

#### Redis Stream Policy

```python
# Ingestor: Add with MAXLEN to bound memory
REDIS_STREAM_MAXLEN = int(os.getenv("REDIS_STREAM_MAXLEN", "100000"))

message_id = redis_client.xadd(
    REDIS_STREAM,
    fields={"payload": serialized, ...},
    maxlen=REDIS_STREAM_MAXLEN,
    approximate=True,  # ~MAXLEN for performance
)
```

**Configuration:**
```yaml
# Environment variables
REDIS_STREAM_MAXLEN: 100000          # Max ~100K events
REDIS_STREAM_APPROX_TRIM: true       # Use ~ for performance
```

**Monitoring Alert:**
```yaml
# Alert when stream approaches capacity
- alert: RedisStreamNearCapacity
  expr: walstream_redis_stream_length > 80000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Redis stream at {{ $value }} events (80% of 100K limit)"
```

#### Kafka Topic Policy

```properties
# Kafka topic configuration
walstream.archive:
  retention.ms=604800000        # 7 days
  retention.bytes=-1            # No size limit (time-based only)
  cleanup.policy=delete         # Delete old segments
  segment.ms=3600000            # 1 hour segments
  min.compaction.lag.ms=0
```

**Monitoring Alert:**
```yaml
- alert: KafkaConsumerLagHigh
  expr: walstream_kafka_consumer_lag > 10000
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Kafka consumer lag is {{ $value }} messages"
```

### 3.4 Proto Versioning & Migration Strategy

**Decision: Use package versioning with backward compatibility period**

#### Version Strategy

```
walstream-proto/
├── proto/
│   ├── v1/
│   │   └── walstream.proto    # Current (stable)
│   └── v2/
│       └── walstream.proto    # New (in development)
└── walstream_proto/
    ├── v1/
    │   ├── __init__.py
    │   ├── walstream_pb2.py
    │   └── walstream_pb2_grpc.py
    └── v2/
        └── ...
```

#### Migration Process

```
Phase 1: Add v2 alongside v1
  - Deploy consumers that understand both v1 and v2
  - Kafka topic remains: walstream.archive (v1 format)

Phase 2: Dual-write period
  - Ingestor writes to both:
    - walstream.archive (v1) - existing
    - walstream.archive.v2 (v2) - new
  - All consumers read v2

Phase 3: Cutover
  - Stop v1 writes
  - Deprecate v1 topic after retention period
  - Remove v1 code
```

#### Compatibility Rules

```protobuf
// v1/walstream.proto - FROZEN after release
message ChangeRecord {
  string lsn = 1;              // Never remove or renumber
  int64 commit_time = 2;
  string table = 3;
  string operation = 4;
  map<string, string> old = 5;
  map<string, string> new = 6;

  reserved 50 to 100;          // Reserved for v1 additions
}

// v2/walstream.proto - New features
message ChangeRecord {
  // All v1 fields preserved with same numbers
  string lsn = 1;
  int64 commit_time = 2;
  string table = 3;
  string operation = 4;
  map<string, string> old = 5;
  map<string, string> new = 6;

  // New v2 fields start at 101
  string schema = 101;
  string transaction_id = 102;
  int32 sequence_in_tx = 103;
  bytes raw_payload = 104;     // For debugging

  reserved 200 to 300;
}
```

---

## 4. Critical Implementation Notes

### 4.1 Async/Sync Library Audit

**CRITICAL**: Never mix `async def` with blocking library calls. This causes event loop starvation.

**Broken pattern (kafka-python in async context):**
```python
async def stream_events(...):
    for message in self.consumer:  # ❌ BLOCKS EVENT LOOP
        yield ReplayEvent(...)
```

**Solution:** Use native async libraries. See Phase 3's `KafkaReplaySource` for correct aiokafka implementation.

| Use Case | Library | Notes |
|----------|---------|-------|
| Kafka | `aiokafka` | Native asyncio - **required** |
| Redis | `redis.asyncio` | Built-in async (redis-py 4.2+) |
| gRPC | `grpc.aio` | Async channel/stub/servicer |
| PostgreSQL | `asyncpg` | For control plane |
| HTTP Client | `httpx` | Or `aiohttp` |

If sync is unavoidable, use `loop.run_in_executor()` but prefer native async libraries.

### 4.2 Checkpoint Format: Per-Partition Offsets

Use JSON with per-partition offsets, not a single string:
```python
# ❌ Wrong: checkpoint = "12345"
# ✅ Correct: checkpoint = {"0": 1234, "1": 5678}  # partition: offset

class ReplayJobCheckpoint(Base):
    __tablename__ = "replay_job_checkpoints"
    job_id = Column(UUID, ForeignKey("replay_jobs.id"), primary_key=True)
    partition_offsets = Column(JSON, nullable=False)  # {"0": 1234, "1": 5678}
    events_processed = Column(BigInteger, default=0)
```

On resume, seek each partition independently: `consumer.seek(tp, offset + 1)`

### 4.3 Shared Library: walstream-common

**Problem:** Replayer needs dedup models but can't import from control/.

**Solution:** Create `walstream-common` with shared models:
```
walstream-common/
├── walstream_common/
│   ├── models/          # ProcessedEvent, ReplayJob, Checkpoint
│   ├── config/          # Pydantic Settings
│   └── utils/           # Idempotency key generation
```

Both `control` and `replayer` depend on `walstream-common[postgres]`.

### 4.4 Dedup Enforcement Point: Replayer Only

**Decision:** Dedup is centralized in the Replayer (single enforcement point).

```python
# Replayer checks and marks processed
async def ReplayEvent(self, request, context) -> ReplayResponse:
    idemp_key = f"{request.event.lsn}:{request.event.table}:{pk_hash}"
    if await self.dedup_repo.exists(idemp_key):
        return ReplayResponse(success=True, was_duplicate=True)
    await self.target_applier.apply(request.event)
    await self.dedup_repo.mark_processed(idemp_key, request.job_id)
    return ReplayResponse(success=True, was_duplicate=False)
```

Worker just calls Replayer and trusts the response - no local dedup.

### 4.5 Kafka Producer Idempotence

```python
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKERS,
    enable_idempotence=True,  # Prevents duplicates from retries
    acks="all", retries=5,
)
```

Producer idempotence handles retry duplicates; Replayer dedup handles replay duplicates.

---

## 5. Implementation Phases

### Phase 0: Critical Fixes (Foundation)
**Goal:** Fix all blocking bugs, establish working baseline

#### 0.1 Fix db/init.sql
**File:** `db/init.sql`
```sql
-- Corrected init.sql
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create replication user with proper permissions
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'repluser') THEN
        CREATE USER repluser WITH REPLICATION LOGIN PASSWORD 'replpass';
    END IF;
END
$$;

-- Grant necessary permissions
GRANT SELECT ON ALL TABLES IN SCHEMA public TO repluser;
GRANT USAGE ON SCHEMA public TO repluser;

-- Note: No CREATE PUBLICATION needed - we use wal2json output plugin
-- which works directly with logical replication slots, not publications
```

#### 0.2 Fix consumer_group.py Threading Bugs
**File:** `worker/consumer_group.py`
```python
# FIXED start_all method
def start_all(self):
    for i in range(self.num_consumers):
        thread = threading.Thread(target=self.start_consumer, args=(i,))
        thread.daemon = True
        self.consumers.append(thread)
        thread.start()
        # Removed: duplicate append and start

# FIXED get_progress - consistent Redis key
def get_progress(self):
    return self.redis.hgetall(f"consumer:{self.group_id}:progress")
    # Removed extra spaces in key
```

#### 0.3 Fix Django INSTALLED_APPS
**File:** `control/walstream/settings.py`
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'replay',  # ADD THIS
]
```

#### 0.4 Deliverables Checklist
- [ ] `db/init.sql` - Fixed syntax, idempotent
- [ ] `worker/consumer_group.py` - Threading fixes
- [ ] `control/walstream/settings.py` - Add replay app
- [ ] Verify system starts without errors

---

### Phase 1: Protobuf Packaging & Versioning
**Goal:** Single source of truth for protobuf with version support

#### 1.1 Create Shared Proto Package

**New Directory Structure:**
```
walstream-proto/
├── pyproject.toml
├── proto/
│   └── v1/
│       └── walstream.proto
├── walstream_proto/
│   ├── __init__.py
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── walstream_pb2.py      (generated)
│   │   └── walstream_pb2_grpc.py (generated)
│   ├── models.py                    (Pydantic models)
│   └── generate.py
└── tests/
    └── test_compatibility.py
```

**File:** `walstream-proto/pyproject.toml`
```toml
[project]
name = "walstream-proto"
version = "1.0.0"
description = "WalStream protobuf definitions and generated code"
requires-python = ">=3.11"
dependencies = [
    "grpcio>=1.60.0",
    "grpcio-tools>=1.60.0",
    "protobuf>=4.25.0",
    "pydantic>=2.0.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project.scripts]
generate-proto = "walstream_proto.generate:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["walstream_proto*"]
```

**File:** `walstream-proto/proto/v1/walstream.proto`
```protobuf
syntax = "proto3";

package walstream.v1;

option python_package = "walstream_proto.v1";

// ==========================================================================
// Core Data Types
// ==========================================================================

message ChangeRecord {
  string lsn = 1;               // Log Sequence Number from PostgreSQL
  int64 commit_time = 2;        // Unix timestamp in milliseconds
  string table = 3;             // Fully qualified table name (schema.table)
  string operation = 4;         // INSERT, UPDATE, DELETE, TRUNCATE
  map<string, string> old = 5;  // Previous row values (UPDATE/DELETE)
  map<string, string> new = 6;  // New row values (INSERT/UPDATE)

  // Reserved for future v1 additions
  reserved 50 to 100;
}

message ReplayRequest {
  string job_id = 1;
  ChangeRecord event = 2;
  int64 virtual_time = 3;       // Adjusted time based on speed_factor
  int64 original_time = 4;      // Original commit_time
  float speed_factor = 5;       // Speed multiplier used
  string idempotency_key = 6;   // For deduplication
}

message ReplayResponse {
  bool success = 1;
  string message = 2;
  bool was_duplicate = 3;       // True if skipped due to dedup
}

// ==========================================================================
// Services (Internal gRPC only)
// ==========================================================================

service Replayer {
  rpc ReplayEvent(ReplayRequest) returns (ReplayResponse);
  rpc Health(HealthRequest) returns (HealthResponse);
}

message HealthRequest {}

message HealthResponse {
  bool healthy = 1;
  map<string, string> components = 2;
}
```

**File:** `walstream-proto/walstream_proto/__init__.py`
```python
"""
WalStream Protocol Buffers Package.

Import from versioned subpackages:
    from walstream_proto.v1 import ChangeRecord, ReplayRequest
"""

# Default to v1 for backward compatibility
from walstream_proto.v1 import (
    ChangeRecord,
    ReplayRequest,
    ReplayResponse,
    ReplayerStub,
    ReplayerServicer,
    add_ReplayerServicer_to_server,
    HealthRequest,
    HealthResponse,
)

__version__ = "1.0.0"
__all__ = [
    "ChangeRecord",
    "ReplayRequest",
    "ReplayResponse",
    "ReplayerStub",
    "ReplayerServicer",
    "add_ReplayerServicer_to_server",
    "HealthRequest",
    "HealthResponse",
]
```

**File:** `walstream-proto/walstream_proto/models.py`
```python
"""Pydantic models for type-safe Python usage and REST API schemas."""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class Operation(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    TRUNCATE = "TRUNCATE"


class ChangeRecordModel(BaseModel):
    """Pydantic representation of ChangeRecord protobuf."""
    lsn: str
    commit_time: int = Field(description="Unix timestamp in milliseconds")
    table: str
    operation: Operation
    old: dict[str, str] = Field(default_factory=dict)
    new: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_protobuf(cls, pb) -> "ChangeRecordModel":
        from walstream_proto.v1 import ChangeRecord
        return cls(
            lsn=pb.lsn,
            commit_time=pb.commit_time,
            table=pb.table,
            operation=Operation(pb.operation) if pb.operation else Operation.INSERT,
            old=dict(pb.old),
            new=dict(pb.new),
        )

    def to_protobuf(self):
        from walstream_proto.v1 import ChangeRecord
        return ChangeRecord(
            lsn=self.lsn,
            commit_time=self.commit_time,
            table=self.table,
            operation=self.operation.value,
            old=self.old,
            new=self.new,
        )

    def idempotency_key(self, primary_key_fields: list[str] | None = None) -> str:
        """Generate idempotency key for deduplication."""
        # Use 'new' for INSERT/UPDATE, 'old' for DELETE
        data = self.new if self.operation != Operation.DELETE else self.old

        if primary_key_fields:
            pk_values = ":".join(str(data.get(f, "")) for f in primary_key_fields)
        else:
            # Fallback: hash all values
            pk_values = hash(frozenset(data.items()))

        return f"{self.lsn}:{self.table}:{pk_values}"


class JobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplayJobCreate(BaseModel):
    """Schema for creating a new replay job."""
    start_time: datetime
    end_time: datetime
    speed_factor: float = Field(default=1.0, ge=0.1, le=100.0)
    target_type: str = Field(default="grpc", pattern="^(grpc|http)$")
    target_url: Optional[str] = None

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v, info):
        if info.data.get("start_time") and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class ReplayJobResponse(BaseModel):
    """Schema for replay job API responses."""
    id: UUID
    start_time: datetime
    end_time: datetime
    speed_factor: float
    target_type: str
    target_url: Optional[str]
    status: JobStatus
    events_total: int
    events_processed: int
    events_failed: int
    events_skipped_dedup: int = 0
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    replay_source: Optional[str] = None  # "redis" or "kafka"

    model_config = {"from_attributes": True}

    @property
    def progress_percent(self) -> float:
        if self.events_total > 0:
            return round((self.events_processed / self.events_total) * 100, 2)
        return 0.0
```

#### 1.2 Proto Generation Script

**File:** `walstream-proto/walstream_proto/generate.py`
```python
#!/usr/bin/env python3
"""Generate protobuf Python files for all versions."""
import subprocess
import sys
from pathlib import Path


def generate_version(version: str) -> bool:
    """Generate proto files for a specific version."""
    base_dir = Path(__file__).parent.parent
    proto_dir = base_dir / "proto" / version
    output_dir = base_dir / "walstream_proto" / version

    proto_file = proto_dir / "walstream.proto"

    if not proto_file.exists():
        print(f"Warning: {proto_file} not found, skipping {version}")
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py
    init_file = output_dir / "__init__.py"
    init_file.write_text('''"""Auto-generated protocol buffer modules."""
from .walstream_pb2 import *
from .walstream_pb2_grpc import *
''')

    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
        str(proto_file),
    ]

    print(f"Generating {version}: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error generating {version}: {result.stderr}")
        return False

    # Fix relative imports in generated grpc file
    grpc_file = output_dir / "walstream_pb2_grpc.py"
    if grpc_file.exists():
        content = grpc_file.read_text()
        content = content.replace(
            "import walstream_pb2",
            "from . import walstream_pb2"
        )
        grpc_file.write_text(content)

    print(f"Generated {version} successfully")
    return True


def main():
    """Generate all proto versions."""
    base_dir = Path(__file__).parent.parent
    proto_base = base_dir / "proto"

    versions = [d.name for d in proto_base.iterdir() if d.is_dir()]

    if not versions:
        print("No version directories found in proto/")
        sys.exit(1)

    success = all(generate_version(v) for v in sorted(versions))

    if success:
        print("\nProto generation complete!")
    else:
        print("\nSome versions failed to generate")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

#### 1.3 Compatibility Test

**File:** `walstream-proto/tests/test_compatibility.py`
```python
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
        # This would contain actual bytes from a known v1 message
        # In practice, store test fixtures of serialized protos
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
```

#### 1.4 Deliverables Checklist
- [ ] Create `walstream-proto/` package structure with v1/
- [ ] Implement generation script supporting multiple versions
- [ ] Generate v1 pb2 files
- [ ] Create Pydantic models with idempotency_key()
- [ ] Add compatibility tests
- [ ] Update all service imports to use `from walstream_proto.v1 import ...`
- [ ] Delete old `ingestor/test_pb2.py`

---

### Phase 2: Ingestor Enhancement with Retention
**Goal:** Full wal2json parsing, proper field extraction, retention policies

#### 2.1 Understanding wal2json Format (v2)

```json
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
```

#### 2.2 Enhanced Ingestor Implementation

**File:** `ingestor/ingestor.py` (rewritten)
```python
"""
WalStream Ingestor - Captures PostgreSQL WAL changes with retention policies.
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
POSTGRES_DB = os.getenv("POSTGRES_DB", "shadowdb")

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
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ingestor")

# ==========================================================================
# Prometheus Metrics
# ==========================================================================

EVENTS_INGESTED = Counter(
    "walstream_events_ingested_total",
    "Total events ingested from PostgreSQL WAL",
    ["table", "operation"]
)

EVENTS_PUBLISHED_REDIS = Counter(
    "walstream_events_published_redis_total",
    "Events published to Redis stream"
)

EVENTS_PUBLISHED_KAFKA = Counter(
    "walstream_events_published_kafka_total",
    "Events published to Kafka"
)

INGEST_ERRORS = Counter(
    "walstream_ingest_errors_total",
    "Total ingestion errors",
    ["error_type"]
)

REDIS_STREAM_LENGTH = Gauge(
    "walstream_redis_stream_length",
    "Current Redis stream length"
)

WAL_LAG_BYTES = Gauge(
    "walstream_wal_lag_bytes",
    "WAL replication lag in bytes"
)

INGEST_LATENCY = Histogram(
    "walstream_ingest_latency_seconds",
    "Time from WAL commit to publish complete",
    buckets=[.001, .005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0]
)

# ==========================================================================
# WAL Parsing
# ==========================================================================

ACTION_MAP = {
    "I": "INSERT",
    "U": "UPDATE",
    "D": "DELETE",
    "T": "TRUNCATE",
}


def parse_wal2json_v2(payload: dict, lsn: int) -> list[ChangeRecord]:
    """
    Parse wal2json format-version 2 payload into ChangeRecord messages.
    Returns a list because one WAL message can contain multiple changes.
    """
    records = []

    timestamp_str = payload.get("timestamp", "")
    try:
        if timestamp_str:
            # Handle both space and T separator
            ts = timestamp_str.replace(" ", "T")
            dt = datetime.fromisoformat(ts)
            commit_time_ms = int(dt.timestamp() * 1000)
        else:
            commit_time_ms = int(time.time() * 1000)
    except ValueError as e:
        logger.warning(f"Could not parse timestamp '{timestamp_str}': {e}")
        commit_time_ms = int(time.time() * 1000)

    for idx, change in enumerate(payload.get("change", [])):
        action = change.get("kind", change.get("action", ""))
        operation = ACTION_MAP.get(action, action)

        schema = change.get("schema", "public")
        table = change.get("table", "unknown")

        old_values = {}
        new_values = {}

        # Extract new values (INSERT, UPDATE)
        if "columns" in change:
            for col in change.get("columns", []):
                col_name = col.get("name", "")
                col_value = col.get("value")
                if col_value is not None:
                    new_values[col_name] = str(col_value)
        elif "columnnames" in change and "columnvalues" in change:
            names = change.get("columnnames", [])
            values = change.get("columnvalues", [])
            for name, value in zip(names, values):
                if value is not None:
                    new_values[name] = str(value)

        # Extract old values (UPDATE, DELETE)
        if "identity" in change:
            for col in change.get("identity", []):
                col_name = col.get("name", "")
                col_value = col.get("value")
                if col_value is not None:
                    old_values[col_name] = str(col_value)
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

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.kafka_producer: Optional[KafkaProducer] = None
        self.pg_conn = None
        self.pg_cursor = None
        self.running = False

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
                logger.warning(f"Redis attempt {attempt + 1}/{max_retries} failed: {e}")
                INGEST_ERRORS.labels(error_type="redis_connection").inc()
                time.sleep(2 ** attempt)
        raise ConnectionError("Could not connect to Redis after retries")

    def connect_kafka(self) -> None:
        """Establish Kafka producer with retry."""
        max_retries = 5
        for attempt in range(max_retries):
            try:
                self.kafka_producer = KafkaProducer(
                    bootstrap_servers=[KAFKA_BROKER],
                    value_serializer=None,
                    acks='all',
                    retries=3,
                    max_in_flight_requests_per_connection=1,
                    enable_idempotence=True,
                )
                logger.info("Connected to Kafka")
                return
            except KafkaError as e:
                logger.warning(f"Kafka attempt {attempt + 1}/{max_retries} failed: {e}")
                INGEST_ERRORS.labels(error_type="kafka_connection").inc()
                time.sleep(2 ** attempt)
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
                REPLICATION_SLOT,
                output_plugin="wal2json"
            )
            logger.info(f"Created replication slot: {REPLICATION_SLOT}")
        except psycopg2.ProgrammingError as e:
            if "already exists" in str(e):
                logger.info(f"Replication slot {REPLICATION_SLOT} already exists")
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
            approximate=True,
        )

        EVENTS_PUBLISHED_REDIS.inc()

        # Update stream length gauge periodically (every 100 events)
        if EVENTS_PUBLISHED_REDIS._value.get() % 100 == 0:
            length = self.redis_client.xlen(REDIS_STREAM)
            REDIS_STREAM_LENGTH.set(length)

        return message_id.decode() if isinstance(message_id, bytes) else str(message_id)

    def publish_to_kafka(self, record: ChangeRecord) -> None:
        """Publish ChangeRecord to Kafka topic."""
        serialized = record.SerializeToString()

        future = self.kafka_producer.send(
            KAFKA_TOPIC,
            value=serialized,
            key=record.table.encode("utf-8"),
        )
        future.get(timeout=10)
        EVENTS_PUBLISHED_KAFKA.inc()

    def process_message(self, msg) -> bool:
        """Process a single replication message."""
        start_time = time.time()

        try:
            msg.cursor.send_feedback(flush_lsn=msg.data_start)

            payload = json.loads(msg.payload)
            records = parse_wal2json_v2(payload, msg.data_start)

            for record in records:
                EVENTS_INGESTED.labels(
                    table=record.table,
                    operation=record.operation
                ).inc()

                redis_id = self.publish_to_redis(record)
                self.publish_to_kafka(record)

                logger.info(
                    f"Ingested: {record.operation} on {record.table} "
                    f"(LSN: {record.lsn}, Redis: {redis_id})"
                )

            INGEST_LATENCY.observe(time.time() - start_time)
            return True

        except json.JSONDecodeError as e:
            INGEST_ERRORS.labels(error_type="json_parse").inc()
            logger.error(f"JSON parse error: {e}")
            return False
        except Exception as e:
            INGEST_ERRORS.labels(error_type="unknown").inc()
            logger.error(f"Error processing message: {e}", exc_info=True)
            return False

    def start(self) -> None:
        """Start the ingestor."""
        logger.info("Starting WalStream Ingestor...")

        # Start metrics server
        start_http_server(METRICS_PORT)
        logger.info(f"Metrics available on port {METRICS_PORT}")

        self.connect_redis()
        self.connect_kafka()
        self.connect_postgres()

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

        logger.info(f"Started replication from slot: {REPLICATION_SLOT}")
        self.running = True

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


def main():
    ingestor = Ingestor()

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
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
            logger.error(f"Ingestor crashed: {e}", exc_info=True)
            INGEST_ERRORS.labels(error_type="crash").inc()
            time.sleep(5)


if __name__ == "__main__":
    main()
```

#### 2.3 Deliverables Checklist
- [ ] Implement `parse_wal2json_v2()` with full field extraction
- [ ] Add MAXLEN trimming to Redis XADD
- [ ] Add Prometheus metrics
- [ ] Add signal handling for graceful shutdown
- [ ] Test with INSERT/UPDATE/DELETE operations
- [ ] Verify old/new maps populated correctly

---

### Phase 3: FastAPI Control Plane with Durable Job Execution
**Goal:** Replace Django with FastAPI, durable job workers, proper replay routing

#### 3.1 Project Structure

```
control/
├── pyproject.toml
├── Dockerfile
├── alembic/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── replay_job.py
│   │   └── dedup_state.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       ├── jobs.py
│   │       ├── events.py
│   │       ├── health.py
│   │       └── metrics.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── replay_router.py
│   │   ├── redis_source.py
│   │   ├── kafka_source.py
│   │   ├── dedup_store.py
│   │   └── grpc_client.py
│   └── workers/
│       ├── __init__.py
│       ├── job_worker.py
│       └── manager.py
└── tests/
```

#### 3.2 Configuration

**File:** `control/app/config.py`
```python
"""Application configuration using Pydantic Settings."""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "WalStream Control"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database (Control Plane)
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/walstream_control"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_stream: str = "walstream:events"
    redis_replay_threshold_ms: int = 3600000  # 1 hour

    # Kafka
    kafka_broker: str = "localhost:9092"
    kafka_topic: str = "walstream.archive"
    kafka_consumer_group: str = "walstream-replay"

    # gRPC Replayer
    replayer_host: str = "localhost"
    replayer_port: int = 50051
    replayer_timeout_seconds: int = 30

    # Job Worker
    job_worker_count: int = 4
    job_poll_interval_seconds: float = 1.0
    job_heartbeat_interval_seconds: float = 10.0
    job_lease_duration_seconds: int = 300  # 5 minutes

    # Deduplication
    dedup_ttl_seconds: int = 604800  # 7 days

    # Security
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Metrics
    metrics_port: int = 9091


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

#### 3.3 Database Models

**File:** `control/app/models/replay_job.py`
```python
"""SQLAlchemy models for replay jobs with durable execution."""
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column, DateTime, Enum, Float, Integer, String, Text,
    Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class JobStatus(str, PyEnum):
    PENDING = "pending"
    QUEUED = "queued"      # In job queue, waiting for worker
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplayJob(Base):
    """Replay job with durable execution support."""

    __tablename__ = "replay_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Time range
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    # Configuration
    speed_factor = Column(Float, default=1.0, nullable=False)
    target_type = Column(String(20), default="grpc")
    target_url = Column(String(255), nullable=True)

    # Status
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)
    events_total = Column(Integer, default=0)
    events_processed = Column(Integer, default=0)
    events_failed = Column(Integer, default=0)
    events_skipped_dedup = Column(Integer, default=0)

    # Replay source (determined at runtime)
    replay_source = Column(String(20), nullable=True)  # "redis" or "kafka"

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_count = Column(Integer, default=0)

    # Checkpoint for resumability
    last_processed_id = Column(String(255), nullable=True)  # Redis ID or Kafka offset
    last_processed_time = Column(DateTime(timezone=True), nullable=True)

    # Worker lease (for durable execution)
    worker_id = Column(String(100), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by = Column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_replay_jobs_status", "status"),
        Index("idx_replay_jobs_lease", "status", "lease_expires_at"),
        CheckConstraint("end_time > start_time", name="check_time_range"),
        CheckConstraint("speed_factor > 0", name="check_speed_factor"),
    )
```

**File:** `control/app/models/dedup_state.py`
```python
"""Deduplication state storage."""
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Index
from app.models.replay_job import Base


class ProcessedEvent(Base):
    """Tracks processed events for idempotency."""

    __tablename__ = "processed_events"
    __table_args__ = (
        Index("idx_processed_events_expires", "expires_at"),
        {"schema": "walstream_dedup"},
    )

    idempotency_key = Column(String(255), primary_key=True)
    processed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    job_id = Column(String(36), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
```

#### 3.4 Replay Source Router

**File:** `control/app/services/replay_router.py`
```python
"""Routes replay requests to Redis or Kafka based on time window."""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Optional

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class ReplayEvent:
    """Unified event representation from any source."""
    message_id: str  # Redis stream ID or Kafka offset
    payload: bytes
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
        checkpoint: Optional[str] = None
    ) -> AsyncIterator[ReplayEvent]:
        """Stream events from checkpoint, yielding one at a time."""
        pass

    @abstractmethod
    def source_name(self) -> str:
        """Return source identifier."""
        pass


class RedisReplaySource(ReplaySource):
    """Replay from Redis stream (for recent/small windows)."""

    def __init__(self, redis_client):
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
        checkpoint: Optional[str] = None
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
                msg_id = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
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


class KafkaReplaySource(ReplaySource):
    """Replay from Kafka using aiokafka (async-native, non-blocking)."""

    def __init__(self, bootstrap_servers: str, topic: str):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self._consumer: Optional[AIOKafkaConsumer] = None

    def source_name(self) -> str:
        return "kafka"

    async def _get_consumer(self, group_id: str) -> AIOKafkaConsumer:
        if not self._consumer:
            self._consumer = AIOKafkaConsumer(
                self.topic, bootstrap_servers=self.bootstrap_servers,
                group_id=group_id, enable_auto_commit=False,
            )
            await self._consumer.start()
        return self._consumer

    async def count_events(self, start_ms: int, end_ms: int) -> int:
        """Approximate count using offset differences."""
        consumer = await self._get_consumer("count-temp")
        partitions = [TopicPartition(self.topic, p)
                      for p in await consumer.partitions_for_topic(self.topic)]
        timestamps = {tp: start_ms for tp in partitions}
        start_offsets = await consumer.offsets_for_times(timestamps)
        timestamps = {tp: end_ms for tp in partitions}
        end_offsets = await consumer.offsets_for_times(timestamps)

        total = 0
        for tp in partitions:
            s, e = start_offsets.get(tp), end_offsets.get(tp)
            if s and e:
                total += max(0, e.offset - s.offset)
        return total

    async def stream_events(self, start_ms: int, end_ms: int,
                           checkpoint: Optional[str] = None) -> AsyncIterator[ReplayEvent]:
        """Stream events using async iteration (yields to event loop)."""
        consumer = await self._get_consumer(f"replay-{uuid.uuid4().hex[:8]}")
        partitions = [TopicPartition(self.topic, p)
                      for p in await consumer.partitions_for_topic(self.topic)]
        consumer.assign(partitions)

        # Seek to checkpoint or timestamp
        if checkpoint:
            offsets = json.loads(checkpoint)  # {"0": 123, "1": 456}
            for p_str, offset in offsets.items():
                consumer.seek(TopicPartition(self.topic, int(p_str)), offset + 1)
        else:
            offsets = await consumer.offsets_for_times({tp: start_ms for tp in partitions})
            for tp, ot in offsets.items():
                if ot: consumer.seek(tp, ot.offset)

        # Async iteration - properly yields to event loop
        async for message in consumer:
            if message.timestamp > end_ms:
                break
            record = ChangeRecord()
            record.ParseFromString(message.value)
            yield ReplayEvent(
                message_id=f"{message.partition}:{message.offset}",
                payload=message.value, commit_time_ms=record.commit_time,
                table=record.table, operation=record.operation,
            )

    async def close(self):
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None


class ReplaySourceRouter:
    """Selects appropriate replay source based on time window."""

    def __init__(self, redis_client, kafka_source: KafkaReplaySource):
        self.redis_source = RedisReplaySource(redis_client)
        self.kafka_source = kafka_source  # Already configured KafkaReplaySource
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
            logger.info(f"Using Redis source (age={age_ms}ms, window={window_ms}ms)")
            return self.redis_source
        else:
            logger.info(f"Using Kafka source (age={age_ms}ms, window={window_ms}ms)")
            return self.kafka_source
```

#### 3.5 Durable Job Worker

**File:** `control/app/workers/job_worker.py`
```python
"""
Durable job worker with lease-based execution.

Features:
- Survives restarts via checkpoint/resume
- Lease-based ownership prevents duplicate execution
- Automatic lease renewal during execution
- Graceful shutdown with checkpoint save
"""
import asyncio
import logging
import signal
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

import grpc
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory
from app.models.replay_job import ReplayJob, JobStatus
from app.services.replay_router import ReplaySourceRouter, ReplayEvent
from app.services.dedup_store import DedupStore
from walstream_proto.v1 import ChangeRecord, ReplayRequest, ReplayerStub

settings = get_settings()
logger = logging.getLogger(__name__)


class JobWorker:
    """
    Durable job worker that processes replay jobs.

    Execution model:
    1. Poll for QUEUED jobs with expired/no lease
    2. Acquire lease (atomic UPDATE ... WHERE)
    3. Execute with periodic lease renewal
    4. Checkpoint progress periodically
    5. On completion/failure, release lease and update status
    """

    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.running = False
        self.current_job_id: Optional[str] = None
        self.grpc_channel = None
        self.grpc_stub = None
        self.source_router: Optional[ReplaySourceRouter] = None
        self.dedup_store: Optional[DedupStore] = None

    async def start(self):
        """Start the worker loop."""
        logger.info(f"Starting job worker: {self.worker_id}")
        self.running = True

        # Initialize dependencies
        await self._init_dependencies()

        # Start lease renewal task
        renewal_task = asyncio.create_task(self._lease_renewal_loop())

        try:
            while self.running:
                try:
                    job = await self._acquire_job()
                    if job:
                        await self._execute_job(job)
                    else:
                        await asyncio.sleep(settings.job_poll_interval_seconds)
                except Exception as e:
                    logger.error(f"Worker error: {e}", exc_info=True)
                    await asyncio.sleep(settings.job_poll_interval_seconds)
        finally:
            renewal_task.cancel()
            await self._cleanup()

    async def stop(self):
        """Stop the worker gracefully."""
        logger.info(f"Stopping worker: {self.worker_id}")
        self.running = False

    async def _init_dependencies(self):
        """Initialize gRPC and source router (aiokafka for async Kafka)."""
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.redis_url)
        # KafkaReplaySource uses aiokafka internally - pass config, not consumer
        kafka_source = KafkaReplaySource(settings.kafka_broker, settings.kafka_topic)
        self.source_router = ReplaySourceRouter(redis_client, kafka_source)

        target = f"{settings.replayer_host}:{settings.replayer_port}"
        self.grpc_channel = grpc.aio.insecure_channel(target)
        self.grpc_stub = ReplayerStub(self.grpc_channel)

    async def _cleanup(self):
        """Cleanup resources."""
        if self.grpc_channel:
            await self.grpc_channel.close()

    async def _acquire_job(self) -> Optional[ReplayJob]:
        """
        Attempt to acquire a queued job using atomic lease.

        Uses optimistic locking: UPDATE ... WHERE status=QUEUED AND (no lease OR expired lease)
        """
        async with async_session_factory() as db:
            now = datetime.utcnow()
            lease_until = now + timedelta(seconds=settings.job_lease_duration_seconds)

            # Atomic acquire: find and lock in one statement
            result = await db.execute(
                update(ReplayJob)
                .where(
                    and_(
                        ReplayJob.status == JobStatus.QUEUED,
                        (ReplayJob.lease_expires_at == None) | (ReplayJob.lease_expires_at < now)
                    )
                )
                .values(
                    worker_id=self.worker_id,
                    lease_expires_at=lease_until,
                    status=JobStatus.RUNNING,
                    started_at=now,
                )
                .returning(ReplayJob.id)
            )
            job_id = result.scalar_one_or_none()

            if job_id:
                await db.commit()
                # Re-fetch full job
                result = await db.execute(
                    select(ReplayJob).where(ReplayJob.id == job_id)
                )
                job = result.scalar_one()
                self.current_job_id = str(job.id)
                logger.info(f"Acquired job {job.id}")
                return job

            return None

    async def _execute_job(self, job: ReplayJob):
        """Execute a replay job with speed control and checkpointing."""
        try:
            start_ms = int(job.start_time.timestamp() * 1000)
            end_ms = int(job.end_time.timestamp() * 1000)

            # Select replay source
            source = self.source_router.get_source(start_ms, end_ms)

            async with async_session_factory() as db:
                # Update replay source
                job = await db.get(ReplayJob, job.id)
                job.replay_source = source.source_name()

                # Count events if not already counted
                if job.events_total == 0:
                    job.events_total = await source.count_events(start_ms, end_ms)

                await db.commit()

            # Initialize timing for speed control
            replay_start_real = time.time()
            first_event_time: Optional[int] = None

            checkpoint_counter = 0
            checkpoint_interval = 100

            async for event in source.stream_events(start_ms, end_ms, job.last_processed_id):
                if not self.running:
                    await self._checkpoint_job(job.id, event.message_id, JobStatus.PAUSED)
                    return

                # Initialize timing reference
                if first_event_time is None:
                    first_event_time = event.commit_time_ms

                # Speed-controlled timing
                await self._wait_for_virtual_time(
                    event.commit_time_ms,
                    first_event_time,
                    replay_start_real,
                    job.speed_factor
                )

                # Process event
                success, was_dup = await self._replay_event(job, event)

                # Update counters
                async with async_session_factory() as db:
                    job = await db.get(ReplayJob, job.id)
                    if success:
                        if was_dup:
                            job.events_skipped_dedup += 1
                        else:
                            job.events_processed += 1
                    else:
                        job.events_failed += 1

                    job.last_processed_id = event.message_id
                    job.last_processed_time = datetime.utcnow()

                    checkpoint_counter += 1
                    if checkpoint_counter >= checkpoint_interval:
                        await db.commit()
                        checkpoint_counter = 0

            # Completed
            await self._complete_job(job.id, JobStatus.COMPLETED)

        except Exception as e:
            logger.error(f"Job {job.id} failed: {e}", exc_info=True)
            await self._fail_job(job.id, str(e))

    async def _wait_for_virtual_time(
        self,
        event_time_ms: int,
        first_event_time: int,
        replay_start_real: float,
        speed_factor: float
    ):
        """Wait until the appropriate wall-clock time based on speed factor."""
        original_elapsed_ms = event_time_ms - first_event_time
        replay_elapsed_ms = original_elapsed_ms / speed_factor
        target_real_time = replay_start_real + (replay_elapsed_ms / 1000)

        now = time.time()
        if target_real_time > now:
            await asyncio.sleep(target_real_time - now)

    async def _replay_event(self, job: ReplayJob, event: ReplayEvent) -> tuple[bool, bool]:
        """
        Send event to Replayer (dedup is handled centrally by Replayer).
        Returns: (success, was_duplicate)
        """
        record = ChangeRecord()
        record.ParseFromString(event.payload)

        try:
            request = ReplayRequest(
                job_id=str(job.id),
                event=record,
                virtual_time=record.commit_time,
                speed_factor=job.speed_factor,
            )
            response = await self.grpc_stub.ReplayEvent(
                request, timeout=settings.replayer_timeout_seconds
            )
            # Replayer handles dedup check and marking - trust its response
            return response.success, response.was_duplicate
        except grpc.RpcError as e:
            logger.error(f"gRPC error replaying event: {e}")
            return False, False

    async def _lease_renewal_loop(self):
        """Periodically renew lease on current job."""
        while self.running:
            await asyncio.sleep(settings.job_heartbeat_interval_seconds)

            if self.current_job_id:
                try:
                    await self._renew_lease(self.current_job_id)
                except Exception as e:
                    logger.error(f"Failed to renew lease: {e}")

    async def _renew_lease(self, job_id: str):
        """Extend lease on current job."""
        async with async_session_factory() as db:
            now = datetime.utcnow()
            lease_until = now + timedelta(seconds=settings.job_lease_duration_seconds)

            await db.execute(
                update(ReplayJob)
                .where(
                    and_(
                        ReplayJob.id == job_id,
                        ReplayJob.worker_id == self.worker_id
                    )
                )
                .values(lease_expires_at=lease_until)
            )
            await db.commit()

    async def _checkpoint_job(self, job_id, last_id: str, status: JobStatus):
        """Save checkpoint for resumability."""
        async with async_session_factory() as db:
            job = await db.get(ReplayJob, job_id)
            job.last_processed_id = last_id
            job.last_processed_time = datetime.utcnow()
            job.status = status
            job.worker_id = None
            job.lease_expires_at = None
            await db.commit()

        self.current_job_id = None
        logger.info(f"Checkpointed job {job_id} at {last_id}")

    async def _complete_job(self, job_id, status: JobStatus):
        """Mark job as completed."""
        async with async_session_factory() as db:
            job = await db.get(ReplayJob, job_id)
            job.status = status
            job.completed_at = datetime.utcnow()
            job.worker_id = None
            job.lease_expires_at = None
            await db.commit()

        self.current_job_id = None
        logger.info(f"Completed job {job_id}")

    async def _fail_job(self, job_id, error: str):
        """Mark job as failed."""
        async with async_session_factory() as db:
            job = await db.get(ReplayJob, job_id)
            job.status = JobStatus.FAILED
            job.error_message = error
            job.error_count += 1
            job.worker_id = None
            job.lease_expires_at = None
            await db.commit()

        self.current_job_id = None
        logger.error(f"Failed job {job_id}: {error}")
```

**File:** `control/app/workers/manager.py`
```python
"""Worker manager for running multiple job workers."""
import asyncio
import logging
import signal
from typing import List

from app.config import get_settings
from app.workers.job_worker import JobWorker

settings = get_settings()
logger = logging.getLogger(__name__)


class WorkerManager:
    """Manages a pool of job workers."""

    def __init__(self, num_workers: int = None):
        self.num_workers = num_workers or settings.job_worker_count
        self.workers: List[JobWorker] = []
        self.tasks: List[asyncio.Task] = []
        self.running = False

    async def start(self):
        """Start all workers."""
        logger.info(f"Starting {self.num_workers} workers")
        self.running = True

        for i in range(self.num_workers):
            worker = JobWorker(worker_id=f"worker-{i}")
            self.workers.append(worker)
            task = asyncio.create_task(worker.start())
            self.tasks.append(task)

        # Wait for all workers
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def stop(self):
        """Stop all workers gracefully."""
        logger.info("Stopping all workers")
        self.running = False

        for worker in self.workers:
            await worker.stop()

        # Wait for tasks to complete
        for task in self.tasks:
            task.cancel()

        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All workers stopped")


async def run_workers():
    """Entry point for running workers as a separate process."""
    manager = WorkerManager()

    loop = asyncio.get_event_loop()

    def signal_handler():
        asyncio.create_task(manager.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    await manager.start()


if __name__ == "__main__":
    asyncio.run(run_workers())
```

#### 3.6 API Endpoints

**File:** `control/app/api/v1/jobs.py`
```python
"""Replay job API endpoints."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.replay_job import ReplayJob, JobStatus
from walstream_proto.models import ReplayJobCreate, ReplayJobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=ReplayJobResponse, status_code=201)
async def create_job(
    job_data: ReplayJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Create a new replay job (status: PENDING)."""
    job = ReplayJob(
        start_time=job_data.start_time,
        end_time=job_data.end_time,
        speed_factor=job_data.speed_factor,
        target_type=job_data.target_type,
        target_url=job_data.target_url,
        status=JobStatus.PENDING,
        created_by=current_user,
    )

    db.add(job)
    await db.commit()
    await db.refresh(job)

    return job


@router.post("/{job_id}/queue", response_model=ReplayJobResponse)
async def queue_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Queue a pending job for execution."""
    result = await db.execute(
        select(ReplayJob).where(ReplayJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.PENDING, JobStatus.PAUSED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot queue job with status: {job.status}"
        )

    job.status = JobStatus.QUEUED
    await db.commit()
    await db.refresh(job)

    return job


@router.post("/{job_id}/cancel", response_model=ReplayJobResponse)
async def cancel_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user),
):
    """Cancel a running or queued job."""
    result = await db.execute(
        select(ReplayJob).where(ReplayJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.PENDING, JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PAUSED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status}"
        )

    job.status = JobStatus.CANCELLED
    await db.commit()
    await db.refresh(job)

    return job


@router.get("", response_model=dict)
async def list_jobs(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List jobs with pagination."""
    query = select(ReplayJob)

    if status:
        query = query.where(ReplayJob.status == status)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    query = query.order_by(ReplayJob.created_at.desc())

    result = await db.execute(query)
    jobs = result.scalars().all()

    return {
        "items": jobs,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


@router.get("/{job_id}", response_model=ReplayJobResponse)
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get job details."""
    result = await db.execute(
        select(ReplayJob).where(ReplayJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job
```

#### 3.7 Deliverables Checklist
- [ ] Create FastAPI project structure
- [ ] Implement config with all settings
- [ ] Create SQLAlchemy models with lease support
- [ ] Implement ReplaySourceRouter (Redis/Kafka selection)
- [ ] Implement durable JobWorker with lease renewal
- [ ] Implement WorkerManager for multiple workers
- [ ] Implement DedupStore (PostgreSQL-backed)
- [ ] Create Job CRUD endpoints
- [ ] Add authentication middleware
- [ ] Create Alembic migrations
- [ ] Write API tests
- [ ] Create separate Dockerfile for workers
- [ ] Remove Django control panel

---

## 6. Security & Authentication

### 6.1 Security as First-Class Milestone

**Phase 4: Security Implementation**

| Component | Implementation | Priority |
|-----------|----------------|----------|
| API Authentication | JWT with refresh tokens | High |
| Authorization | Role-based (admin, operator, viewer) | High |
| Audit Logging | All control plane mutations | High |
| Secret Management | Environment variables / Vault | Medium |
| Network Security | Internal services on private network | Medium |

### 6.2 JWT Authentication

**File:** `control/app/api/deps.py`

**Roles:** admin > operator > viewer (hierarchical)

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from jose import JWTError, jwt

security = HTTPBearer()

def create_access_token(username: str, role: str) -> str:
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")

async def get_current_user(credentials = Depends(security)) -> str:
    payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=["HS256"])
    return payload.get("sub")

async def require_role(required_role: str):  # Dependency factory
    async def check_role(credentials = Depends(security)):
        role = jwt.decode(...).get("role")
        if role_hierarchy[role] < role_hierarchy[required_role]:
            raise HTTPException(403)
        return payload.get("sub")
    return check_role
```

### 6.3 Audit Logging

**Model:** `control/app/models/audit_log.py`

```python
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(UUID, primary_key=True)
    timestamp = Column(DateTime(timezone=True))
    username = Column(String(100))
    action = Column(String(50))           # create_job, cancel_job, etc.
    resource_type = Column(String(50))    # job, user, etc.
    resource_id = Column(String(100))
    request_body = Column(JSONB)
```

Log all mutations via middleware: `await log_audit_event(db, username, action, resource_type, ...)`

### 6.4 Security Deliverables Checklist
- [ ] Implement JWT authentication
- [ ] Add role-based authorization
- [ ] Create audit log model and middleware
- [ ] Add API key support for service-to-service auth
- [ ] Document security configuration
- [ ] Add rate limiting middleware
- [ ] Secure inter-service communication (mTLS for gRPC in production)

---

## 7. Observability, Metrics & Alerting

### 7.1 Comprehensive Metrics

**File:** `shared/metrics.py` - All metrics prefixed with `walstream_`

| Service | Metric | Type | Labels |
|---------|--------|------|--------|
| Ingestor | `ingestor_events_total` | Counter | table, operation |
| Ingestor | `ingestor_publish_latency_seconds` | Histogram | - |
| Ingestor | `ingestor_errors_total` | Counter | error_type |
| Ingestor | `redis_stream_length` | Gauge | - |
| Ingestor | `wal_replication_lag_bytes` | Gauge | - |
| Replayer | `replayer_events_total` | Counter | table, operation, result |
| Replayer | `replayer_latency_seconds` | Histogram | - |
| Replayer | `replayer_dedup_hits_total` | Counter | - |
| Worker | `worker_jobs_active` | Gauge | worker_id |
| Worker | `worker_jobs_completed_total` | Counter | status |
| Worker | `worker_events_processed_total` | Counter | job_id, result |
| Worker | `worker_replay_lag_seconds` | Gauge | job_id |
| Kafka | `kafka_consumer_lag` | Gauge | group_id, topic, partition |
| API | `api_requests_total` | Counter | method, endpoint, status_code |
| API | `api_request_latency_seconds` | Histogram | method, endpoint |
| API | `jobs_by_status` | Gauge | status |

### 7.2 Alerting Rules

**File:** `monitoring/alertmanager/rules/walstream.yml`

| Alert | Severity | Condition | Description |
|-------|----------|-----------|-------------|
| IngestorStalled | critical | `rate(events_total[5m]) == 0` for 10m | No events ingested |
| RedisStreamNearCapacity | warning | `stream_length > 80000` | 80% of MAXLEN |
| RedisStreamAtCapacity | critical | `stream_length > 95000` | Events being dropped |
| ReplayerStalled | critical | `rate(events[5m]) == 0` AND `jobs_active > 0` | Jobs active but no progress |
| ReplayerFailureRateHigh | warning | `failure_rate > 5%` | High failure rate |
| NoActiveWorkers | critical | `jobs_active == 0` AND `queued > 0` | Jobs waiting, no workers |
| JobStuck | warning | `job_duration > 1h` | Job running too long |
| KafkaConsumerLagCritical | critical | `lag > 100000` | Severe consumer lag |
| APIErrorRateHigh | warning | `5xx_rate > 1%` | High API error rate |

Example rule format:
```yaml
- alert: IngestorStalled
  expr: rate(walstream_ingestor_events_total[5m]) == 0
  for: 10m
  labels: {severity: critical, service: ingestor}
  annotations: {summary: "Ingestor stopped", runbook_url: "..."}
```

### 7.3 Alertmanager Configuration

**Routing:** `group_by: [alertname, service]`, `repeat_interval: 4h`

| Severity | Receivers |
|----------|-----------|
| critical | Slack (#critical) + PagerDuty |
| warning | Slack (#alerts) |

Inhibit warning when critical firing for same alert.

### 7.4 Grafana Dashboard

**Panels:** `monitoring/grafana/provisioning/dashboards/walstream.json`

| Panel | Type | Metric |
|-------|------|--------|
| Events Ingested | graph | `rate(ingestor_events_total[5m]) by operation` |
| Redis Stream Length | gauge | `redis_stream_length` (thresholds: 80k/95k) |
| Kafka Consumer Lag | graph | `kafka_consumer_lag by group_id` |
| Jobs by Status | piechart | `jobs_by_status` |
| Replayer Latency | graph | `histogram_quantile(0.95, replayer_latency)` |
| Replayer Results | graph | `rate(replayer_events_total) by result` |

### 7.5 Next.js Dashboard (Optional)

**Feasibility: Confirmed**

The Next.js dashboard integrates via:
- **REST API** (`/api/v1/*`) - Job CRUD, metrics, health
- **WebSocket** (`/ws/events`) - Live event stream (optional)

**Recommended Stack:**
- Next.js 14+ (App Router)
- TanStack Query for data fetching
- Recharts for visualizations
- shadcn/ui for components

**Key Pages:**
```
app/
├── page.tsx              # Dashboard overview
├── jobs/
│   ├── page.tsx          # Job list
│   └── [id]/page.tsx     # Job details + progress
├── events/
│   └── page.tsx          # Live event viewer (WebSocket)
├── alerts/
│   └── page.tsx          # Active alerts (from Alertmanager API)
└── settings/
    └── page.tsx          # Configuration viewer
```

### 7.6 Observability Deliverables Checklist
- [ ] Add Prometheus metrics to all services
- [ ] Create alerting rules for all critical paths
- [ ] Configure Alertmanager with Slack/PagerDuty
- [ ] Create Grafana dashboards
- [ ] Add `/metrics` endpoints to all services
- [ ] Document SLOs and alert thresholds
- [ ] (Optional) Scaffold Next.js dashboard

---

## 8. Testing Strategy

### 8.1 Test Pyramid

```
              /\
             /  \
            / E2E \         (5-10 tests, slow, high confidence)
           /______\
          /        \
         /Integration\      (20-50 tests, medium speed)
        /______________\
       /                \
      /    Unit Tests    \  (100+ tests, fast, focused)
     /____________________\
```

### 8.2 Test Categories

| Category | Scope | Tools | Examples |
|----------|-------|-------|----------|
| Unit | Single function/class | pytest, mock | `test_parse_wal2json_v2`, `test_idempotency_key` |
| Integration | Service + real deps | testcontainers | `test_ingestor_to_redis`, `test_kafka_consumer` |
| Failure | Error handling | pytest, mocks | `test_redis_connection_retry`, `test_job_lease_expiry` |
| E2E | Full pipeline | docker-compose | `test_insert_to_replay_complete` |

### 8.3 Critical Test Scenarios

```python
# tests/integration/test_delivery_semantics.py

class TestDeliverySemantics:
    """Verify at-least-once with idempotency guarantees."""

    async def test_duplicate_events_are_skipped(self, replayer, dedup_store):
        """Same event sent twice should only be applied once."""
        event = create_test_event(lsn="0/123", table="public.events")

        # First replay
        resp1 = await replayer.replay_event(event)
        assert resp1.success is True
        assert resp1.was_duplicate is False

        # Second replay (duplicate)
        resp2 = await replayer.replay_event(event)
        assert resp2.success is True
        assert resp2.was_duplicate is True

    async def test_replay_survives_worker_restart(self, job_factory, worker_manager):
        """Job continues from checkpoint after worker restart."""
        job = await job_factory.create(events_total=1000)

        # Start worker, let it process some events
        await worker_manager.start()
        await asyncio.sleep(5)

        # Kill worker mid-job
        await worker_manager.stop()

        # Check checkpoint saved
        job = await job_factory.refresh(job.id)
        assert job.events_processed > 0
        assert job.events_processed < 1000
        assert job.last_processed_id is not None

        # Restart worker
        await worker_manager.start()
        await asyncio.sleep(10)

        # Verify completion from checkpoint (not restart)
        job = await job_factory.refresh(job.id)
        assert job.status == "completed"
        assert job.events_processed == 1000
```

### 8.4 Failure Mode Tests

```python
# tests/failure/test_infrastructure_failures.py

class TestRedisFailures:
    async def test_ingestor_retries_redis_connection(self, ingestor, mock_redis):
        """Ingestor retries on Redis connection failure."""
        mock_redis.side_effect = [
            redis.ConnectionError(),
            redis.ConnectionError(),
            MagicMock(),  # Success on 3rd try
        ]

        await ingestor.connect_redis()
        assert mock_redis.call_count == 3

    async def test_replay_falls_back_to_kafka_when_redis_empty(
        self, replay_router, redis_client, kafka_consumer
    ):
        """Historical replay uses Kafka when Redis data is trimmed."""
        # Request replay from 1 week ago (beyond Redis retention)
        start_ms = int((time.time() - 7 * 24 * 3600) * 1000)
        end_ms = start_ms + 3600000

        source = replay_router.get_source(start_ms, end_ms)
        assert source.source_name() == "kafka"


class TestKafkaFailures:
    async def test_ingestor_buffers_on_kafka_unavailable(
        self, ingestor, mock_kafka
    ):
        """Ingestor continues to Redis when Kafka is down."""
        mock_kafka.send.side_effect = KafkaError("Broker not available")

        # Should still write to Redis, log error for Kafka
        await ingestor.process_event(test_event)

        assert ingestor.metrics["events_published_redis"] == 1
        assert ingestor.metrics["kafka_errors"] == 1
```

---

## 9. Developer Experience

### 9.1 Makefile

**File:** `Makefile`
```makefile
.PHONY: help install proto up down logs test lint fmt

help:
	@echo "WalStream Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install      Install all dependencies"
	@echo "  make proto        Generate protobuf files"
	@echo ""
	@echo "Development:"
	@echo "  make up           Start all services"
	@echo "  make up-full      Start with monitoring stack"
	@echo "  make down         Stop all services"
	@echo "  make logs         Follow all logs"
	@echo "  make logs-SVC     Follow specific service (e.g., make logs-ingestor)"
	@echo ""
	@echo "Testing:"
	@echo "  make test         Run all tests"
	@echo "  make test-unit    Run unit tests only"
	@echo "  make test-int     Run integration tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         Run linters"
	@echo "  make fmt          Format code"
	@echo "  make typecheck    Run mypy"

install:
	pip install -e walstream-proto/
	pip install -r requirements-dev.txt
	cd control && pip install -r requirements.txt
	cd ingestor && pip install -r requirements.txt
	cd replayer && pip install -r requirements.txt
	cd worker && pip install -r requirements.txt
	pre-commit install

proto:
	cd walstream-proto && python -m walstream_proto.generate

up:
	docker compose up -d postgres redis kafka zookeeper
	@echo "Waiting for infrastructure..."
	@sleep 10
	docker compose up -d ingestor replayer control worker

up-full:
	docker compose --profile monitoring up -d

down:
	docker compose --profile monitoring down

logs:
	docker compose logs -f

logs-%:
	docker compose logs -f $*

test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit -v

test-int:
	pytest tests/integration -v --tb=short

lint:
	ruff check .

fmt:
	ruff format .
	ruff check --fix .

typecheck:
	mypy --strict walstream-proto/ control/app/ ingestor/ replayer/

# Database
db-migrate:
	cd control && alembic upgrade head

db-revision:
	cd control && alembic revision --autogenerate -m "$(MSG)"
```

### 9.2 Quick Start

```bash
# 1. Clone and setup
git clone <repo>
cd walstream

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
make install

# 4. Generate protobuf
make proto

# 5. Start services
make up

# 6. Create test data
psql -h localhost -U postgres -d shadowdb -c \
  "INSERT INTO events (name) VALUES ('test1'), ('test2');"

# 7. Watch logs
make logs

# 8. Access API
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/jobs

# 9. Stop
make down
```

---

## 10. Appendix

### 10.1 Implementation Order Summary

| Phase | Focus | Key Deliverables |
|-------|-------|------------------|
| **Phase 0** | Critical Fixes | SQL fixes, threading fixes, Django config |
| **Phase 1** | Proto Packaging | Versioned proto package, generation scripts |
| **Phase 2** | Ingestor | Full wal2json parsing, retention policies |
| **Phase 3** | FastAPI Control | REST API, durable workers, replay routing |
| **Phase 4** | Security | JWT auth, RBAC, audit logging |
| **Phase 5** | Observability | Metrics, alerting rules, Grafana dashboards |
| **Phase 6** | Testing | Unit, integration, failure mode tests |
| **Phase 7** | Infrastructure | Docker Compose, CI/CD |

### 10.2 Configuration Reference

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `REDIS_STREAM_MAXLEN` | ingestor | 100000 | Max events in Redis stream |
| `REDIS_REPLAY_THRESHOLD_MS` | control | 3600000 | 1h - threshold for Redis vs Kafka |
| `KAFKA_RETENTION_MS` | kafka | 604800000 | 7 days |
| `DEDUP_TTL_SECONDS` | replayer | 604800 | 7 days |
| `JOB_LEASE_DURATION_SECONDS` | worker | 300 | 5 minutes |
| `JOB_HEARTBEAT_INTERVAL_SECONDS` | worker | 10 | Lease renewal interval |

### 10.3 Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Replay source of truth | **Kafka** for history, Redis for live tail | Kafka scales, Redis is ephemeral |
| Delivery semantics | **At-least-once with idempotency** | Exactly-once too complex |
| Dedup location | **Replayer** (centralized) | Single enforcement point |
| Job execution | **Dedicated workers with leases** | Survives restarts |
| Primary API | **REST** | Easier to debug, secure |
| gRPC usage | **Internal only** (replayer) | High-throughput internal |
| Async Kafka client | **aiokafka** | Native asyncio, non-blocking |
| Shared models | **walstream-common** library | Cross-service model sharing without coupling |
| Checkpoint format | **Per-partition JSON** | Handles rebalances correctly |

---

*Document Version: 4.0*
*Last Updated: Fixed async/sync consistency (aiokafka throughout), centralized dedup in Replayer only, removed unnecessary CREATE PUBLICATION, compacted verbose sections*
