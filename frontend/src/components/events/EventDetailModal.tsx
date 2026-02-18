'use client';

import { format } from 'date-fns';
import { Copy, Check } from 'lucide-react';
import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { CDCEvent, CDCOperation } from '@/types/event';

interface EventDetailModalProps {
  event: CDCEvent | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function JsonViewer({ data, label }: { data: unknown; label: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!data || (typeof data === 'object' && Object.keys(data as object).length === 0)) {
    return (
      <div className="text-sm text-muted-foreground italic">
        No {label.toLowerCase()} available
      </div>
    );
  }

  return (
    <div className="relative">
      <Button
        size="sm"
        variant="ghost"
        className="absolute top-2 right-2"
        onClick={handleCopy}
      >
        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      </Button>
      <pre className="text-sm bg-muted p-4 rounded-lg overflow-auto max-h-80">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

export function EventDetailModal({ event, open, onOpenChange }: EventDetailModalProps) {
  if (!event) return null;

  const operation = (event.event?.operation ?? event.operation ?? 'INSERT') as CDCOperation;
  const table = event.event?.table ?? event.table ?? 'unknown';
  const lsn = event.event?.lsn ?? '';
  const newData = event.event?.new ?? {};
  const oldData = event.event?.old ?? {};

  // Split "schema.table" into schema and table parts
  const tableParts = table.split('.');
  const schemaName = tableParts.length > 1 ? tableParts[0] : 'public';
  const tableName = tableParts.length > 1 ? tableParts.slice(1).join('.') : table;

  const timestamp = event.event?.commit_time
    ? new Date(event.event.commit_time)
    : null;

  const operationColor = {
    INSERT: 'bg-green-500',
    UPDATE: 'bg-blue-500',
    DELETE: 'bg-red-500',
    TRUNCATE: 'bg-yellow-500',
  }[operation];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <span>{tableName}</span>
            <Badge className={operationColor}>{operation}</Badge>
          </DialogTitle>
        </DialogHeader>

        <ScrollArea className="max-h-[60vh]">
          <div className="space-y-6 pr-4">
            {/* Metadata */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-muted-foreground mb-1">Stream ID</div>
                <div className="font-mono">{event.id}</div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1">Timestamp</div>
                <div>{timestamp ? format(timestamp, 'PPpp') : 'N/A'}</div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1">Schema</div>
                <div className="font-mono">{schemaName}</div>
              </div>
              <div>
                <div className="text-muted-foreground mb-1">LSN</div>
                <div className="font-mono">{lsn || 'N/A'}</div>
              </div>
            </div>

            {/* Data Tabs */}
            <Tabs defaultValue="new" className="w-full">
              <TabsList>
                <TabsTrigger value="new">New Data</TabsTrigger>
                <TabsTrigger value="old">Old Data</TabsTrigger>
                <TabsTrigger value="raw">Raw Event</TabsTrigger>
              </TabsList>

              <TabsContent value="new" className="mt-4">
                <JsonViewer data={newData} label="New Data" />
              </TabsContent>

              <TabsContent value="old" className="mt-4">
                <JsonViewer data={oldData} label="Old Data" />
              </TabsContent>

              <TabsContent value="raw" className="mt-4">
                <JsonViewer data={event} label="Raw Event" />
              </TabsContent>
            </Tabs>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
