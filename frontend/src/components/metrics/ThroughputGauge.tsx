'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface ThroughputGaugeProps {
  value: number;
  label: string;
  maxValue?: number;
  unit?: string;
  className?: string;
}

export function ThroughputGauge({
  value,
  label,
  maxValue = 1000,
  unit = 'events/s',
  className,
}: ThroughputGaugeProps) {
  const percentage = Math.min((value / maxValue) * 100, 100);

  // Color based on percentage
  const getColor = () => {
    if (percentage < 33) return 'text-green-500';
    if (percentage < 66) return 'text-yellow-500';
    return 'text-red-500';
  };

  const getStrokeColor = () => {
    if (percentage < 33) return '#22c55e';
    if (percentage < 66) return '#eab308';
    return '#ef4444';
  };

  // SVG arc calculation
  const radius = 60;
  const circumference = Math.PI * radius;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center">
        <div className="relative">
          <svg width="140" height="80" viewBox="0 0 140 80">
            {/* Background arc */}
            <path
              d="M 10 70 A 60 60 0 0 1 130 70"
              fill="none"
              stroke="currentColor"
              strokeWidth="10"
              className="text-muted/30"
            />
            {/* Value arc */}
            <path
              d="M 10 70 A 60 60 0 0 1 130 70"
              fill="none"
              stroke={getStrokeColor()}
              strokeWidth="10"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              style={{ transition: 'stroke-dashoffset 0.5s ease' }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-end pb-1">
            <span className={cn('text-2xl font-bold', getColor())}>
              {value.toFixed(1)}
            </span>
          </div>
        </div>
        <span className="text-sm text-muted-foreground mt-1">{unit}</span>
      </CardContent>
    </Card>
  );
}
