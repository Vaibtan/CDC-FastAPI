'use client';

import { format, formatDistanceToNow } from 'date-fns';
import { Clock, Calendar, Zap, FileText, AlertCircle, CheckCircle2, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { JobStatusBadge } from './JobStatusBadge';
import type { ReplayJob } from '@/types/job';

interface JobDetailPanelProps {
  job: ReplayJob;
}

export function JobDetailPanel({ job }: JobDetailPanelProps) {
  const stats = [
    {
      label: 'Processed',
      value: job.events_processed.toLocaleString(),
      icon: CheckCircle2,
      color: 'text-green-500',
    },
    {
      label: 'Failed',
      value: job.events_failed.toLocaleString(),
      icon: XCircle,
      color: 'text-red-500',
    },
    {
      label: 'Skipped (Dedup)',
      value: job.events_skipped_dedup.toLocaleString(),
      icon: AlertCircle,
      color: 'text-yellow-500',
    },
    {
      label: 'Total Events',
      value: job.events_total.toLocaleString(),
      icon: FileText,
      color: 'text-blue-500',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header Card */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg font-mono">{job.id}</CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                Created {formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
                {job.created_by && ` by ${job.created_by}`}
              </p>
            </div>
            <JobStatusBadge status={job.status} className="text-sm" />
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Progress Section */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Progress</span>
              <span className="font-medium">{job.progress_percent.toFixed(1)}%</span>
            </div>
            <Progress value={job.progress_percent} className="h-3" />
          </div>

          <Separator />

          {/* Time Range */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Calendar className="h-4 w-4" />
                <span>Start Time</span>
              </div>
              <p className="font-medium">
                {format(new Date(job.start_time), 'MMM d, yyyy HH:mm:ss')}
              </p>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Calendar className="h-4 w-4" />
                <span>End Time</span>
              </div>
              <p className="font-medium">
                {format(new Date(job.end_time), 'MMM d, yyyy HH:mm:ss')}
              </p>
            </div>
          </div>

          <Separator />

          {/* Speed and Duration */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Zap className="h-4 w-4" />
                <span>Speed Factor</span>
              </div>
              <p className="font-medium font-mono">{job.speed_factor}x</p>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Clock className="h-4 w-4" />
                <span>Duration</span>
              </div>
              <p className="font-medium">
                {job.finished_at
                  ? formatDistanceToNow(new Date(job.started_at || job.created_at), {
                      includeSeconds: true,
                    })
                  : job.started_at
                  ? 'Running...'
                  : 'Not started'}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardContent className="p-4">
              <div className="flex items-center gap-2">
                <stat.icon className={`h-5 w-5 ${stat.color}`} />
                <span className="text-sm text-muted-foreground">{stat.label}</span>
              </div>
              <p className="text-2xl font-bold mt-2">{stat.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Timestamps */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Timeline</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Created</span>
            <span>{format(new Date(job.created_at), 'MMM d, yyyy HH:mm:ss')}</span>
          </div>
          {job.started_at && (
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Started</span>
              <span>{format(new Date(job.started_at), 'MMM d, yyyy HH:mm:ss')}</span>
            </div>
          )}
          {job.paused_at && (
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Paused</span>
              <span>{format(new Date(job.paused_at), 'MMM d, yyyy HH:mm:ss')}</span>
            </div>
          )}
          {job.finished_at && (
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Finished</span>
              <span>{format(new Date(job.finished_at), 'MMM d, yyyy HH:mm:ss')}</span>
            </div>
          )}
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Last Updated</span>
            <span>{format(new Date(job.updated_at), 'MMM d, yyyy HH:mm:ss')}</span>
          </div>
        </CardContent>
      </Card>

      {/* Error Message */}
      {job.error_message && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-base text-destructive flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              Error
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-sm text-destructive whitespace-pre-wrap font-mono bg-destructive/10 p-3 rounded">
              {job.error_message}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
