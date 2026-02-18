'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { format } from 'date-fns';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const jobCreateSchema = z.object({
  start_time: z.string().min(1, 'Start time is required'),
  end_time: z.string().min(1, 'End time is required'),
  speed_factor: z.number().min(0.1, 'Speed must be at least 0.1x').max(100, 'Speed must be at most 100x'),
}).refine(
  (data) => new Date(data.end_time) > new Date(data.start_time),
  {
    message: 'End time must be after start time',
    path: ['end_time'],
  }
);

type JobCreateFormValues = {
  start_time: string;
  end_time: string;
  speed_factor: number;
};

interface JobCreateFormProps {
  onSubmit: (data: JobCreateFormValues) => Promise<void>;
  isLoading?: boolean;
}

const speedPresets = [
  { value: '0.5', label: '0.5x (Slow)' },
  { value: '1', label: '1x (Real-time)' },
  { value: '2', label: '2x' },
  { value: '5', label: '5x' },
  { value: '10', label: '10x' },
  { value: '50', label: '50x (Fast)' },
];

export function JobCreateForm({ onSubmit, isLoading }: JobCreateFormProps) {
  const form = useForm<JobCreateFormValues>({
    resolver: zodResolver(jobCreateSchema),
    defaultValues: {
      start_time: '',
      end_time: '',
      speed_factor: 1,
    },
  });

  const handleSubmit = form.handleSubmit(async (data) => {
    await onSubmit({
      start_time: new Date(data.start_time).toISOString(),
      end_time: new Date(data.end_time).toISOString(),
      speed_factor: data.speed_factor,
    });
  });

  // Helper to set quick time ranges
  const setTimeRange = (hours: number) => {
    const now = new Date();
    const start = new Date(now.getTime() - hours * 60 * 60 * 1000);
    form.setValue('start_time', format(start, "yyyy-MM-dd'T'HH:mm"));
    form.setValue('end_time', format(now, "yyyy-MM-dd'T'HH:mm"));
  };

  return (
    <Form {...form}>
      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Time Range</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Quick Range Buttons */}
            <div className="flex flex-wrap gap-2">
              <span className="text-sm text-muted-foreground mr-2">Quick select:</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setTimeRange(1)}
              >
                Last 1 hour
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setTimeRange(6)}
              >
                Last 6 hours
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setTimeRange(24)}
              >
                Last 24 hours
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setTimeRange(168)}
              >
                Last 7 days
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="start_time"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Start Time</FormLabel>
                    <FormControl>
                      <Input type="datetime-local" {...field} />
                    </FormControl>
                    <FormDescription>
                      Replay events from this time
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="end_time"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>End Time</FormLabel>
                    <FormControl>
                      <Input type="datetime-local" {...field} />
                    </FormControl>
                    <FormDescription>
                      Replay events until this time
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Replay Speed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <FormField
              control={form.control}
              name="speed_factor"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Speed Factor</FormLabel>
                  <div className="flex gap-4">
                    <Select
                      value={String(field.value)}
                      onValueChange={(value) => field.onChange(parseFloat(value))}
                    >
                      <FormControl>
                        <SelectTrigger className="w-48">
                          <SelectValue placeholder="Select speed" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {speedPresets.map((preset) => (
                          <SelectItem key={preset.value} value={preset.value}>
                            {preset.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <span className="text-sm text-muted-foreground self-center">or</span>
                    <Input
                      type="number"
                      step="0.1"
                      min="0.1"
                      max="100"
                      className="w-24"
                      value={field.value}
                      onChange={(e) => field.onChange(parseFloat(e.target.value) || 1)}
                    />
                  </div>
                  <FormDescription>
                    1x = real-time, 10x = 10 times faster than real-time
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        <div className="flex justify-end gap-4">
          <Button type="button" variant="outline" onClick={() => form.reset()}>
            Reset
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Create Job
          </Button>
        </div>
      </form>
    </Form>
  );
}
