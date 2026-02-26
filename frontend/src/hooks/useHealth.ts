'use client';

import { useQuery } from '@tanstack/react-query';
import * as healthApi from '@/lib/api/health';
import { HEALTH_POLL_INTERVAL } from '@/lib/constants';

export function useHealthStatus() {
  return useQuery({
    queryKey: ['health'],
    queryFn: healthApi.getHealthStatus,
    refetchInterval: HEALTH_POLL_INTERVAL,
    retry: 1,
  });
}
