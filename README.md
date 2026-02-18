# WalStream CDC

Enterprise Change Data Capture Platform with FastAPI, PostgreSQL, Redis, Kafka, and Next.js.

## Overview

WalStream is a production-ready CDC (Change Data Capture) system that:

- Captures PostgreSQL WAL changes in real-time using `wal2json` format-version 2
- Dual-writes to Redis Streams (low-latency buffer) and Kafka (durable archive)
- Provides speed-controlled replay with idempotency guarantees
- Offers a REST API control plane with JWT authentication
- Includes real-time WebSocket event streaming
- Uses async-native libraries throughout (aiokafka, redis.asyncio, grpc.aio)

## Architecture

```
PostgreSQL (WAL with wal2json v2)
       |
       v
   Ingestor ----+----> Redis Stream (live buffer, ~1hr, MAXLEN trimmed)
       |        |
       |        +----> Kafka Topic (durable archive, 7 days, idempotent producer)
       |
       v
   Prometheus Metrics (:9090)

                     +------------------+
                     |  Replay Router   |
                     | Redis < 1hr age  |
                     | Kafka >= 1hr age |
                     +--------+---------+
                              |
                              v
   FastAPI Control Plane (:8000)
       |
       +---> Job Workers (lease-based, checkpoint/resume)
       |           |
       |           v
       |    +------------------+
       |    | gRPC Replayer    |
       |    | (centralized     |
       |    |  deduplication)  |
       |    +--------+---------+
       |             |
       |             v
       |      Target Database
       |
       +---> WebSocket Events (/api/v1/events/ws)
       +---> REST API (/api/v1/docs)
       +---> Prometheus Metrics (:9091)
```

## Architectural Decisions (As of February 15, 2026)

- **FastAPI control plane over Django**: Legacy Django scaffolding was removed and all control-plane features live in `control/app/`.
- **Centralized dedup in Replayer**: Workers do not maintain local dedup state; idempotency is enforced in `replayer/server.py`.
- **At-least-once replay semantics**: Replayer uses `exists -> apply -> mark_processed` so failed applies are retried instead of being pre-marked as duplicates.
- **Fail-fast job progression on unreplayable events**: Workers retry each event up to `MAX_EVENT_RETRIES` times after the initial attempt; if still failing, the job is marked `FAILED` without advancing checkpoint beyond the failed event.
- **Dual replay source strategy**: Replay router serves recent/small windows from Redis and historical/large windows from Kafka.
- **Source-pinned resume behavior**: Resumed jobs reuse their original `replay_source` to avoid cross-source checkpoint mismatches (for example Redis stream IDs interpreted as Kafka offsets).
- **Per-partition Kafka checkpoints**: Kafka progress is stored in JSON (`checkpoint`) keyed by partition, while `last_processed_id` is retained as a fallback string checkpoint.
- **Safe Kafka partition seek semantics**: On resume, uncheckpointed partitions seek to `start_ms`; if no offset exists at/after `start_ms`, they seek to partition end to avoid replaying out-of-window historical data.
- **Lease-based worker ownership**: Job execution uses DB-backed leases plus renewal to prevent concurrent workers from processing the same job.
- **Async I/O across services**: `aiokafka`, `redis.asyncio`, `grpc.aio`, and async SQLAlchemy are used to keep ingestion and replay non-blocking.
- **JWT auth for REST and WebSocket**: API routes and WebSocket stream are token-authenticated to keep monitoring and control endpoints private.

## Frontend Dashboard

WalStream includes a modern web dashboard built with Next.js 14:

```
Frontend (Next.js 14 + TypeScript)
       |
       +---> /login          - JWT Authentication
       +---> /                - Dashboard Overview
       +---> /jobs            - Replay Job Management
       +---> /jobs/new        - Create New Job
       +---> /jobs/[id]       - Job Details & Actions
       +---> /events          - Real-time Event Stream
       +---> /metrics         - Prometheus Metrics Dashboard
```

### Frontend Tech Stack

- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **UI Components**: shadcn/ui + Tailwind CSS
- **State Management**: Zustand (auth, events)
- **Server State**: TanStack Query (React Query)
- **Charts**: Recharts
- **Virtualization**: @tanstack/react-virtual

## Features

- **Real-time Change Capture**: PostgreSQL logical replication via WAL streaming
- **Dual Storage Pipeline**: Redis Streams for live tail, Kafka for historical replay
- **At-Least-Once Delivery**: With centralized deduplication at the Replayer
- **Speed-Controlled Replay**: Configurable 0.1x to 100x replay speed
- **Durable Job Execution**: Lease-based workers with checkpoint/resume
- **REST API**: FastAPI-based control plane with OpenAPI docs
- **WebSocket Streaming**: Real-time event monitoring
- **Prometheus Metrics**: Full observability for all components
- **Async-Native**: aiokafka, redis.asyncio, grpc.aio for non-blocking I/O
- **Docker Ready**: Complete docker-compose setup
- **Modern Frontend**: Next.js 14 dashboard with real-time updates

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- uv (recommended) or pip
- Node.js 18+ (for frontend development)

### Database Architecture

WalStream uses **two PostgreSQL databases**:

| Database | Port | Purpose |
|----------|------|---------|
| `postgres` (walstreamdb) | 5432 | Source database with WAL for CDC capture |
| `postgres-control` | 5433 | Control plane database (jobs, users, dedup state) |

---

## Option A: Docker Setup (Recommended)

### 1. Clone & Configure

```bash
git clone <repo-url>
cd CDC-FastAPI
cp .env.example .env
```

### 2. Start Infrastructure

```bash
# Start databases, Redis, and Kafka
docker-compose up -d postgres postgres-control redis zookeeper kafka

# Wait until all infrastructure services are healthy
docker-compose ps
```

### 3. Run Database Migrations (Required Before First Start)

The control plane verifies the database schema on startup and **will refuse to
start** if migrations have not been applied. Run Alembic from inside the
control image (which already includes the migration files):

```bash
# Build the control image once
docker-compose build control

# Apply migrations to the control-plane database
docker-compose run --rm control alembic upgrade head

# (Optional) Verify the current revision
docker-compose run --rm control alembic current
```

Or, if you have Python + dependencies installed locally:

```bash
make migrate          # runs: cd control && alembic upgrade head
make migrate-check    # shows current revision
```

> **Why migration-first?**  The control plane calls `check_db_revision()` at
> startup and compares the database's Alembic head against the expected
> revision compiled into the code. A mismatch raises `RuntimeError` and exits
> immediately. This prevents the application from running against a stale
> schema.

### 4. Start Application Services

```bash
docker-compose up -d ingestor control replayer worker frontend
```

The Docker setup automatically:
- Configures PostgreSQL with `wal_level=logical`
- Runs `db/init.sql` to create tables and replication user

> **Note**: The default `postgres:16-alpine` image does NOT include wal2json.
> For production, use an image with wal2json pre-installed, or build a custom image:
> ```dockerfile
> FROM postgres:16
> RUN apt-get update && apt-get install -y postgresql-16-wal2json && rm -rf /var/lib/apt/lists/*
> ```

### 5. Verify Setup

```bash
# Check all services are running
docker-compose ps

# Check PostgreSQL replication is configured
docker exec walstream-postgres psql -U postgres -c "SHOW wal_level;"
# Should output: logical

# Check replication user exists
docker exec walstream-postgres psql -U postgres -c "SELECT rolname FROM pg_roles WHERE rolreplication = true;"
# Should show: repluser
```

### 6. Access Services

- **Frontend Dashboard**: http://localhost:3000
- **API Docs**: http://localhost:8000/api/v1/docs
- **Health Check**: http://localhost:8000/api/v1/health/live
- **Metrics (Ingestor)**: http://localhost:9090/metrics
- **Metrics (Control)**: http://localhost:9091/metrics
- **Metrics (Replayer)**: http://localhost:9092/metrics

---

## Option B: Manual/Local Setup

### 1. Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e ".[dev]"

# Generate protobuf files
cd walstream-proto
python -m walstream_proto.generate
cd ..
```

### 2. PostgreSQL Setup (Source Database)

#### 2.1 Configure WAL for Logical Replication

Edit `postgresql.conf`:

```ini
# Required for logical replication
wal_level = logical
max_replication_slots = 10
max_wal_senders = 10
```

Restart PostgreSQL after changing these settings.

#### 2.2 Install wal2json Extension

```bash
# Ubuntu/Debian
sudo apt-get install postgresql-16-wal2json

# macOS with Homebrew
brew install wal2json

# Or build from source
git clone https://github.com/eulerto/wal2json.git
cd wal2json
make && sudo make install
```

#### 2.3 Create Database and Replication User

```bash
# Connect as superuser
psql -U postgres
```

```sql
-- Create the source database
CREATE DATABASE walstreamdb;

-- Connect to it
\c walstreamdb

-- Create events table for testing
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create replication user
CREATE USER repluser WITH REPLICATION LOGIN PASSWORD 'replpass';

-- Grant permissions
GRANT SELECT ON ALL TABLES IN SCHEMA public TO repluser;
GRANT USAGE ON SCHEMA public TO repluser;

-- Verify wal2json is installed
SELECT * FROM pg_available_extensions WHERE name = 'wal2json';
```

#### 2.4 Configure pg_hba.conf

Add this line to allow replication connections:

```
# TYPE  DATABASE        USER            ADDRESS                 METHOD
host    replication     repluser        127.0.0.1/32            md5
host    replication     repluser        ::1/128                 md5
```

Reload PostgreSQL:
```bash
sudo systemctl reload postgresql
# or
pg_ctl reload
```

### 3. PostgreSQL Setup (Control Plane Database)

```bash
psql -U postgres
```

```sql
-- Create control plane database
CREATE DATABASE walstream_control;

-- Connect to it
\c walstream_control

-- Create dedup schema
CREATE SCHEMA IF NOT EXISTS walstream_dedup;

-- Create processed events table for deduplication
CREATE TABLE IF NOT EXISTS walstream_dedup.processed_events (
    idempotency_key VARCHAR(255) PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    job_id VARCHAR(36),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);

CREATE INDEX IF NOT EXISTS idx_processed_events_expires
    ON walstream_dedup.processed_events(expires_at);
```

### 4. Run Alembic Migrations (Required Before First Start)

The control plane will **fail fast** on startup if the database schema is
behind the expected Alembic head revision. Always run migrations before
starting the control service:

```bash
cd control
alembic upgrade head
cd ..

# Verify (optional)
cd control && alembic current && cd ..
```

Or via Makefile:

```bash
make migrate          # runs: cd control && alembic upgrade head
make migrate-check    # shows current DB revision
```

### 5. Start Redis and Kafka

```bash
# Using Docker for infrastructure only
docker-compose up -d redis zookeeper kafka
```

Or install locally:
- Redis: https://redis.io/docs/getting-started/
- Kafka: https://kafka.apache.org/quickstart

### 6. Configure Environment

Update `.env` with your local settings:

```bash
# Source database (with WAL)
POSTGRES_HOST=localhost
POSTGRES_USER=repluser
POSTGRES_PASSWORD=replpass
POSTGRES_DB=walstreamdb

# Control plane database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/walstream_control

# Redis
REDIS_URL=redis://localhost:6379/0

# Kafka
KAFKA_BROKER=localhost:29092
```

### 7. Start Services (Local Development)

```bash
# Terminal 1: Control plane
cd control && uvicorn app.main:app --reload --port 8000

# Terminal 2: Ingestor
python ingestor/ingestor.py

# Terminal 3: Replayer
python replayer/server.py

# Terminal 4: Frontend (optional)
cd frontend && npm install && npm run dev
```

---

## Verify CDC is Working

### 1. Create Test Data

```bash
# Insert data into source database
docker exec walstream-postgres psql -U postgres -d walstreamdb -c \
  "INSERT INTO events (name, payload) VALUES ('test', '{\"key\": \"value\"}');"
```

### 2. Check Ingestor Logs

```bash
docker logs -f walstream-ingestor
# Should show: Ingested: INSERT on public.events (LSN: ...)
```

### 3. Check Redis Stream

```bash
docker exec walstream-redis redis-cli XLEN walstream:events
# Should show count > 0

docker exec walstream-redis redis-cli XRANGE walstream:events - + COUNT 1
# Should show the event
```

### 4. Check Kafka Topic

```bash
docker exec walstream-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic walstream.archive \
  --from-beginning \
  --max-messages 1
```

---

## Troubleshooting

### "FATAL: no pg_hba.conf entry for replication connection"

Add replication entry to `pg_hba.conf` (see step 2.4 above).

### "wal2json not found"

Install the wal2json extension for your PostgreSQL version.

### "replication slot already exists"

```sql
-- List existing slots
SELECT * FROM pg_replication_slots;

-- Drop if needed
SELECT pg_drop_replication_slot('walstream_slot');
```

### "could not access file 'wal2json'"

Ensure wal2json is installed in PostgreSQL's lib directory and restart PostgreSQL.

## API Usage

### Authentication

```bash
# Register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "email": "admin@example.com", "password": "secret123"}'

# Get token
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=admin&password=secret123" | jq -r '.access_token')
```

### Replay Jobs

```bash
# Create replay job
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2024-01-15T00:00:00Z",
    "end_time": "2024-01-15T01:00:00Z",
    "speed_factor": 2.0
  }'

# Start the job
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/start \
  -H "Authorization: Bearer $TOKEN"

# Check job status
curl http://localhost:8000/api/v1/jobs/{job_id} \
  -H "Authorization: Bearer $TOKEN"

# Pause a running job
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/pause \
  -H "Authorization: Bearer $TOKEN"

# Resume a paused job
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/resume \
  -H "Authorization: Bearer $TOKEN"

# Cancel a job
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/cancel \
  -H "Authorization: Bearer $TOKEN"
```

### WebSocket Events

```javascript
const token = '<jwt>';
const ws = new WebSocket(`ws://localhost:8000/api/v1/events/ws?token=${token}`);
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

## Project Structure

```
CDC-FastAPI/
├── frontend/                  # Next.js 14 web dashboard
│   ├── src/
│   │   ├── app/               # App Router pages
│   │   │   ├── (auth)/        # Auth layout (login)
│   │   │   ├── (dashboard)/   # Dashboard layout (protected)
│   │   │   └── api/           # API routes (metrics proxy)
│   │   ├── components/        # React components
│   │   │   ├── ui/            # shadcn/ui components
│   │   │   ├── layout/        # Sidebar, Header
│   │   │   ├── auth/          # AuthGuard
│   │   │   ├── errors/        # ErrorBoundary, ErrorFallback
│   │   │   ├── jobs/          # Job management
│   │   │   ├── events/        # Event stream
│   │   │   └── metrics/       # Charts & gauges
│   │   ├── hooks/             # Custom React hooks
│   │   ├── stores/            # Zustand stores (auth, events)
│   │   ├── lib/               # API client, utilities
│   │   ├── types/             # TypeScript types
│   │   └── middleware.ts       # Auth route protection
│   ├── Dockerfile             # Multi-stage Docker build
│   └── package.json
│
├── walstream-proto/           # Protobuf definitions & Pydantic models
│   ├── proto/v1/              # .proto files (ChangeRecord, ReplayRequest, etc.)
│   ├── walstream_proto/       # Python package
│   │   ├── models.py          # Pydantic models for REST API
│   │   ├── generate.py        # Proto generation script
│   │   └── v1/                # Generated protobuf code
│   └── tests/                 # Compatibility tests
│
├── ingestor/                  # WAL capture & dual-write service
│   └── ingestor.py            # Main ingestor with wal2json v2 parsing
│
├── control/                   # FastAPI control plane
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── config.py          # Pydantic Settings configuration
│   │   ├── database.py        # Async SQLAlchemy setup
│   │   ├── api/
│   │   │   ├── deps.py        # Dependency injection (auth, db)
│   │   │   └── v1/            # REST endpoints
│   │   │       ├── auth.py    # Authentication (JWT)
│   │   │       ├── jobs.py    # Replay job management
│   │   │       ├── events.py  # WebSocket streaming
│   │   │       └── health.py  # Health checks
│   │   ├── models/            # SQLAlchemy ORM models
│   │   │   ├── replay_job.py  # ReplayJob with lease support
│   │   │   ├── user.py        # User model
│   │   │   └── dedup_state.py # Deduplication state
│   │   ├── services/          # Business logic
│   │   │   ├── replay_router.py  # Redis/Kafka source routing
│   │   │   └── dedup_store.py    # Legacy dedup utility (not in active replay path)
│   │   └── workers/           # Background workers
│   │       ├── job_worker.py  # Durable job execution
│   │       └── manager.py     # Worker pool manager
│   ├── alembic/               # Database migrations
│   └── tests/                 # Test suite
│
├── replayer/                  # gRPC replay service
│   └── server.py              # Replayer with centralized dedup
│
├── db/                        # Database initialization
│   └── init.sql               # PostgreSQL setup script
│
├── monitoring/                # Observability
│   └── prometheus.yml         # Prometheus configuration
│
├── docker-compose.yml         # Complete stack definition
├── pyproject.toml             # Root project configuration
└── .env.example               # Environment template
```

## Configuration

See `.env.example` for all configuration options. Key settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Control plane PostgreSQL | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `REDIS_STREAM_MAXLEN` | Max events in Redis | `100000` |
| `KAFKA_BROKER` | Kafka bootstrap server | `localhost:9092` |
| `KAFKA_TOPIC` | Archive topic name | `walstream.archive` |
| `REPLAYER_HOST` | gRPC replayer host | `localhost` |
| `REPLAYER_PORT` | gRPC replayer port | `50051` |
| `JOB_WORKER_COUNT` | Parallel job workers | `4` |
| `JOB_LEASE_DURATION_SECONDS` | Worker lease TTL | `300` |
| `MAX_EVENT_RETRIES` | Retries per event (after initial attempt) before job fails | `3` |
| `SECRET_KEY` | JWT signing key | (change in production) |

### Frontend Configuration (frontend/.env.local)

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |
| `NEXT_PUBLIC_WS_URL` | WebSocket URL | `ws://localhost:8000` |
| `PROMETHEUS_INGESTOR_URL` | Ingestor metrics | `http://localhost:9090/metrics` |
| `PROMETHEUS_CONTROL_URL` | Control metrics | `http://localhost:9091/metrics` |
| `PROMETHEUS_REPLAYER_URL` | Replayer metrics | `http://localhost:9092/metrics` |

## Delivery Semantics

**At-Least-Once with Idempotency**:

1. Events may be delivered multiple times due to retries or worker restarts
2. Replayer enforces centralized deduplication using `(lsn, table, pk_hash)` key
3. Replayer marks dedup state only after successful apply (`exists -> apply -> mark_processed`)
4. Dedup state stored in PostgreSQL with 7-day TTL
5. Workers trust Replayer for dedup - no local dedup to avoid race conditions
6. Worker retries each failed event up to `MAX_EVENT_RETRIES` times after the initial attempt, then fails the job without moving checkpoint past that event
7. Kafka resume checkpoints are tracked per partition in JSON (`checkpoint`) and serialized back into the replay source on resume
8. Resumed jobs reuse their stored replay source; Kafka partitions without a resume offset seek by timestamp, then to end if no in-range offset exists

**Idempotent Producer**:

- Kafka producer uses `enable_idempotence=True` to prevent duplicates from retries

## Monitoring

Start the monitoring stack:

```bash
docker-compose --profile monitoring up -d
```

- **Prometheus**: http://localhost:9099
- **Grafana**: http://localhost:3001 (admin/admin)

### Key Metrics

| Metric | Description |
|--------|-------------|
| `walstream_events_ingested_total` | Events captured from WAL |
| `walstream_events_published_redis_total` | Events written to Redis |
| `walstream_events_published_kafka_total` | Events written to Kafka |
| `walstream_events_replayed_total` | Events successfully replayed |
| `walstream_events_duplicates_total` | Duplicate events skipped |
| `walstream_events_failed_total` | Failed replay attempts |
| `walstream_ingest_latency_seconds` | WAL-to-publish latency |
| `walstream_replay_latency_seconds` | Per-event replay latency |

### SLO Targets & Alert Thresholds

| SLO | Target | Alert Threshold | Alert Name | Severity |
|-----|--------|-----------------|------------|----------|
| Ingest availability | Events flowing continuously | 0 events/5min | `IngestorStalled` | critical |
| Ingest latency (p99) | < 1s WAL-to-publish | p99 > 1s for 5min | `HighIngestLatency` | warning |
| Replay availability | Events replayed while jobs are active | 0 events/10min with queued/running jobs | `ReplayerStalled` | critical |
| Replay success rate | > 95% | Failure rate > 5% for 5min | `ReplayerHighFailureRate` | warning |
| Replay latency (p99) | < 500ms | p99 > 500ms for 5min | `HighReplayLatency` | warning |
| Redis buffer headroom | < 90% of MAXLEN | > 90,000 entries for 2min | `RedisStreamNearCapacity` | warning |
| Kafka consumer lag | < 10,000 messages | > 10,000 for 5min | `KafkaConsumerLagCritical` | critical |
| Job lease integrity | No orphaned leases | Running job with expired lease for 1min | `JobLeaseExpiredWithRunningState` | warning |
| DB schema alignment | Alembic head matches code | Checked at startup; mismatch = fail-fast | `ControlPlaneDown` (startup failure symptom) | critical |

Alert rules are defined in `monitoring/alertmanager/rules/walstream.yml`. Alertmanager routes critical alerts to PagerDuty and warning alerts to Slack (configure in `monitoring/alertmanager/alertmanager.yml`).

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=control --cov=ingestor --cov=replayer

# Format code
ruff format .

# Lint code
ruff check .

# Type check
mypy control/ ingestor/ replayer/
```

### Code Style

This project follows the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
See `google_python_style_guide.md` for a local reference.

---

## Implementation Checklist

> Items marked `[x]` are complete; `[ ]` items remain.

---

### Backend — Phase 0: Critical Fixes

- [x] `db/init.sql` — fixed syntax, idempotent user creation, includes dedup schema
- [x] Removed legacy standalone `worker/` utilities (superseded by `control/app/workers/`)
- [x] Django replaced with FastAPI control plane; legacy Django scaffolding removed

### Backend — Phase 1: Protobuf Packaging & Versioning

- [x] `walstream-proto/` package with `proto/v1/` directory structure
- [x] `walstream.proto` with reserved field ranges and versioning strategy
- [x] **Generated pb2 files** — `walstream_pb2.py` and `walstream_pb2_grpc.py` are present under `walstream-proto/walstream_proto/v1/`
- [x] Pydantic models (`walstream_proto/models.py`) with `from_protobuf` / `to_protobuf` / `idempotency_key`
- [x] Compatibility tests (`walstream-proto/tests/test_compatibility.py`)

### Backend — Phase 2: Ingestor Enhancement

- [x] Full `wal2json` format-version 2 parsing (`parse_wal2json_v2`) with operation/old/new extraction
- [x] Redis `XADD` with `MAXLEN` trimming (100K, approximate)
- [x] Prometheus metrics (7 metrics: ingested, published, errors, lag, latency)
- [x] Signal handling (SIGTERM/SIGINT) with graceful shutdown and auto-restart loop
- [x] Kafka idempotent producer (`enable_idempotence=True`)

### Backend — Phase 3: FastAPI Control Plane

- [x] `control/app/config.py` — Pydantic Settings with all env vars
- [x] `control/app/database.py` — async SQLAlchemy engine + session factory
- [x] `control/app/models/` — User, ReplayJob (with lease fields), ProcessedEvent (dedup)
- [x] `control/app/api/v1/jobs.py` — full CRUD + start/pause/resume/cancel endpoints
- [x] `control/app/api/v1/auth.py` — JWT token, register, /me
- [x] `control/app/api/v1/events.py` — WebSocket live streaming, /stream/stats, /recent
- [x] `control/app/api/v1/health.py` — liveness + readiness probes with component checks
- [x] `control/app/services/replay_router.py` — Redis/Kafka source selection with source-pinned resume and safe partition seek behavior
- [x] `control/app/services/dedup_store.py` — retained legacy utility module (active dedup is centralized in Replayer)
- [x] `control/app/workers/job_worker.py` — lease-based acquisition, renewal, fail-fast replay, and per-partition checkpoint/resume
- [x] `control/app/workers/manager.py` — worker pool manager
- [x] Alembic migrations directory scaffold
- [x] Alembic revision files for controlled schema evolution (3 migrations: initial, RBAC+audit, API keys)
- [x] Remove production startup `create_all` path; use migration-only schema bootstrap
- [x] Add startup DB revision guard (fail fast when DB is behind expected Alembic head)
- [x] Pause/cancel API transitions must clear `worker_id` + `lease_expires_at` atomically
- [x] Separate read/write DB session policy (no implicit commit on read-only request paths)
- [x] Service-layer transaction boundaries for multi-step job state transitions

### Backend — Phase 4: gRPC Replayer

- [x] `replayer/server.py` — centralized dedup enforcement (`exists -> apply -> mark_processed`)
- [x] `PostgreSQLTargetApplier` — INSERT/UPDATE/DELETE/TRUNCATE with ON CONFLICT handling
- [x] `LoggingTargetApplier` — dry-run testing
- [x] Health RPC endpoint
- [x] Prometheus metrics (replayed, duplicates, failed, latency)
- [x] Automatic dedup entry cleanup task

### Backend — Phase 5: Security & Authentication

- [x] JWT authentication (OAuth2PasswordBearer, token generation/validation)
- [x] User model with `is_active`, `is_superuser` flags
- [x] CORS middleware configured (origins via settings)
- [x] Middleware stale-token handling with deterministic recovery path (`AuthContextMiddleware` + `X-Token-Expired` header)
- [x] Align middleware/API auth validation behavior (`AuthContextMiddleware` feeds identity to audit; deps distinguish expired vs missing tokens)
- [x] **Role-based authorization (RBAC)** — admin/operator/viewer hierarchy with `require_role` dependency
- [x] **Audit logging** — `AuditLog` model and middleware for mutation tracking
- [x] **Rate limiting middleware**
- [x] **API key support** for service-to-service auth

### Backend — Phase 6: Observability & Alerting

- [x] Prometheus metrics on all services (ingestor :9090, control :9091, replayer :9092)
- [x] `monitoring/prometheus.yml` scrape config
- [x] Prometheus + Grafana in docker-compose (monitoring profile)
- [x] **Alerting rules** (`monitoring/alertmanager/rules/walstream.yml`) — IngestorStalled, RedisStreamNearCapacity, ReplayerStalled, KafkaConsumerLagCritical, etc.
- [x] Alerts for replay lease/state inconsistency invariants and control-plane availability
- [x] **Alertmanager configuration** — Slack/PagerDuty routing, severity grouping
- [x] **Grafana dashboards** — provisioned JSON dashboards for all services
- [x] **SLO documentation** — alert thresholds, SLO targets, runbook URLs

### Backend — Phase 7: Testing

- [x] `walstream-proto/tests/test_compatibility.py` — proto serialization + Pydantic tests
- [x] `control/tests/test_health.py` — basic health endpoint tests
- [x] **Unit tests** — `test_parse_wal2json_v2`, `test_idempotency_key`, `test_replay_router_source_selection`, `test_rbac`, `test_middleware`
- [x] **Integration tests** — `test_job_lifecycle` (CRUD + full state machine through API), `test_auth` (endpoint auth enforcement)
- [x] **Failure mode tests** — bounded retries, retry exhaustion, checkpoint non-advancement on failure (`test_delivery_semantics`)
- [x] **Delivery semantics tests** — replayer dedup contract (exists→apply→mark), duplicate skipped, failed apply not marked
- [x] Job lifecycle invariant tests — pause/cancel transitions clear lease ownership (`test_job_service`)
- [x] Migration strategy tests — startup fails when DB revision is behind expected Alembic head (`test_migration_guard`)
- [x] Replay resume matrix tests — Redis checkpoint, Kafka single/multi-partition checkpoint, sparse partition checkpoint (`test_replay_resume`)
- [x] Kafka range-boundary tests — partitions with no in-range timestamp offset seek to end (`test_replay_resume`)
- [x] Auth consistency tests — stale token + expired token returns 401 with `X-Token-Expired`, health is public (`test_auth`)
- [ ] **E2E tests** — full pipeline: INSERT → ingest → replay → verify in target

### Backend — Phase 8: Docker & DevEx

- [x] Dockerfiles for all services (ingestor, control, replayer, frontend)
- [x] `docker-compose.yml` — complete stack with health checks, volumes, networking
- [x] **Makefile** — `make up`, `make test`, `make proto`, `make lint`, `make migrate`, `make migrate-check`, `make test-delivery`
- [x] **Clean up legacy Django files** — removed `control/walstream/`, `control/replay/`, and `control/manage.py`
- [x] **.env.example** — root-level env template for easy onboarding
- [x] Migration-first local/dev startup docs and scripts (no runtime schema auto-create in production path)

---

### Frontend — Phase 1: Foundation

- [x] Next.js 14 project with TypeScript, Tailwind CSS, shadcn/ui (19 components)
- [x] API client (`lib/api/client.ts`) with JWT interceptors and 401 redirect
- [x] Auth store (`stores/authStore.ts`) with Zustand persist + cookie sync
- [x] Login page with Zod validation and react-hook-form
- [x] Auth middleware (`middleware.ts`) + client-side `AuthGuard` component
- [x] Dashboard layout with Sidebar and Header
- [x] React Query provider (`lib/providers.tsx`)

### Frontend — Phase 2: Job Management

- [x] Job TypeScript types (`types/job.ts`) with all plan fields + extras
- [x] Jobs API functions (`lib/api/jobs.ts`) — full CRUD + lifecycle actions
- [x] `useJobs` React Query hooks with dynamic polling intervals
- [x] `JobsTable` — sortable, filterable, paginated with inline actions
- [x] `JobStatusBadge` — colored status indicators
- [x] `JobActions` — start/pause/resume/cancel/delete with confirmation dialogs
- [x] `JobDetailPanel` — full info, progress, timeline, stats grid
- [x] `JobCreateForm` — Zod schema, time range presets, speed factor

### Frontend — Phase 3: Real-time Events

- [x] `useWebSocket` hook with auto-reconnect, status tracking, exponential backoff
- [x] Event store (`stores/eventStore.ts`) — Zustand, 1000-event FIFO, filtering, pause
- [x] `EventStream` — virtualized list with `@tanstack/react-virtual`
- [x] `EventCard` — operation-colored event display
- [x] `EventFilters` — table name, operation type, search query
- [x] `EventDetailModal` — full payload view with tabs
- [x] `ConnectionStatus` — WebSocket status indicator

### Frontend — Phase 4: Metrics Dashboard

- [x] Prometheus text parser (`lib/utils/prometheus-parser.ts`) with histogram percentiles
- [x] Metrics API route (`app/api/metrics/route.ts`) — proxies to 3 Prometheus endpoints
- [x] `useMetrics` hooks — raw metrics, snapshot, history with rate calculations
- [x] `EventsLineChart` — ingested vs replayed over time
- [x] `OperationsBarChart` — horizontal bars by operation type
- [x] `LatencyChart` — p50/p90/p99 bar chart
- [x] `ThroughputGauge` — SVG gauge with events/sec
- [x] `ReplayStatusChart`, `RedisStreamCard`, `StatsCard` — extra components
- [x] Auto-refresh via React Query `refetchInterval`

### Frontend — Phase 5: Polish & Integration

- [x] Dashboard overview page with real metrics, health status, recent jobs
- [x] Toast notifications (shadcn/ui Toaster)
- [x] Error boundaries (`ErrorBoundary`, `ErrorFallback`, per-route `error.tsx`)
- [x] `not-found.tsx` — custom 404 page
- [x] Docker config (multi-stage `Dockerfile`, `.dockerignore`)
- [ ] Stale-cookie session handling UX alignment between middleware guards and API 401 handling
- [ ] Degraded readiness/503 UI states for dashboard health cards and overview widgets
- [ ] **Dark/light mode toggle** (`ThemeToggle.tsx`) — Tailwind dark mode is configured but no toggle UI
- [ ] **Mobile responsive sidebar** — no hamburger menu for small screens
- [ ] **Extracted dashboard components** — `OverviewCards`, `RecentJobs`, `HealthStatus`, `QuickActions` are inline in `page.tsx`, not reusable components
- [ ] **UI store** (`stores/uiStore.ts`) — sidebar collapse, theme state
- [ ] **Utility files** — `lib/utils/formatters.ts`, `lib/constants.ts`
- [ ] **Frontend `.env.example`** — environment template for developers
- [ ] **`useDebounce` hook** — for search input debouncing
- [ ] **Dynamic imports** for chart components (code splitting)

### Frontend — Testing

- [ ] **Vitest + Testing Library** — component unit tests
- [ ] **Hook tests** — `renderHook` for useJobs, useWebSocket, useMetrics
- [ ] **MSW integration tests** — API client with mock service worker
- [ ] Middleware/auth tests — stale cookie + invalid token redirect behavior
- [ ] Health contract tests — flat keys (`postgres/redis/kafka`) + `components` map compatibility
- [ ] **Playwright E2E** (optional) — login flow, job lifecycle, event filtering

---

### Not In Original Plan (Bonus Features Completed)

- [x] `useHealth` hook and health API client
- [x] `useEvents` hook for REST event fetching
- [x] Auth cookie sync for server-side middleware
- [x] `RedisStreamCard` — Redis buffer visualization
- [x] `ReplayStatusChart` — replay/duplicate/failed breakdown chart
- [x] `StatsCard` — generic reusable metrics card
- [x] Per-route error pages (`app/error.tsx`, `app/(dashboard)/error.tsx`)

## License

MIT
