import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { JobStatus } from '@/types/job';

const statusConfig: Record<JobStatus, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline'; className: string }> = {
  pending: {
    label: 'Pending',
    variant: 'secondary',
    className: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  },
  queued: {
    label: 'Queued',
    variant: 'secondary',
    className: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  },
  running: {
    label: 'Running',
    variant: 'default',
    className: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  },
  paused: {
    label: 'Paused',
    variant: 'secondary',
    className: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
  },
  completed: {
    label: 'Completed',
    variant: 'default',
    className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300',
  },
  failed: {
    label: 'Failed',
    variant: 'destructive',
    className: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
  },
  cancelled: {
    label: 'Cancelled',
    variant: 'outline',
    className: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
  },
};

interface JobStatusBadgeProps {
  status: JobStatus;
  className?: string;
}

export function JobStatusBadge({ status, className }: JobStatusBadgeProps) {
  const config = statusConfig[status];

  return (
    <Badge
      variant={config.variant}
      className={cn(config.className, className)}
    >
      {config.label}
    </Badge>
  );
}
