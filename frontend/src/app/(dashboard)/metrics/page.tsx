'use client';

import { AlertTriangle } from 'lucide-react';
import dynamic from 'next/dynamic';
import { Header } from '@/components/layout/Header';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { StatsCard } from '@/components/metrics/StatsCard';
import { useMetricsSnapshot } from '@/hooks/useMetrics';
import { useJobs } from '@/hooks/useJobs';
import { Activity, Database, Zap } from 'lucide-react';
import { METRICS_POLL_INTERVAL } from '@/lib/constants';

const ThroughputGauge = dynamic(
  () => import('@/components/metrics/ThroughputGauge').then((m) => m.ThroughputGauge),
  { ssr: false, loading: () => <Skeleton className="h-48" /> }
);
const EventsLineChart = dynamic(
  () => import('@/components/metrics/EventsLineChart').then((m) => m.EventsLineChart),
  { ssr: false, loading: () => <Skeleton className="h-80" /> }
);
const OperationsBarChart = dynamic(
  () => import('@/components/metrics/OperationsBarChart').then((m) => m.OperationsBarChart),
  { ssr: false, loading: () => <Skeleton className="h-80" /> }
);
const ReplayStatusChart = dynamic(
  () => import('@/components/metrics/ReplayStatusChart').then((m) => m.ReplayStatusChart),
  { ssr: false, loading: () => <Skeleton className="h-80" /> }
);
const LatencyChart = dynamic(
  () => import('@/components/metrics/LatencyChart').then((m) => m.LatencyChart),
  { ssr: false, loading: () => <Skeleton className="h-64" /> }
);
const RedisStreamCard = dynamic(
  () => import('@/components/metrics/RedisStreamCard').then((m) => m.RedisStreamCard),
  { ssr: false, loading: () => <Skeleton className="h-80" /> }
);

export default function MetricsPage() {
  const { snapshot, history, isLoading, error } = useMetricsSnapshot(METRICS_POLL_INTERVAL);
  const { data: jobsData } = useJobs(undefined, 1, 1);

  if (error) {
    return (
      <div className="flex flex-col">
        <Header title="Metrics" />
        <div className="p-6">
          <Card className="border-destructive">
            <CardContent className="p-6">
              <div className="flex items-center gap-2 text-destructive">
                <AlertTriangle className="h-5 w-5" />
                <span>Failed to load metrics: {error instanceof Error ? error.message : 'Unknown error'}</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <Header title="Metrics Dashboard" />

      <div className="p-6 space-y-6">
        {/* Error alerts */}
        {snapshot?.errors && snapshot.errors.length > 0 && (
          <Card className="border-yellow-500 bg-yellow-500/10">
            <CardContent className="p-4">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-5 w-5 text-yellow-500 mt-0.5" />
                <div>
                  <div className="font-medium text-yellow-500">Some metrics unavailable</div>
                  <ul className="text-sm text-muted-foreground mt-1">
                    {snapshot.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Top Stats Row */}
        {isLoading ? (
          <div className="grid grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        ) : snapshot ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatsCard
              title="Events Ingested"
              value={snapshot.eventsIngested}
              icon={Activity}
            />
            <StatsCard
              title="Events Replayed"
              value={snapshot.eventsReplayed}
              icon={Zap}
            />
            <StatsCard
              title="Active Jobs"
              value={snapshot.activeJobs}
              icon={Database}
            />
            <StatsCard
              title="Total Jobs Created"
              value={jobsData?.total ?? snapshot.totalJobsCreated}
            />
          </div>
        ) : null}

        {/* Throughput Gauges */}
        {isLoading ? (
          <div className="grid grid-cols-2 gap-4">
            {[...Array(2)].map((_, i) => (
              <Skeleton key={i} className="h-48" />
            ))}
          </div>
        ) : snapshot ? (
          <div className="grid grid-cols-2 gap-4">
            <ThroughputGauge
              value={snapshot.ingestRate}
              label="Ingest Rate"
              maxValue={100}
            />
            <ThroughputGauge
              value={snapshot.replayRate}
              label="Replay Rate"
              maxValue={100}
            />
          </div>
        ) : null}

        {/* Charts Grid */}
        {isLoading ? (
          <div className="grid grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-80" />
            ))}
          </div>
        ) : snapshot ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Events over time */}
            <EventsLineChart data={history} />

            {/* Operations breakdown */}
            <OperationsBarChart data={snapshot.eventsIngestedByOperation} />

            {/* Replay status */}
            <ReplayStatusChart
              replayed={snapshot.eventsReplayed}
              duplicate={snapshot.eventsDuplicate}
              failed={snapshot.eventsFailed}
            />

            {/* Redis stream */}
            <RedisStreamCard length={snapshot.redisStreamLength} />
          </div>
        ) : null}

        {/* Latency Charts */}
        {isLoading ? (
          <div className="grid grid-cols-2 gap-4">
            {[...Array(2)].map((_, i) => (
              <Skeleton key={i} className="h-64" />
            ))}
          </div>
        ) : snapshot ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <LatencyChart
              title="Ingestor Latency"
              p50={snapshot.ingestorLatencyP50}
              p90={snapshot.ingestorLatencyP90}
              p99={snapshot.ingestorLatencyP99}
            />
            <LatencyChart
              title="Replayer Latency"
              p50={snapshot.replayerLatencyP50}
              p90={snapshot.replayerLatencyP90}
              p99={snapshot.replayerLatencyP99}
            />
          </div>
        ) : null}

        {/* Last updated */}
        {snapshot && (
          <div className="text-xs text-muted-foreground text-right">
            Last updated: {new Date(snapshot.timestamp).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
}
