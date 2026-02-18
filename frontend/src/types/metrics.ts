export interface ParsedMetric {
  name: string;
  labels: Record<string, string>;
  value: number;
  timestamp?: number;
}

export interface MetricsResponse {
  ingestor: ParsedMetric[];
  control: ParsedMetric[];
  replayer: ParsedMetric[];
  fetchedAt: number;
  errors: string[];
}

export interface MetricsSnapshot {
  // Ingestor metrics
  events_ingested_total: number;
  events_published_redis_total: number;
  events_published_kafka_total: number;
  ingest_errors_total: number;
  redis_stream_length: number;
  wal_lag_bytes: number;
  ingest_latency_p50: number;
  ingest_latency_p90: number;
  ingest_latency_p99: number;

  // Replayer metrics
  events_replayed_total: number;
  events_duplicates_total: number;
  events_failed_total: number;
  replay_latency_p50: number;
  replay_latency_p90: number;
  replay_latency_p99: number;

  // Computed rates (events per second)
  ingest_rate: number;
  replay_rate: number;

  // By operation
  events_by_operation: Record<string, number>;

  // Timestamp
  timestamp: number;
}

export interface TimeSeriesPoint {
  timestamp: number;
  value: number;
  label?: string;
}

export interface LatencyData {
  p50: number;
  p90: number;
  p99: number;
  timestamp: number;
}
