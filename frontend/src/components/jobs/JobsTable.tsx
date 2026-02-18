'use client';

import { useRouter } from 'next/navigation';
import { format } from 'date-fns';
import { MoreHorizontal, Play, Pause, Square, Trash2 } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { JobStatusBadge } from './JobStatusBadge';
import { useStartJob, usePauseJob, useResumeJob, useCancelJob, useDeleteJob } from '@/hooks/useJobs';
import { useToast } from '@/hooks/use-toast';
import type { ReplayJob } from '@/types/job';

interface JobsTableProps {
  jobs: ReplayJob[];
  isLoading: boolean;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function JobsTable({
  jobs,
  isLoading,
  page,
  totalPages,
  onPageChange,
}: JobsTableProps) {
  const router = useRouter();
  const { toast } = useToast();

  const startJob = useStartJob();
  const pauseJob = usePauseJob();
  const resumeJob = useResumeJob();
  const cancelJob = useCancelJob();
  const deleteJob = useDeleteJob();

  const handleAction = async (
    action: 'start' | 'pause' | 'resume' | 'cancel' | 'delete',
    jobId: string
  ) => {
    try {
      switch (action) {
        case 'start':
          await startJob.mutateAsync(jobId);
          toast({ title: 'Job started' });
          break;
        case 'pause':
          await pauseJob.mutateAsync(jobId);
          toast({ title: 'Job paused' });
          break;
        case 'resume':
          await resumeJob.mutateAsync(jobId);
          toast({ title: 'Job resumed' });
          break;
        case 'cancel':
          await cancelJob.mutateAsync(jobId);
          toast({ title: 'Job cancelled' });
          break;
        case 'delete':
          await deleteJob.mutateAsync(jobId);
          toast({ title: 'Job deleted' });
          break;
      }
    } catch (error) {
      toast({
        title: 'Action failed',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No jobs found. Create your first replay job to get started.
      </div>
    );
  }

  return (
    <div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Time Range</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Progress</TableHead>
            <TableHead>Speed</TableHead>
            <TableHead>Created</TableHead>
            <TableHead className="w-12"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((job) => (
            <TableRow
              key={job.id}
              className="cursor-pointer"
              onClick={() => router.push(`/jobs/${job.id}`)}
            >
              <TableCell>
                <div className="text-sm">
                  {format(new Date(job.start_time), 'MMM d, HH:mm')} -{' '}
                  {format(new Date(job.end_time), 'MMM d, HH:mm')}
                </div>
                <div className="text-xs text-muted-foreground font-mono">
                  {job.id.slice(0, 8)}...
                </div>
              </TableCell>
              <TableCell>
                <JobStatusBadge status={job.status} />
              </TableCell>
              <TableCell>
                <div className="w-32 space-y-1">
                  <Progress value={job.progress_percent} className="h-2" />
                  <div className="text-xs text-muted-foreground">
                    {job.events_processed.toLocaleString()} / {job.events_total.toLocaleString()}
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <span className="font-mono">{job.speed_factor}x</span>
              </TableCell>
              <TableCell>
                <div className="text-sm">
                  {format(new Date(job.created_at), 'MMM d, HH:mm')}
                </div>
                {job.created_by && (
                  <div className="text-xs text-muted-foreground">{job.created_by}</div>
                )}
              </TableCell>
              <TableCell onClick={(e) => e.stopPropagation()}>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {job.status === 'pending' && (
                      <DropdownMenuItem onClick={() => handleAction('start', job.id)}>
                        <Play className="mr-2 h-4 w-4" />
                        Start
                      </DropdownMenuItem>
                    )}
                    {job.status === 'running' && (
                      <DropdownMenuItem onClick={() => handleAction('pause', job.id)}>
                        <Pause className="mr-2 h-4 w-4" />
                        Pause
                      </DropdownMenuItem>
                    )}
                    {job.status === 'paused' && (
                      <DropdownMenuItem onClick={() => handleAction('resume', job.id)}>
                        <Play className="mr-2 h-4 w-4" />
                        Resume
                      </DropdownMenuItem>
                    )}
                    {!job.is_terminal && (
                      <DropdownMenuItem onClick={() => handleAction('cancel', job.id)}>
                        <Square className="mr-2 h-4 w-4" />
                        Cancel
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => handleAction('delete', job.id)}
                      className="text-destructive"
                      disabled={!job.is_terminal}
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-end space-x-2 py-4">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
