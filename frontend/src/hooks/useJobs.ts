import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as jobsApi from '@/lib/api/jobs';
import type { ReplayJob, ReplayJobCreate, JobStatus } from '@/types/job';

export function useJobs(status?: JobStatus, page = 1, pageSize = 20) {
  return useQuery({
    queryKey: ['jobs', { status, page, pageSize }],
    queryFn: () => jobsApi.listJobs({ status, page, page_size: pageSize }),
    refetchInterval: 5000, // Poll every 5s for status updates
  });
}

export function useJob(jobId: string) {
  return useQuery({
    queryKey: ['jobs', jobId],
    queryFn: () => jobsApi.getJob(jobId),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data as ReplayJob | undefined;
      // Faster polling for running jobs
      return data?.status === 'running' ? 1000 : 5000;
    },
  });
}

export function useCreateJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ReplayJobCreate) => jobsApi.createJob(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useDeleteJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => jobsApi.deleteJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useStartJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => jobsApi.startJob(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      queryClient.invalidateQueries({ queryKey: ['jobs', jobId] });
    },
  });
}

export function usePauseJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => jobsApi.pauseJob(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      queryClient.invalidateQueries({ queryKey: ['jobs', jobId] });
    },
  });
}

export function useResumeJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => jobsApi.resumeJob(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      queryClient.invalidateQueries({ queryKey: ['jobs', jobId] });
    },
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => jobsApi.cancelJob(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      queryClient.invalidateQueries({ queryKey: ['jobs', jobId] });
    },
  });
}
