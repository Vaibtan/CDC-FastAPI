// Auth
export const COOKIE_NAME = 'walstream-token';
export const LOCAL_STORAGE_KEY = 'walstream-auth';

// Limits
export const MAX_EVENTS = 1000;
export const REDIS_STREAM_MAXLEN = 100_000;

// Polling intervals (ms)
export const HEALTH_POLL_INTERVAL = 30_000;
export const METRICS_POLL_INTERVAL = 10_000;
export const JOBS_POLL_INTERVAL = 5_000;
export const STREAM_STATS_POLL_INTERVAL = 5_000;
export const JOBS_RUNNING_POLL_INTERVAL = 1_000;
