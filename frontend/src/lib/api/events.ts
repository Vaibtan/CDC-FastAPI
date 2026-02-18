import { apiClient } from './client';
import type { CDCEvent, StreamStats } from '@/types/event';

/**
 * Fetch recent events from the backend.
 * Backend returns a flat list (not wrapped in {events: [...]}).
 * Backend uses `count` param, not `limit`.
 */
export async function getRecentEvents(count = 100): Promise<CDCEvent[]> {
  const response = await apiClient.get<CDCEvent[]>('/events/recent', {
    params: { count },
  });
  return response.data;
}

export async function getStreamStats(): Promise<StreamStats> {
  const response = await apiClient.get<StreamStats>('/events/stream/stats');
  return response.data;
}

export function getWebSocketUrl(): string {
  const baseUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';
  return `${baseUrl}/api/v1/events/ws`;
}
