'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface LatencyChartProps {
  p50: number;
  p90: number;
  p99: number;
  title: string;
  className?: string;
}

const colors = {
  p50: '#22c55e',
  p90: '#eab308',
  p99: '#ef4444',
};

export function LatencyChart({ p50, p90, p99, title, className }: LatencyChartProps) {
  const data = [
    { name: 'p50', value: p50 * 1000, color: colors.p50 },
    { name: 'p90', value: p90 * 1000, color: colors.p90 },
    { name: 'p99', value: p99 * 1000, color: colors.p99 },
  ];

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} className="text-muted-foreground" />
              <YAxis
                tick={{ fontSize: 12 }}
                className="text-muted-foreground"
                tickFormatter={(value) => `${value.toFixed(0)}ms`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--background))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px',
                }}
                formatter={(value) => [`${Number(value).toFixed(2)}ms`, 'Latency']}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="flex justify-center gap-6 mt-2 text-sm">
          {data.map((item) => (
            <div key={item.name} className="text-center">
              <div className="font-medium" style={{ color: item.color }}>
                {item.value.toFixed(2)}ms
              </div>
              <div className="text-xs text-muted-foreground">{item.name}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
