'use client';

import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import Link from 'next/link';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { JobDetailPanel } from '@/components/jobs/JobDetailPanel';
import { JobActions } from '@/components/jobs/JobActions';
import { useJob } from '@/hooks/useJobs';

export default function JobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.id as string;

  const { data: job, isLoading, error, refetch, isRefetching } = useJob(jobId);

  if (error) {
    return (
      <div className="flex flex-col">
        <Header title="Job Details" />
        <div className="p-6">
          <div className="text-center py-12">
            <p className="text-destructive mb-4">
              {error instanceof Error ? error.message : 'Failed to load job'}
            </p>
            <Button variant="outline" onClick={() => refetch()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <Header title="Job Details" />

      <div className="p-6 space-y-6">
        {/* Navigation and Actions */}
        <div className="flex items-center justify-between">
          <Button variant="ghost" asChild>
            <Link href="/jobs">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Jobs
            </Link>
          </Button>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isRefetching}
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${isRefetching ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            {job && <JobActions job={job} onDeleted={() => router.push('/jobs')} />}
          </div>
        </div>

        {/* Job Details */}
        {isLoading ? (
          <div className="space-y-6">
            <Skeleton className="h-64 w-full" />
            <div className="grid grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-24" />
              ))}
            </div>
            <Skeleton className="h-48 w-full" />
          </div>
        ) : job ? (
          <JobDetailPanel job={job} />
        ) : null}
      </div>
    </div>
  );
}
