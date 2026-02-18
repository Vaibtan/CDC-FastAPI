'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface ReplayStatusChartProps {
  replayed: number;
  duplicate: number;
  failed: number;
  className?: string;
}

export function ReplayStatusChart({
  replayed,
  duplicate,
  failed,
  className,
}: ReplayStatusChartProps) {
  const total = replayed + duplicate + failed;

  // Create data for a simple display
  const data = [
    { name: 'Replayed', value: replayed, color: '#22c55e' },
    { name: 'Duplicates', value: duplicate, color: '#eab308' },
    { name: 'Failed', value: failed, color: '#ef4444' },
  ];

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Replay Status</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Stats row */}
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-green-500">
                {replayed.toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground">Replayed</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-yellow-500">
                {duplicate.toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground">Duplicates</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-red-500">
                {failed.toLocaleString()}
              </div>
              <div className="text-xs text-muted-foreground">Failed</div>
            </div>
          </div>

          {/* Progress bar */}
          {total > 0 && (
            <div className="flex h-4 rounded-full overflow-hidden bg-muted">
              {data.map((item) => {
                const percentage = (item.value / total) * 100;
                if (percentage === 0) return null;
                return (
                  <div
                    key={item.name}
                    className="transition-all duration-500"
                    style={{
                      width: `${percentage}%`,
                      backgroundColor: item.color,
                    }}
                    title={`${item.name}: ${item.value.toLocaleString()} (${percentage.toFixed(1)}%)`}
                  />
                );
              })}
            </div>
          )}

          {/* Legend */}
          <div className="flex justify-center gap-4 text-sm">
            {data.map((item) => (
              <div key={item.name} className="flex items-center gap-1">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-muted-foreground">{item.name}</span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
