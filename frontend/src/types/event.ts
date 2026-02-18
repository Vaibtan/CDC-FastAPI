export type CDCOperation = 'INSERT' | 'UPDATE' | 'DELETE' | 'TRUNCATE';

/**
 * Matches backend ChangeRecordModel fields exactly.
 * Backend wraps this in {"id": "<stream_id>", "event": <ChangeRecordModel>}.
 */
export interface ChangeRecordEvent {
  lsn: string;
  commit_time: number;
  table: string;
  operation: CDCOperation;
  old: Record<string, string>;
  new: Record<string, string>;
}

/**
 * A single entry from GET /events/recent or WebSocket payload.
 * Contains the Redis stream ID and the parsed event.
 */
export interface CDCEvent {
  id: string;
  event?: ChangeRecordEvent;
  // Fallback fields when protobuf parsing fails on backend
  table?: string;
  operation?: string;
  parse_error?: string;
}

/**
 * WebSocket message from backend EventStreamMessage model.
 * Backend sends event_type (not type).
 */
export interface EventStreamMessage {
  event_type: 'change_event' | 'heartbeat' | 'job_update';
  payload: CDCEvent | { timestamp: string };
  timestamp?: string;
}

export interface StreamStats {
  stream: string;
  length: number;
  first_entry: unknown;
  last_entry: unknown;
  consumer_groups: Array<{
    name: string;
    consumers: number;
    pending: number;
    last_delivered_id: string;
  }>;
  error?: string;
}

export const OPERATION_COLORS: Record<CDCOperation, string> = {
  INSERT: 'bg-green-500',
  UPDATE: 'bg-blue-500',
  DELETE: 'bg-red-500',
  TRUNCATE: 'bg-yellow-500',
};
