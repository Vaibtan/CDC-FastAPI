'use client';

import { useQuery } from '@tanstack/react-query';
import { useRef, useMemo } from 'react';
import {
  type ParsedMetric,
  getMetricValue,
  getMetricsByLabel,
  extractHistogramPercentiles,
  computeRate,
} from '@/lib/utils/prometheus-parser';

interface MetricsResponse {
  timestamp: string;
  ingestor: ParsedMetric[];
  control: ParsedMetric[];
  replayer: ParsedMetric[];
  errors: string[];
}

interface MetricsSnapshot {
  // Ingestor metrics
  eventsIngested: number;
  eventsIngestedByOperation: Record<string, number>;
  ingestorLatencyP50: number;
  ingestorLatencyP90: number;
  ingestorLatencyP99: number;

  // Control plane metrics
  activeJobs: number;
  totalJobsCreated: number;

  // Replayer metrics
  eventsReplayed: number;
  eventsDuplicate: number;
  eventsFailed: number;
  replayerLatencyP50: number;
  replayerLatencyP90: number;
  replayerLatencyP99: number;

  // Redis metrics
  redisStreamLength: number;

  // Computed rates (events/sec)
  ingestRate: number;
  replayRate: number;

  // Errors
  errors: string[];
  timestamp: string;
}

interface MetricsHistory {
  timestamp: number;
  eventsIngested: number;
  eventsReplayed: number;
}

const MAX_HISTORY = 60; // 10 minutes at 10s intervals

async function fetchMetrics(): Promise<MetricsResponse> {
  const response = await fetch('/api/metrics');
  if (!response.ok) {
    throw new Error('Failed to fetch metrics');
  }
  return response.json();
}

export function useRawMetrics(refreshInterval = 10000) {
  return useQuery({
    queryKey: ['metrics', 'raw'],
    queryFn: fetchMetrics,
    refetchInterval: refreshInterval,
    staleTime: refreshInterval - 1000,
  });
}

export function useMetricsSnapshot(refreshInterval = 10000) {
  const previousRef = useRef<{ timestamp: number; snapshot: MetricsSnapshot } | null>(null);
  const historyRef = useRef<MetricsHistory[]>([]);

  const { data, isLoading, error } = useRawMetrics(refreshInterval);

  const snapshot = useMemo<MetricsSnapshot | null>(() => {
    if (!data) return null;

    const allMetrics = [...data.ingestor, ...data.control, ...data.replayer];

    // Extract values
    const eventsIngested = getMetricValue(data.ingestor, 'walstream_events_ingested_total') || 0;
    const eventsReplayed = getMetricValue(data.replayer, 'walstream_events_replayed_total') || 0;
    const eventsDuplicate = getMetricValue(data.replayer, 'walstream_events_duplicate_total') || 0;
    const eventsFailed = getMetricValue(data.replayer, 'walstream_events_failed_total') || 0;
    const redisStreamLength = getMetricValue(allMetrics, 'walstream_redis_stream_length') || 0;
    const activeJobs = getMetricValue(data.control, 'walstream_active_jobs') || 0;
    const totalJobsCreated = getMetricValue(data.control, 'walstream_jobs_created_total') || 0;

    // Events by operation
    const eventsIngestedByOperation = getMetricsByLabel(
      data.ingestor,
      'walstream_events_ingested_total',
      'operation'
    );

    // Latency percentiles
    const ingestorLatency = extractHistogramPercentiles(
      data.ingestor,
      'walstream_ingest_latency_seconds'
    );
    const replayerLatency = extractHistogramPercentiles(
      data.replayer,
      'walstream_replay_latency_seconds'
    );

    // Compute rates
    let ingestRate = 0;
    let replayRate = 0;

    const now = Date.now();
    if (previousRef.current) {
      const intervalMs = now - previousRef.current.timestamp;
      const prevSnapshot = previousRef.current.snapshot;

      ingestRate = computeRate(eventsIngested, prevSnapshot.eventsIngested, intervalMs);
      replayRate = computeRate(eventsReplayed, prevSnapshot.eventsReplayed, intervalMs);
    }

    const newSnapshot: MetricsSnapshot = {
      eventsIngested,
      eventsIngestedByOperation,
      ingestorLatencyP50: ingestorLatency.p50 || 0,
      ingestorLatencyP90: ingestorLatency.p90 || 0,
      ingestorLatencyP99: ingestorLatency.p99 || 0,
      activeJobs,
      totalJobsCreated,
      eventsReplayed,
      eventsDuplicate,
      eventsFailed,
      replayerLatencyP50: replayerLatency.p50 || 0,
      replayerLatencyP90: replayerLatency.p90 || 0,
      replayerLatencyP99: replayerLatency.p99 || 0,
      redisStreamLength,
      ingestRate,
      replayRate,
      errors: data.errors,
      timestamp: data.timestamp,
    };

    // Update history
    historyRef.current = [
      ...historyRef.current,
      { timestamp: now, eventsIngested, eventsReplayed },
    ].slice(-MAX_HISTORY);

    // Store for next rate calculation
    previousRef.current = { timestamp: now, snapshot: newSnapshot };

    return newSnapshot;
  }, [data]);

  return {
    snapshot,
    history: historyRef.current,
    isLoading,
    error,
  };
}

export function useMetricsHistory() {
  const { history } = useMetricsSnapshot();
  return history;
}
