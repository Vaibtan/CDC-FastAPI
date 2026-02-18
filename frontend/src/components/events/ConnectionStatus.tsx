'use client';

import { Wifi, WifiOff, Loader2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WebSocketStatus } from '@/hooks/useWebSocket';

interface ConnectionStatusProps {
  status: WebSocketStatus;
  reconnectAttempts?: number;
  className?: string;
}

const statusConfig: Record<WebSocketStatus, { icon: React.ElementType; label: string; className: string }> = {
  connected: {
    icon: Wifi,
    label: 'Connected',
    className: 'text-green-500 bg-green-500/10',
  },
  connecting: {
    icon: Loader2,
    label: 'Connecting...',
    className: 'text-yellow-500 bg-yellow-500/10',
  },
  disconnected: {
    icon: WifiOff,
    label: 'Disconnected',
    className: 'text-gray-500 bg-gray-500/10',
  },
  error: {
    icon: AlertCircle,
    label: 'Error',
    className: 'text-red-500 bg-red-500/10',
  },
};

export function ConnectionStatus({ status, reconnectAttempts = 0, className }: ConnectionStatusProps) {
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <div
      className={cn(
        'inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium',
        config.className,
        className
      )}
    >
      <Icon className={cn('h-4 w-4', status === 'connecting' && 'animate-spin')} />
      <span>{config.label}</span>
      {status === 'disconnected' && reconnectAttempts > 0 && (
        <span className="text-xs opacity-70">
          (retry {reconnectAttempts})
        </span>
      )}
    </div>
  );
}
