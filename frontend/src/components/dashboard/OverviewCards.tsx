'use client';

import { Activity, CheckCircle, Clock, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatNumber, formatRate, formatPercent } from '@/lib/utils/formatters';

interface MetricsSnapshot {
  eventsIngested: number;
  activeJobs: number;
  totalJobsCreated: number;
  eventsReplayed: number;
  eventsDuplicate: number;
  eventsFailed: number;
  ingestRate: number;
}

interface OverviewCardsProps {
  snapshot: MetricsSnapshot | null;
  totalJobsCreated?: number;
  isLoading: boolean;
}

export function OverviewCards({ snapshot, totalJobsCreated, isLoading }: OverviewCardsProps) {
  const totalJobs = totalJobsCreated ?? snapshot?.totalJobsCreated ?? 0;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Events Ingested</CardTitle>
          <Activity className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-8 w-24" />
          ) : (
            <>
              <div className="text-2xl font-bold">
                {formatNumber(snapshot?.eventsIngested || 0)}
              </div>
              <p className="text-xs text-muted-foreground">
                {formatRate(snapshot?.ingestRate || 0)}
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
          {isLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <>
              <div className="text-2xl font-bold">{snapshot?.activeJobs || 0}</div>
              <p className="text-xs text-muted-foreground">
                {totalJobs} total created
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
          {isLoading ? (
            <Skeleton className="h-8 w-24" />
          ) : (
            <>
              <div className="text-2xl font-bold">
                {formatNumber(snapshot?.eventsReplayed || 0)}
              </div>
              <p className="text-xs text-muted-foreground">
                {formatNumber(snapshot?.eventsDuplicate || 0)} duplicates skipped
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
          {isLoading ? (
            <Skeleton className="h-8 w-16" />
          ) : (
            <>
              <div className="text-2xl font-bold">{snapshot?.eventsFailed || 0}</div>
              <p className="text-xs text-muted-foreground">
                {formatPercent(
                  snapshot && snapshot.eventsReplayed + snapshot.eventsFailed > 0
                    ? (snapshot.eventsFailed / (snapshot.eventsReplayed + snapshot.eventsFailed)) * 100
                    : 0,
                  3
                )}{' '}
                failure rate
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
