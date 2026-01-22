-- WalStream CDC Database Initialization
-- This script initializes the PostgreSQL database for CDC operations

-- Create events table for testing CDC
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create replication user with proper permissions (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'repluser') THEN
        CREATE USER repluser WITH REPLICATION LOGIN PASSWORD 'replpass';
    END IF;
END
$$;

-- Grant necessary permissions for logical replication
GRANT SELECT ON ALL TABLES IN SCHEMA public TO repluser;
GRANT USAGE ON SCHEMA public TO repluser;

-- Create dedup schema for idempotency tracking
CREATE SCHEMA IF NOT EXISTS walstream_dedup;

-- Create processed events table for deduplication (used by Replayer)
CREATE TABLE IF NOT EXISTS walstream_dedup.processed_events (
    idempotency_key VARCHAR(255) PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    job_id VARCHAR(36),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);

CREATE INDEX IF NOT EXISTS idx_processed_events_expires
    ON walstream_dedup.processed_events(expires_at);

-- Note: No CREATE PUBLICATION needed - we use wal2json output plugin
-- which works directly with logical replication slots, not publications
