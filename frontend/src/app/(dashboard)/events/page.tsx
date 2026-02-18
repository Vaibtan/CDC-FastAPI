'use client';

import { Pause, Play, Trash2, RefreshCw } from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ConnectionStatus } from '@/components/events/ConnectionStatus';
import { EventFilters } from '@/components/events/EventFilters';
import { EventStream } from '@/components/events/EventStream';
import { useEventStream, useStreamStats } from '@/hooks/useEvents';
import { useEventStore } from '@/stores/eventStore';

export default function EventsPage() {
  const {
    status,
    filteredEvents,
    isPaused,
    reconnectAttempts,
    tables,
    operations,
    connect,
    clearEvents,
    setPaused,
    setFilters,
    resetFilters,
  } = useEventStream();

  const { filters } = useEventStore();
  const { data: stats, isLoading: statsLoading } = useStreamStats();

  return (
    <div className="flex flex-col h-full">
      <Header title="Event Stream" />

      <div className="flex-1 p-6 space-y-4 overflow-hidden flex flex-col">
        {/* Status Bar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <ConnectionStatus status={status} reconnectAttempts={reconnectAttempts} />
            {!statsLoading && stats && (
              <div className="text-sm text-muted-foreground">
                Stream length: <span className="font-mono">{stats.stream_length.toLocaleString()}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPaused(!isPaused)}
            >
              {isPaused ? (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Resume
                </>
              ) : (
                <>
                  <Pause className="mr-2 h-4 w-4" />
                  Pause
                </>
              )}
            </Button>

            <Button variant="outline" size="sm" onClick={clearEvents}>
              <Trash2 className="mr-2 h-4 w-4" />
              Clear
            </Button>

            {status === 'disconnected' && (
              <Button variant="outline" size="sm" onClick={connect}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Reconnect
              </Button>
            )}
          </div>
        </div>

        {/* Filters */}
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm font-medium">Filters</CardTitle>
          </CardHeader>
          <CardContent className="pb-3">
            <EventFilters
              tables={tables}
              operations={operations}
              selectedTables={filters.tables}
              selectedOperations={filters.operations}
              searchQuery={filters.searchQuery}
              onTableChange={(tables) => setFilters({ tables })}
              onOperationChange={(operations) => setFilters({ operations })}
              onSearchChange={(searchQuery) => setFilters({ searchQuery })}
              onReset={resetFilters}
            />
          </CardContent>
        </Card>

        {/* Event Stream */}
        <Card className="flex-1 overflow-hidden">
          <CardHeader className="py-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">
                Events ({filteredEvents.length.toLocaleString()})
              </CardTitle>
              {isPaused && (
                <span className="text-xs text-yellow-500 font-medium">
                  Stream paused
                </span>
              )}
            </div>
          </CardHeader>
          <CardContent className="p-0 h-[calc(100%-60px)]">
            <EventStream events={filteredEvents} className="h-full px-4 pb-4" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
