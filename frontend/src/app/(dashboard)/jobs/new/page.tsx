'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { JobCreateForm } from '@/components/jobs/JobCreateForm';
import { useCreateJob } from '@/hooks/useJobs';
import { useToast } from '@/hooks/use-toast';

export default function NewJobPage() {
  const router = useRouter();
  const { toast } = useToast();
  const createJob = useCreateJob();

  const handleSubmit = async (data: {
    start_time: string;
    end_time: string;
    speed_factor: number;
  }) => {
    try {
      const job = await createJob.mutateAsync(data);
      toast({ title: 'Job created successfully' });
      router.push(`/jobs/${job.id}`);
    } catch (error) {
      toast({
        title: 'Failed to create job',
        description: error instanceof Error ? error.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  return (
    <div className="flex flex-col">
      <Header title="Create Replay Job" />

      <div className="p-6 space-y-6 max-w-3xl">
        {/* Navigation */}
        <Button variant="ghost" asChild>
          <Link href="/jobs">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Jobs
          </Link>
        </Button>

        {/* Form */}
        <JobCreateForm onSubmit={handleSubmit} isLoading={createJob.isPending} />
      </div>
    </div>
  );
}
