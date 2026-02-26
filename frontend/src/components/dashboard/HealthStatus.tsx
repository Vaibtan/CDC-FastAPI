'use client';

import { Database, Zap, Activity, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { HealthStatus as HealthStatusType } from '@/lib/api/health';

interface HealthStatusProps {
  health: HealthStatusType | undefined;
  isLoading: boolean;
  isError: boolean;
  dataUpdatedAt: number;
}

const STALE_THRESHOLD_MS = 60_000;

function getHealthColor(status?: string) {
  if (!status) return 'text-gray-400';
  return status === 'healthy' ? 'text-green-500' : 'text-red-500';
}

function HealthRow({
  icon: Icon,
  label,
  status,
}: {
  icon: React.ElementType;
  label: string;
  status?: string;
}) {
  const isUnhealthy = status && status !== 'healthy';

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        {isUnhealthy && (
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500" />
          </span>
        )}
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm">{label}</span>
      </div>
      <span className={cn('text-sm font-medium', getHealthColor(status))}>
        {status || 'Unknown'}
      </span>
    </div>
  );
}

export function HealthStatus({ health, isLoading, isError, dataUpdatedAt }: HealthStatusProps) {
  const isStale = dataUpdatedAt > 0 && Date.now() - dataUpdatedAt > STALE_THRESHOLD_MS;

  // Network error / 503 state
  if (isError) {
    return (
      <Card className="border-amber-500">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            System Health
          </CardTitle>
          <CardDescription>Unable to reach health endpoint</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
            <AlertTriangle className="h-4 w-4" />
            Health check unavailable. The backend may be down or unreachable.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>System Health</CardTitle>
            <CardDescription>Component status overview</CardDescription>
          </div>
          {isStale && (
            <Badge variant="outline" className="text-amber-600 border-amber-500">
              Stale
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            <HealthRow icon={Database} label="PostgreSQL" status={health?.postgres} />
            <HealthRow icon={Zap} label="Redis" status={health?.redis} />
            <HealthRow icon={Activity} label="Kafka" status={health?.kafka} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
