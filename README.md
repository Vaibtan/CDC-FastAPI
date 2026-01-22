# WalStream CDC

Enterprise Change Data Capture Platform with FastAPI, PostgreSQL, Redis, and Kafka.

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

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- uv (recommended) or pip

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

### 2. Start All Services

```bash
# Start infrastructure (PostgreSQL with WAL enabled, Redis, Kafka)
docker-compose up -d postgres postgres-control redis zookeeper kafka

# Wait for services to be healthy
docker-compose ps

# Start application services
docker-compose up -d ingestor control replayer worker
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

### 3. Verify Setup

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

### 4. Access Services

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

### 4. Run Alembic Migrations

```bash
cd control
alembic upgrade head
cd ..
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
const ws = new WebSocket('ws://localhost:8000/api/v1/events/ws');
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

## Project Structure

```
CDC-FastAPI/
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
│   │   │   └── dedup_store.py    # Deduplication store
│   │   └── workers/           # Background workers
│   │       ├── job_worker.py  # Durable job execution
│   │       └── manager.py     # Worker pool manager
│   ├── alembic/               # Database migrations
│   └── tests/                 # Test suite
│
├── replayer/                  # gRPC replay service
│   └── server.py              # Replayer with centralized dedup
│
├── worker/                    # Kafka consumer utilities
│   ├── main.py                # Simple Redis worker
│   └── consumer_group.py      # Parallel Kafka consumers
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
| `SECRET_KEY` | JWT signing key | (change in production) |

## Delivery Semantics

**At-Least-Once with Idempotency**:

1. Events may be delivered multiple times due to retries or worker restarts
2. Replayer enforces centralized deduplication using `(lsn, table, pk_hash)` key
3. Dedup state stored in PostgreSQL with 7-day TTL
4. Workers trust Replayer for dedup - no local dedup to avoid race conditions

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

## License

MIT
