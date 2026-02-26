'use client';

import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { ReplayJobListResponse } from '@/types/job';

interface RecentJobsProps {
  jobs: ReplayJobListResponse | undefined;
  isLoading: boolean;
}

export function RecentJobs({ jobs, isLoading }: RecentJobsProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Recent Jobs</CardTitle>
          <CardDescription>Latest replay job activity</CardDescription>
        </div>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/jobs">
            View all <ArrowRight className="ml-2 h-4 w-4" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : jobs?.items && jobs.items.length > 0 ? (
          <div className="space-y-2">
            {jobs.items.slice(0, 5).map((job) => (
              <Link
                key={job.id}
                href={`/jobs/${job.id}`}
                className="flex items-center justify-between p-2 rounded-lg hover:bg-muted transition-colors"
              >
                <div className="flex items-center gap-2">
                  <div
                    className={cn(
                      'w-2 h-2 rounded-full',
                      job.status === 'running' && 'bg-green-500',
                      job.status === 'paused' && 'bg-yellow-500',
                      job.status === 'completed' && 'bg-blue-500',
                      job.status === 'failed' && 'bg-red-500',
                      job.status === 'pending' && 'bg-gray-500'
                    )}
                  />
                  <span className="text-sm font-mono">{job.id.slice(0, 8)}...</span>
                </div>
                <span className="text-xs text-muted-foreground capitalize">
                  {job.status}
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-sm text-muted-foreground text-center py-4">
            No jobs yet.{' '}
            <Link href="/jobs/new" className="text-primary hover:underline">
              Create one
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
