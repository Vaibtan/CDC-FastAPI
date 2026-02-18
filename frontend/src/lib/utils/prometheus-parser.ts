export interface ParsedMetric {
  name: string;
  labels: Record<string, string>;
  value: number;
  help?: string;
  type?: string;
}

export interface MetricFamily {
  name: string;
  help: string;
  type: string;
  metrics: ParsedMetric[];
}

/**
 * Parse Prometheus text format into structured metrics
 */
export function parsePrometheusText(text: string): ParsedMetric[] {
  const lines = text.split('\n');
  const metrics: ParsedMetric[] = [];
  let currentHelp = '';
  let currentType = '';

  for (const line of lines) {
    const trimmed = line.trim();

    // Skip empty lines
    if (!trimmed) continue;

    // Parse HELP lines
    if (trimmed.startsWith('# HELP ')) {
      const match = trimmed.match(/^# HELP (\S+) (.+)$/);
      if (match) {
        currentHelp = match[2];
      }
      continue;
    }

    // Parse TYPE lines
    if (trimmed.startsWith('# TYPE ')) {
      const match = trimmed.match(/^# TYPE (\S+) (\S+)$/);
      if (match) {
        currentType = match[2];
      }
      continue;
    }

    // Skip other comment lines
    if (trimmed.startsWith('#')) continue;

    // Parse metric line
    const metricMatch = trimmed.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)?({[^}]*})?\s+([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?|NaN|[+-]?Inf)$/);
    if (metricMatch) {
      const [, name, labelsStr, valueStr] = metricMatch;

      // Parse labels
      const labels: Record<string, string> = {};
      if (labelsStr) {
        const labelMatches = Array.from(labelsStr.matchAll(/(\w+)="([^"]*)"/g));
        for (const match of labelMatches) {
          labels[match[1]] = match[2];
        }
      }

      // Parse value
      let value: number;
      if (valueStr === 'NaN') {
        value = NaN;
      } else if (valueStr === '+Inf' || valueStr === 'Inf') {
        value = Infinity;
      } else if (valueStr === '-Inf') {
        value = -Infinity;
      } else {
        value = parseFloat(valueStr);
      }

      metrics.push({
        name: name || '',
        labels,
        value,
        help: currentHelp,
        type: currentType,
      });
    }
  }

  return metrics;
}

/**
 * Group metrics by name into families
 */
export function groupMetricsByName(metrics: ParsedMetric[]): Map<string, MetricFamily> {
  const families = new Map<string, MetricFamily>();

  for (const metric of metrics) {
    // Get base name (remove _bucket, _count, _sum, _total suffixes for grouping)
    const baseName = metric.name
      .replace(/_bucket$/, '')
      .replace(/_count$/, '')
      .replace(/_sum$/, '')
      .replace(/_total$/, '');

    if (!families.has(baseName)) {
      families.set(baseName, {
        name: baseName,
        help: metric.help || '',
        type: metric.type || 'untyped',
        metrics: [],
      });
    }

    families.get(baseName)!.metrics.push(metric);
  }

  return families;
}

/**
 * Extract histogram percentiles from bucket metrics
 */
export function extractHistogramPercentiles(
  metrics: ParsedMetric[],
  metricName: string,
  percentiles: number[] = [0.5, 0.9, 0.99]
): Record<string, number> {
  const bucketMetrics = metrics
    .filter((m) => m.name === `${metricName}_bucket`)
    .sort((a, b) => {
      const leA = parseFloat(a.labels.le || '0');
      const leB = parseFloat(b.labels.le || '0');
      return leA - leB;
    });

  const countMetric = metrics.find((m) => m.name === `${metricName}_count`);
  const totalCount = countMetric?.value || 0;

  if (totalCount === 0 || bucketMetrics.length === 0) {
    return Object.fromEntries(percentiles.map((p) => [`p${p * 100}`, 0]));
  }

  const result: Record<string, number> = {};

  for (const percentile of percentiles) {
    const targetCount = totalCount * percentile;
    let previousBucket = { le: 0, count: 0 };

    for (const bucket of bucketMetrics) {
      const le = parseFloat(bucket.labels.le || '0');
      const count = bucket.value;

      if (count >= targetCount) {
        // Linear interpolation within the bucket
        const bucketCount = count - previousBucket.count;
        const bucketRange = le - previousBucket.le;
        const countInBucket = targetCount - previousBucket.count;

        if (bucketCount > 0 && isFinite(bucketRange)) {
          const fraction = countInBucket / bucketCount;
          result[`p${percentile * 100}`] = previousBucket.le + fraction * bucketRange;
        } else {
          result[`p${percentile * 100}`] = le;
        }
        break;
      }

      previousBucket = { le, count };
    }
  }

  return result;
}

/**
 * Get a single metric value by name and optional labels
 */
export function getMetricValue(
  metrics: ParsedMetric[],
  name: string,
  labels?: Record<string, string>
): number | null {
  const metric = metrics.find((m) => {
    if (m.name !== name) return false;
    if (!labels) return true;

    for (const [key, value] of Object.entries(labels)) {
      if (m.labels[key] !== value) return false;
    }
    return true;
  });

  return metric?.value ?? null;
}

/**
 * Get all metric values for a name grouped by a label
 */
export function getMetricsByLabel(
  metrics: ParsedMetric[],
  name: string,
  labelKey: string
): Record<string, number> {
  const result: Record<string, number> = {};

  for (const metric of metrics) {
    if (metric.name === name && metric.labels[labelKey]) {
      result[metric.labels[labelKey]] = metric.value;
    }
  }

  return result;
}

/**
 * Compute rate between two metric snapshots
 */
export function computeRate(
  currentValue: number,
  previousValue: number,
  intervalMs: number
): number {
  if (intervalMs <= 0) return 0;
  const delta = currentValue - previousValue;
  if (delta < 0) return 0; // Counter reset
  return (delta / intervalMs) * 1000; // Convert to per-second rate
}
