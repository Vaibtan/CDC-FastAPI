'use client';

import { useRef, useState, useCallback } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { EventCard } from './EventCard';
import { EventDetailModal } from './EventDetailModal';
import type { CDCEvent } from '@/types/event';

interface EventStreamProps {
  events: CDCEvent[];
  className?: string;
}

export function EventStream({ events, className }: EventStreamProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const [selectedEvent, setSelectedEvent] = useState<CDCEvent | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const virtualizer = useVirtualizer({
    count: events.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 100,
    overscan: 5,
  });

  const handleEventClick = useCallback((event: CDCEvent) => {
    setSelectedEvent(event);
    setModalOpen(true);
  }, []);

  if (events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
        <p className="text-lg font-medium">No events yet</p>
        <p className="text-sm">Events will appear here as they stream in</p>
      </div>
    );
  }

  return (
    <>
      <div
        ref={parentRef}
        className={className}
        style={{ overflow: 'auto', contain: 'strict' }}
      >
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {virtualizer.getVirtualItems().map((virtualItem) => {
            const event = events[virtualItem.index];
            return (
              <div
                key={virtualItem.key}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualItem.size}px`,
                  transform: `translateY(${virtualItem.start}px)`,
                  padding: '4px 0',
                }}
              >
                <EventCard
                  event={event}
                  onClick={() => handleEventClick(event)}
                />
              </div>
            );
          })}
        </div>
      </div>

      <EventDetailModal
        event={selectedEvent}
        open={modalOpen}
        onOpenChange={setModalOpen}
      />
    </>
  );
}
