/** Locale-formatted number with commas. */
export function formatNumber(n: number): string {
  return n.toLocaleString();
}

/** Fixed-point rate with "events/sec" suffix. */
export function formatRate(n: number): string {
  return `${n.toFixed(1)} events/sec`;
}

/** Percentage formatting. */
export function formatPercent(n: number, decimals = 2): string {
  return `${n.toFixed(decimals)}%`;
}

/** Human-readable duration from milliseconds. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return `${h}h ${m}m`;
}

/** Relative time string like "2m ago", "1h ago". */
export function formatRelativeTime(date: string | number | Date): string {
  const now = Date.now();
  const then = new Date(date).getTime();
  const diffMs = now - then;

  if (diffMs < 0) return 'just now';
  if (diffMs < 60_000) return `${Math.floor(diffMs / 1000)}s ago`;
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)}m ago`;
  if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)}h ago`;
  return `${Math.floor(diffMs / 86_400_000)}d ago`;
}
