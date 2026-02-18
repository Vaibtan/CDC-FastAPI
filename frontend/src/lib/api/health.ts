import { apiClient } from './client';

export interface HealthStatus {
  status: string;
  version: string;
  components: Record<string, string>;
  // Flat keys for convenience (also present at top level)
  postgres: string;
  redis: string;
  kafka: string;
}

export async function getHealthStatus(): Promise<HealthStatus> {
  const response = await apiClient.get('/health');
  return response.data;
}

export async function getLivenessStatus(): Promise<{ status: string }> {
  const response = await apiClient.get('/health/live');
  return response.data;
}

export async function getReadinessStatus(): Promise<{ status: string }> {
  const response = await apiClient.get('/health/ready');
  return response.data;
}
