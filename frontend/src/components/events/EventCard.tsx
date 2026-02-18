'use client';

import { format } from 'date-fns';
import { Plus, Edit2, Trash2, Database, AlertCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { CDCEvent, CDCOperation } from '@/types/event';

interface EventCardProps {
  event: CDCEvent;
  onClick?: () => void;
  className?: string;
}

const operationConfig: Record<CDCOperation, { icon: React.ElementType; color: string; bgColor: string }> = {
  INSERT: {
    icon: Plus,
    color: 'text-green-500',
    bgColor: 'bg-green-500/10 hover:bg-green-500/20',
  },
  UPDATE: {
    icon: Edit2,
    color: 'text-blue-500',
    bgColor: 'bg-blue-500/10 hover:bg-blue-500/20',
  },
  DELETE: {
    icon: Trash2,
    color: 'text-red-500',
    bgColor: 'bg-red-500/10 hover:bg-red-500/20',
  },
  TRUNCATE: {
    icon: AlertCircle,
    color: 'text-yellow-500',
    bgColor: 'bg-yellow-500/10 hover:bg-yellow-500/20',
  },
};

export function EventCard({ event, onClick, className }: EventCardProps) {
  const operation = (event.event?.operation ?? event.operation ?? 'INSERT') as CDCOperation;
  const table = event.event?.table ?? event.table ?? 'unknown';
  const config = operationConfig[operation];
  const Icon = config.icon;

  // Derive a timestamp from commit_time (ms since epoch) if available
  const timestamp = event.event?.commit_time
    ? new Date(event.event.commit_time)
    : null;

  // Show first value from new data as a preview key
  const newData = event.event?.new ?? {};
  const firstKey = Object.keys(newData)[0];
  const pkPreview = firstKey ? `${firstKey}: ${newData[firstKey]}` : event.id;

  return (
    <div
      onClick={onClick}
      className={cn(
        'p-3 rounded-lg border cursor-pointer transition-colors',
        config.bgColor,
        className
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={cn('p-2 rounded-md bg-background', config.color)}>
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium">{table}</span>
              <Badge variant="outline" className="text-xs">
                {operation}
              </Badge>
            </div>
            <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground">
              <Database className="h-3 w-3" />
              <span className="font-mono">{String(pkPreview).slice(0, 30)}</span>
            </div>
          </div>
        </div>
        {timestamp && (
          <div className="text-right text-sm text-muted-foreground">
            <div>{format(timestamp, 'HH:mm:ss')}</div>
            <div className="text-xs">{format(timestamp, 'MMM d')}</div>
          </div>
        )}
      </div>

      {/* Preview of changed data */}
      {Object.keys(newData).length > 0 && (
        <div className="mt-2 pt-2 border-t border-border/50">
          <div className="text-xs text-muted-foreground font-mono truncate">
            {JSON.stringify(newData).slice(0, 100)}...
          </div>
        </div>
      )}
    </div>
  );
}
