'use client';

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect } from 'react';
import { useWebSocket, WebSocketStatus } from './useWebSocket';
import { useEventStore } from '@/stores/eventStore';
import * as eventsApi from '@/lib/api/events';
import type { CDCEvent, EventStreamMessage } from '@/types/event';
import { STREAM_STATS_POLL_INTERVAL } from '@/lib/constants';

export function useRecentEvents(count = 100) {
  return useQuery({
    queryKey: ['events', 'recent', count],
    queryFn: () => eventsApi.getRecentEvents(count),
  });
}

export function useStreamStats() {
  return useQuery({
    queryKey: ['events', 'stream', 'stats'],
    queryFn: eventsApi.getStreamStats,
    refetchInterval: STREAM_STATS_POLL_INTERVAL,
  });
}

interface UseEventStreamReturn {
  status: WebSocketStatus;
  events: CDCEvent[];
  filteredEvents: CDCEvent[];
  isPaused: boolean;
  reconnectAttempts: number;
  tables: string[];
  operations: string[];
  connect: () => void;
  disconnect: () => void;
  clearEvents: () => void;
  setPaused: (paused: boolean) => void;
  setFilters: (filters: { tables?: string[]; operations?: string[]; searchQuery?: string }) => void;
  resetFilters: () => void;
}

export function useEventStream(): UseEventStreamReturn {
  const {
    events,
    isPaused,
    addEvent,
    clearEvents,
    setFilters,
    resetFilters,
    setPaused,
    filteredEvents,
    uniqueTables,
    uniqueOperations,
  } = useEventStore();

  const handleMessage = useCallback(
    (data: unknown) => {
      // Backend sends EventStreamMessage with event_type (not type)
      const message = data as EventStreamMessage;

      if (message.event_type === 'change_event' && message.payload) {
        // payload contains {id, event} matching CDCEvent shape
        addEvent(message.payload as CDCEvent);
      }
      // heartbeat and job_update messages are ignored for the event stream
    },
    [addEvent]
  );

  const { status, connect, disconnect, reconnectAttempts } = useWebSocket({
    url: eventsApi.getWebSocketUrl(),
    onMessage: handleMessage,
    reconnect: true,
  });

  // Load initial events when connected
  useEffect(() => {
    if (status === 'connected') {
      // Backend returns a flat list of CDCEvent, not {events: [...]}
      eventsApi.getRecentEvents(100).then((events) => {
        events.forEach((event) => addEvent(event));
      }).catch(console.error);
    }
  }, [status, addEvent]);

  return {
    status,
    events,
    filteredEvents: filteredEvents(),
    isPaused,
    reconnectAttempts,
    tables: uniqueTables(),
    operations: uniqueOperations(),
    connect,
    disconnect,
    clearEvents,
    setPaused,
    setFilters,
    resetFilters,
  };
}
