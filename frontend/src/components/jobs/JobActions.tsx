'use client';

import { useState } from 'react';
import { Play, Pause, Square, Trash2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import { useStartJob, usePauseJob, useResumeJob, useCancelJob, useDeleteJob } from '@/hooks/useJobs';
import type { ReplayJob } from '@/types/job';

interface JobActionsProps {
  job: ReplayJob;
  onDeleted?: () => void;
}

export function JobActions({ job, onDeleted }: JobActionsProps) {
  const { toast } = useToast();
  const [isDeleting, setIsDeleting] = useState(false);

  const startJob = useStartJob();
  const pauseJob = usePauseJob();
  const resumeJob = useResumeJob();
  const cancelJob = useCancelJob();
  const deleteJob = useDeleteJob();

  const handleStart = async () => {
    try {
      await startJob.mutateAsync(job.id);
      toast({ title: 'Job started successfully' });
    } catch (error) {
      toast({
        title: 'Failed to start job',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const handlePause = async () => {
    try {
      await pauseJob.mutateAsync(job.id);
      toast({ title: 'Job paused' });
    } catch (error) {
      toast({
        title: 'Failed to pause job',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const handleResume = async () => {
    try {
      await resumeJob.mutateAsync(job.id);
      toast({ title: 'Job resumed' });
    } catch (error) {
      toast({
        title: 'Failed to resume job',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const handleCancel = async () => {
    try {
      await cancelJob.mutateAsync(job.id);
      toast({ title: 'Job cancelled' });
    } catch (error) {
      toast({
        title: 'Failed to cancel job',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await deleteJob.mutateAsync(job.id);
      toast({ title: 'Job deleted' });
      onDeleted?.();
    } catch (error) {
      toast({
        title: 'Failed to delete job',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsDeleting(false);
    }
  };

  const isLoading =
    startJob.isPending ||
    pauseJob.isPending ||
    resumeJob.isPending ||
    cancelJob.isPending ||
    isDeleting;

  return (
    <div className="flex items-center gap-2">
      {/* Start Button - Only for pending jobs */}
      {job.status === 'pending' && (
        <Button onClick={handleStart} disabled={isLoading} size="sm">
          {startJob.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          Start
        </Button>
      )}

      {/* Pause Button - Only for running jobs */}
      {job.status === 'running' && (
        <Button onClick={handlePause} disabled={isLoading} variant="secondary" size="sm">
          {pauseJob.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Pause className="mr-2 h-4 w-4" />
          )}
          Pause
        </Button>
      )}

      {/* Resume Button - Only for paused jobs */}
      {job.status === 'paused' && (
        <Button onClick={handleResume} disabled={isLoading} size="sm">
          {resumeJob.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          Resume
        </Button>
      )}

      {/* Cancel Button - Only for non-terminal jobs */}
      {!job.is_terminal && (
        <Button onClick={handleCancel} disabled={isLoading} variant="outline" size="sm">
          {cancelJob.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Square className="mr-2 h-4 w-4" />
          )}
          Cancel
        </Button>
      )}

      {/* Delete Button - Only for terminal jobs */}
      {job.is_terminal && (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" size="sm" disabled={isLoading}>
              {isDeleting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-4 w-4" />
              )}
              Delete
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete Job</AlertDialogTitle>
              <AlertDialogDescription>
                Are you sure you want to delete this job? This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  );
}
