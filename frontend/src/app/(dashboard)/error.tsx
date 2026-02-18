'use client';

import { useEffect } from 'react';
import { ErrorFallback } from '@/components/errors/ErrorFallback';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Dashboard error:', error);
  }, [error]);

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <ErrorFallback
        error={error}
        reset={reset}
        title="Dashboard Error"
        showHomeButton={true}
      />
    </div>
  );
}
