'use client';

import { useMemo } from 'react';
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

interface OperationsBarChartProps {
  data: Record<string, number>;
  className?: string;
}

const operationColors: Record<string, string> = {
  INSERT: '#22c55e',
  UPDATE: '#3b82f6',
  DELETE: '#ef4444',
};

export function OperationsBarChart({ data, className }: OperationsBarChartProps) {
  const chartData = useMemo(() => {
    return Object.entries(data).map(([operation, count]) => ({
      operation,
      count,
      color: operationColors[operation] || '#6b7280',
    }));
  }, [data]);

  if (chartData.length === 0) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Events by Operation</CardTitle>
        </CardHeader>
        <CardContent className="h-64 flex items-center justify-center text-muted-foreground">
          No data available
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Events by Operation</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis type="number" tick={{ fontSize: 12 }} className="text-muted-foreground" />
              <YAxis
                dataKey="operation"
                type="category"
                tick={{ fontSize: 12 }}
                className="text-muted-foreground"
                width={80}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--background))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px',
                }}
                formatter={(value) => [Number(value).toLocaleString(), 'Count']}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
