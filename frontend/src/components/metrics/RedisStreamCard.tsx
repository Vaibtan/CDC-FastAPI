'use client';

import { Database } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

interface RedisStreamCardProps {
  length: number;
  maxLength?: number;
  className?: string;
}

export function RedisStreamCard({ length, maxLength = 100000, className }: RedisStreamCardProps) {
  const percentage = Math.min((length / maxLength) * 100, 100);

  const getStatusColor = () => {
    if (percentage < 50) return 'text-green-500';
    if (percentage < 80) return 'text-yellow-500';
    return 'text-red-500';
  };

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Database className="h-4 w-4" />
          Redis Stream
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end justify-between">
          <div>
            <div className={`text-3xl font-bold ${getStatusColor()}`}>
              {length.toLocaleString()}
            </div>
            <div className="text-sm text-muted-foreground">pending events</div>
          </div>
          <div className="text-right text-sm text-muted-foreground">
            <div>Max: {maxLength.toLocaleString()}</div>
            <div>{percentage.toFixed(1)}% used</div>
          </div>
        </div>

        <Progress value={percentage} className="h-2" />

        <div className="flex justify-between text-xs text-muted-foreground">
          <span>0</span>
          <span>{(maxLength / 2).toLocaleString()}</span>
          <span>{maxLength.toLocaleString()}</span>
        </div>
      </CardContent>
    </Card>
  );
}
