'use client';

import Link from 'next/link';
import { Header } from '@/components/layout/Header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Activity, CheckCircle, Clock, AlertTriangle, ArrowRight, Zap, Database } from 'lucide-react';
import { useMetricsSnapshot } from '@/hooks/useMetrics';
import { useHealthStatus } from '@/hooks/useHealth';
import { useJobs } from '@/hooks/useJobs';
import { ThroughputGauge } from '@/components/metrics/ThroughputGauge';
import { cn } from '@/lib/utils';

export default function DashboardPage() {
  const { snapshot, isLoading: metricsLoading } = useMetricsSnapshot(10000);
  const { data: health, isLoading: healthLoading } = useHealthStatus();
  const { data: jobsData, isLoading: jobsLoading } = useJobs(undefined, 1, 5);

  const getHealthColor = (status?: string) => {
    if (!status) return 'text-gray-400';
    return status === 'healthy' ? 'text-green-500' : 'text-red-500';
  };

  return (
    <div className="flex flex-col">
      <Header title="Dashboard" />

      <div className="p-6 space-y-6">
        {/* Stats Cards */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Events Ingested</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {metricsLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <>
                  <div className="text-2xl font-bold">
                    {(snapshot?.eventsIngested || 0).toLocaleString()}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {snapshot?.ingestRate.toFixed(1)} events/sec
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Active Jobs</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {metricsLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <>
                  <div className="text-2xl font-bold">{snapshot?.activeJobs || 0}</div>
                  <p className="text-xs text-muted-foreground">
                    {snapshot?.totalJobsCreated || 0} total created
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Events Replayed</CardTitle>
              <CheckCircle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {metricsLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <>
                  <div className="text-2xl font-bold">
                    {(snapshot?.eventsReplayed || 0).toLocaleString()}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {(snapshot?.eventsDuplicate || 0).toLocaleString()} duplicates skipped
                  </p>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Failed Events</CardTitle>
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {metricsLoading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <>
                  <div className="text-2xl font-bold">{snapshot?.eventsFailed || 0}</div>
                  <p className="text-xs text-muted-foreground">
                    {snapshot?.eventsReplayed
                      ? ((snapshot.eventsFailed / snapshot.eventsReplayed) * 100).toFixed(3)
                      : '0.000'}
                    % failure rate
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        </div>

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
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Recent Jobs</CardTitle>
                <CardDescription>Latest replay job activity</CardDescription>
              </div>
              <Button variant="ghost" size="sm" asChild>
                <Link href="/jobs">
                  View all <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            </CardHeader>
            <CardContent>
              {jobsLoading ? (
                <div className="space-y-2">
                  {[...Array(3)].map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : jobsData?.items && jobsData.items.length > 0 ? (
                <div className="space-y-2">
                  {jobsData.items.slice(0, 5).map((job) => (
                    <Link
                      key={job.id}
                      href={`/jobs/${job.id}`}
                      className="flex items-center justify-between p-2 rounded-lg hover:bg-muted transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <div
                          className={cn(
                            'w-2 h-2 rounded-full',
                            job.status === 'running' && 'bg-green-500',
                            job.status === 'paused' && 'bg-yellow-500',
                            job.status === 'completed' && 'bg-blue-500',
                            job.status === 'failed' && 'bg-red-500',
                            job.status === 'pending' && 'bg-gray-500'
                          )}
                        />
                        <span className="text-sm font-mono">{job.id.slice(0, 8)}...</span>
                      </div>
                      <span className="text-xs text-muted-foreground capitalize">
                        {job.status}
                      </span>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground text-center py-4">
                  No jobs yet.{' '}
                  <Link href="/jobs/new" className="text-primary hover:underline">
                    Create one
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>System Health</CardTitle>
              <CardDescription>Component status overview</CardDescription>
            </CardHeader>
            <CardContent>
              {healthLoading ? (
                <div className="space-y-2">
                  {[...Array(3)].map((_, i) => (
                    <Skeleton key={i} className="h-8 w-full" />
                  ))}
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">PostgreSQL</span>
                    </div>
                    <span className={cn('text-sm font-medium', getHealthColor(health?.postgres))}>
                      {health?.postgres || 'Unknown'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Zap className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">Redis</span>
                    </div>
                    <span className={cn('text-sm font-medium', getHealthColor(health?.redis))}>
                      {health?.redis || 'Unknown'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Activity className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">Kafka</span>
                    </div>
                    <span className={cn('text-sm font-medium', getHealthColor(health?.kafka))}>
                      {health?.kafka || 'Unknown'}
                    </span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
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
                    <span className="font-medium">{snapshot.redisStreamLength.toLocaleString()}</span>
                  </div>
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{
                        width: `${Math.min((snapshot.redisStreamLength / 100000) * 100, 100)}%`,
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
