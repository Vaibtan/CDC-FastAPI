import { NextResponse } from 'next/server';
import { parsePrometheusText, type ParsedMetric } from '@/lib/utils/prometheus-parser';

interface MetricsResponse {
  timestamp: string;
  ingestor: ParsedMetric[];
  control: ParsedMetric[];
  replayer: ParsedMetric[];
  errors: string[];
}

async function fetchMetrics(url: string, name: string): Promise<{ metrics: ParsedMetric[]; error?: string }> {
  try {
    const response = await fetch(url, {
      cache: 'no-store',
      signal: AbortSignal.timeout(5000),
    });

    if (!response.ok) {
      return { metrics: [], error: `${name}: HTTP ${response.status}` };
    }

    const text = await response.text();
    const metrics = parsePrometheusText(text);
    return { metrics };
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return { metrics: [], error: `${name}: ${message}` };
  }
}

export async function GET() {
  const ingestorUrl = process.env.PROMETHEUS_INGESTOR_URL || 'http://localhost:9090/metrics';
  const controlUrl = process.env.PROMETHEUS_CONTROL_URL || 'http://localhost:9091/metrics';
  const replayerUrl = process.env.PROMETHEUS_REPLAYER_URL || 'http://localhost:9092/metrics';

  const [ingestorResult, controlResult, replayerResult] = await Promise.all([
    fetchMetrics(ingestorUrl, 'ingestor'),
    fetchMetrics(controlUrl, 'control'),
    fetchMetrics(replayerUrl, 'replayer'),
  ]);

  const errors: string[] = [];
  if (ingestorResult.error) errors.push(ingestorResult.error);
  if (controlResult.error) errors.push(controlResult.error);
  if (replayerResult.error) errors.push(replayerResult.error);

  const response: MetricsResponse = {
    timestamp: new Date().toISOString(),
    ingestor: ingestorResult.metrics,
    control: controlResult.metrics,
    replayer: replayerResult.metrics,
    errors,
  };

  return NextResponse.json(response);
}
