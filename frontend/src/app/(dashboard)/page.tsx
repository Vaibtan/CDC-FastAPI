'use client';

import { Header } from '@/components/layout/Header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useMetricsSnapshot } from '@/hooks/useMetrics';
import { useHealthStatus } from '@/hooks/useHealth';
import { useJobs } from '@/hooks/useJobs';
import { OverviewCards } from '@/components/dashboard/OverviewCards';
import { RecentJobs } from '@/components/dashboard/RecentJobs';
import { HealthStatus } from '@/components/dashboard/HealthStatus';
import dynamic from 'next/dynamic';
import { formatNumber } from '@/lib/utils/formatters';
import { METRICS_POLL_INTERVAL, REDIS_STREAM_MAXLEN } from '@/lib/constants';

const ThroughputGauge = dynamic(
  () => import('@/components/metrics/ThroughputGauge').then((m) => m.ThroughputGauge),
  { ssr: false, loading: () => <Skeleton className="h-48" /> }
);

export default function DashboardPage() {
  const { snapshot, isLoading: metricsLoading } = useMetricsSnapshot(METRICS_POLL_INTERVAL);
  const { data: health, isLoading: healthLoading, isError: healthError, dataUpdatedAt } = useHealthStatus();
  const { data: jobsData, isLoading: jobsLoading } = useJobs(undefined, 1, 5);

  return (
    <div className="flex flex-col">
      <Header title="Dashboard" />

      <div className="p-6 space-y-6">
        {/* Stats Cards */}
        <OverviewCards
          snapshot={snapshot}
          totalJobsCreated={jobsData?.total}
          isLoading={metricsLoading}
        />

        {/* Throughput Gauges */}
        <div className="grid gap-4 md:grid-cols-2">
          {metricsLoading ? (
            <>
              <Skeleton className="h-48" />
              <Skeleton className="h-48" />
            </>
          ) : (
            <>
              <ThroughputGauge
                value={snapshot?.ingestRate || 0}
                label="Ingest Rate"
                maxValue={100}
              />
              <ThroughputGauge
                value={snapshot?.replayRate || 0}
                label="Replay Rate"
                maxValue={100}
              />
            </>
          )}
        </div>

        {/* Recent Activity & Health */}
        <div className="grid gap-4 md:grid-cols-2">
          <RecentJobs jobs={jobsData} isLoading={jobsLoading} />
          <HealthStatus
            health={health}
            isLoading={healthLoading}
            isError={healthError}
            dataUpdatedAt={dataUpdatedAt}
          />
        </div>

        {/* Redis Stream */}
        {!metricsLoading && snapshot && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Redis Stream Buffer</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-muted-foreground">Pending Events</span>
                    <span className="font-medium">{formatNumber(snapshot.redisStreamLength)}</span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{
                        width: `${Math.min((snapshot.redisStreamLength / REDIS_STREAM_MAXLEN) * 100, 100)}%`,
                      }}
                    />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
