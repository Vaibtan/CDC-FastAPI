import apiClient from './client';
import type {
  ReplayJob,
  ReplayJobCreate,
  ReplayJobUpdate,
  ReplayJobListResponse,
  JobStatus,
} from '@/types/job';

export interface ListJobsParams {
  status?: JobStatus;
  page?: number;
  page_size?: number;
}

export async function listJobs(params: ListJobsParams = {}): Promise<ReplayJobListResponse> {
  const response = await apiClient.get<ReplayJobListResponse>('/jobs', { params });
  return response.data;
}

export async function getJob(jobId: string): Promise<ReplayJob> {
  const response = await apiClient.get<ReplayJob>(`/jobs/${jobId}`);
  return response.data;
}

export async function createJob(data: ReplayJobCreate): Promise<ReplayJob> {
  const response = await apiClient.post<ReplayJob>('/jobs', data);
  return response.data;
}

export async function updateJob(jobId: string, data: ReplayJobUpdate): Promise<ReplayJob> {
  const response = await apiClient.patch<ReplayJob>(`/jobs/${jobId}`, data);
  return response.data;
}

export async function deleteJob(jobId: string): Promise<void> {
  await apiClient.delete(`/jobs/${jobId}`);
}

export async function startJob(jobId: string): Promise<ReplayJob> {
  const response = await apiClient.post<ReplayJob>(`/jobs/${jobId}/start`);
  return response.data;
}

export async function pauseJob(jobId: string): Promise<ReplayJob> {
  const response = await apiClient.post<ReplayJob>(`/jobs/${jobId}/pause`);
  return response.data;
}

export async function resumeJob(jobId: string): Promise<ReplayJob> {
  const response = await apiClient.post<ReplayJob>(`/jobs/${jobId}/resume`);
  return response.data;
}

export async function cancelJob(jobId: string): Promise<ReplayJob> {
  const response = await apiClient.post<ReplayJob>(`/jobs/${jobId}/cancel`);
  return response.data;
}
