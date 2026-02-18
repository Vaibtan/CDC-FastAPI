'use client';

import { useQuery } from '@tanstack/react-query';
import * as healthApi from '@/lib/api/health';

export function useHealthStatus() {
  return useQuery({
    queryKey: ['health'],
    queryFn: healthApi.getHealthStatus,
    refetchInterval: 30000, // Check every 30 seconds
    retry: 1,
  });
}
