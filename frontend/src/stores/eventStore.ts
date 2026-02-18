import { create } from 'zustand';
import type { CDCEvent } from '@/types/event';

const MAX_EVENTS = 1000;

interface EventFilters {
  tables: string[];
  operations: string[];
  searchQuery: string;
}

interface EventState {
  events: CDCEvent[];
  filters: EventFilters;
  isPaused: boolean;

  // Actions
  addEvent: (event: CDCEvent) => void;
  addEvents: (events: CDCEvent[]) => void;
  clearEvents: () => void;
  setFilters: (filters: Partial<EventFilters>) => void;
  resetFilters: () => void;
  setPaused: (paused: boolean) => void;

  // Computed
  filteredEvents: () => CDCEvent[];
  uniqueTables: () => string[];
  uniqueOperations: () => string[];
}

const initialFilters: EventFilters = {
  tables: [],
  operations: [],
  searchQuery: '',
};

/** Extract table name from a CDCEvent (nested or fallback). */
function getTable(event: CDCEvent): string {
  return event.event?.table ?? event.table ?? '';
}

/** Extract operation from a CDCEvent (nested or fallback). */
function getOperation(event: CDCEvent): string {
  return event.event?.operation ?? event.operation ?? '';
}

export const useEventStore = create<EventState>((set, get) => ({
  events: [],
  filters: initialFilters,
  isPaused: false,

  addEvent: (event) => {
    if (get().isPaused) return;

    set((state) => ({
      events: [event, ...state.events].slice(0, MAX_EVENTS),
    }));
  },

  addEvents: (events) => {
    if (get().isPaused) return;

    set((state) => ({
      events: [...events, ...state.events].slice(0, MAX_EVENTS),
    }));
  },

  clearEvents: () => set({ events: [] }),

  setFilters: (newFilters) =>
    set((state) => ({
      filters: { ...state.filters, ...newFilters },
    })),

  resetFilters: () => set({ filters: initialFilters }),

  setPaused: (paused) => set({ isPaused: paused }),

  filteredEvents: () => {
    const { events, filters } = get();

    return events.filter((event) => {
      const table = getTable(event);
      const operation = getOperation(event);

      // Filter by table
      if (filters.tables.length > 0 && !filters.tables.includes(table)) {
        return false;
      }

      // Filter by operation
      if (filters.operations.length > 0 && !filters.operations.includes(operation)) {
        return false;
      }

      // Filter by search query
      if (filters.searchQuery) {
        const query = filters.searchQuery.toLowerCase();
        const searchableText = JSON.stringify(event).toLowerCase();
        if (!searchableText.includes(query)) {
          return false;
        }
      }

      return true;
    });
  },

  uniqueTables: () => {
    const { events } = get();
    return Array.from(new Set(events.map(getTable).filter(Boolean))).sort();
  },

  uniqueOperations: () => {
    const { events } = get();
    return Array.from(new Set(events.map(getOperation).filter(Boolean))).sort();
  },
}));
