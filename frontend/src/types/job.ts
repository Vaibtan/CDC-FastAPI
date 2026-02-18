export type JobStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface ReplayJob {
  id: string;
  start_time: string;
  end_time: string;
  speed_factor: number;
  target_type?: string;
  target_url?: string;
  table_filter?: string;
  status: JobStatus;
  events_total: number;
  events_processed: number;
  events_failed: number;
  events_skipped_dedup: number;
  progress_percent: number;
  is_terminal: boolean;
  error_message?: string;
  error_count: number;
  created_at: string;
  updated_at: string;
  started_at?: string;
  paused_at?: string;
  finished_at?: string;
  completed_at?: string;
  replay_source?: 'redis' | 'kafka';
  created_by?: string;
  worker_id?: string;
}

export interface ReplayJobCreate {
  start_time: string;
  end_time: string;
  speed_factor?: number;
  target_type?: string;
  target_url?: string;
  table_filter?: string;
}

export interface ReplayJobUpdate {
  speed_factor?: number;
  status?: JobStatus;
}

export interface ReplayJobListResponse {
  items: ReplayJob[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export const JOB_STATUS_COLORS: Record<JobStatus, string> = {
  pending: 'bg-gray-500',
  queued: 'bg-blue-500',
  running: 'bg-green-500',
  paused: 'bg-yellow-500',
  completed: 'bg-emerald-500',
  failed: 'bg-red-500',
  cancelled: 'bg-gray-400',
};

export const TERMINAL_STATUSES: JobStatus[] = ['completed', 'failed', 'cancelled'];

export function isTerminalStatus(status: JobStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}
