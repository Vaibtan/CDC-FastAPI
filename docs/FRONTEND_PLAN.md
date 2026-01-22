# WalStream CDC NextJS Dashboard - Full Implementation Plan

## Overview

This document outlines the complete implementation plan for a NextJS 14 dashboard that provides:
- Real-time CDC event streaming via WebSocket
- Replay job management with full lifecycle control
- Prometheus metrics visualization
- JWT-based authentication

## Technology Stack

| Category | Technology | Justification |
|----------|------------|---------------|
| Framework | NextJS 14 (App Router) | Server Components, streaming, modern React patterns |
| UI Library | shadcn/ui + Tailwind CSS | Accessible, customizable components |
| State (Server) | @tanstack/react-query | Caching, background refetch, optimistic updates |
| State (Client) | Zustand | Lightweight, simple auth/UI state |
| Charts | Recharts | React-native, declarative, good for time-series |
| HTTP Client | Axios | Interceptors for auth tokens |
| Validation | Zod | TypeScript-first schema validation |
| Virtualization | @tanstack/react-virtual | Efficient rendering for event streams |

## Project Structure

```
frontend/
├── src/
│   ├── app/                           # NextJS App Router
│   │   ├── layout.tsx                 # Root layout with providers
│   │   ├── globals.css                # Tailwind + custom styles
│   │   ├── (auth)/
│   │   │   └── login/
│   │   │       └── page.tsx           # Login page
│   │   └── (dashboard)/
│   │       ├── layout.tsx             # Dashboard shell (sidebar + header)
│   │       ├── page.tsx               # Overview dashboard
│   │       ├── jobs/
│   │       │   ├── page.tsx           # Jobs list
│   │       │   ├── [id]/page.tsx      # Job detail
│   │       │   └── new/page.tsx       # Create job form
│   │       ├── events/
│   │       │   └── page.tsx           # Real-time event stream
│   │       └── metrics/
│   │           └── page.tsx           # Prometheus metrics charts
│   │
│   ├── components/
│   │   ├── ui/                        # shadcn/ui components
│   │   │   ├── button.tsx
│   │   │   ├── card.tsx
│   │   │   ├── data-table.tsx
│   │   │   ├── dialog.tsx
│   │   │   ├── form.tsx
│   │   │   ├── input.tsx
│   │   │   ├── select.tsx
│   │   │   ├── badge.tsx
│   │   │   ├── progress.tsx
│   │   │   ├── skeleton.tsx
│   │   │   └── toast.tsx
│   │   │
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx            # Navigation sidebar
│   │   │   ├── Header.tsx             # Top header with user menu
│   │   │   └── ThemeToggle.tsx        # Dark/light mode switch
│   │   │
│   │   ├── auth/
│   │   │   ├── LoginForm.tsx          # Username/password form
│   │   │   └── ProtectedRoute.tsx     # Auth guard component
│   │   │
│   │   ├── jobs/
│   │   │   ├── JobsTable.tsx          # DataTable with actions
│   │   │   ├── JobStatusBadge.tsx     # Colored status indicator
│   │   │   ├── JobProgressBar.tsx     # Progress with percentage
│   │   │   ├── JobDetailPanel.tsx     # Full job information
│   │   │   ├── JobCreateForm.tsx      # Create job form
│   │   │   └── JobActions.tsx         # Start/Pause/Resume/Cancel buttons
│   │   │
│   │   ├── events/
│   │   │   ├── EventStream.tsx        # Virtualized event list
│   │   │   ├── EventCard.tsx          # Single event display
│   │   │   ├── EventFilters.tsx       # Table/operation filters
│   │   │   ├── EventDetailModal.tsx   # Full event payload
│   │   │   └── ConnectionStatus.tsx   # WebSocket status indicator
│   │   │
│   │   ├── metrics/
│   │   │   ├── MetricsGrid.tsx        # Dashboard grid layout
│   │   │   ├── EventsLineChart.tsx    # Events over time
│   │   │   ├── OperationsBarChart.tsx # Events by operation type
│   │   │   ├── LatencyGauge.tsx       # Replay latency gauge
│   │   │   ├── ThroughputCard.tsx     # Events per second
│   │   │   └── MetricCard.tsx         # Reusable metric display
│   │   │
│   │   └── dashboard/
│   │       ├── OverviewCards.tsx      # Summary statistics
│   │       ├── RecentJobs.tsx         # Latest jobs table
│   │       ├── HealthStatus.tsx       # System health indicators
│   │       └── QuickActions.tsx       # Common action buttons
│   │
│   ├── hooks/
│   │   ├── useAuth.ts                 # Auth state and actions
│   │   ├── useWebSocket.ts            # WebSocket connection management
│   │   ├── useJobs.ts                 # React Query hooks for jobs
│   │   ├── useMetrics.ts              # Metrics fetching hooks
│   │   └── useDebounce.ts             # Input debouncing
│   │
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts              # Axios instance with interceptors
│   │   │   ├── auth.ts                # Auth API functions
│   │   │   ├── jobs.ts                # Jobs API functions
│   │   │   ├── events.ts              # Events API functions
│   │   │   └── metrics.ts             # Metrics API functions
│   │   │
│   │   ├── utils/
│   │   │   ├── cn.ts                  # Class name helper
│   │   │   ├── formatters.ts          # Date, number formatters
│   │   │   └── prometheus-parser.ts   # Parse Prometheus text format
│   │   │
│   │   └── constants.ts               # API URLs, config values
│   │
│   ├── stores/
│   │   ├── authStore.ts               # Zustand auth store
│   │   ├── eventStore.ts              # Event stream state
│   │   └── uiStore.ts                 # Sidebar, theme state
│   │
│   └── types/
│       ├── api.ts                     # API response types
│       ├── job.ts                     # Job-related types
│       ├── event.ts                   # CDC event types
│       └── metrics.ts                 # Metrics types
│
├── public/
│   └── favicon.ico
│
├── .env.local                         # Environment variables
├── .env.example                       # Template env file
├── Dockerfile                         # Production Docker build
├── next.config.js                     # NextJS configuration
├── tailwind.config.ts                 # Tailwind configuration
├── tsconfig.json                      # TypeScript configuration
├── components.json                    # shadcn/ui configuration
└── package.json
```

## Backend API Reference

### Authentication Endpoints

```
POST /api/v1/auth/register
  Body: { username, email, password }
  Response: { id, username, email }

POST /api/v1/auth/token
  Body: application/x-www-form-urlencoded
    username=<user>&password=<pass>
  Response: { access_token, token_type: "bearer" }
```

### Jobs Endpoints

```
GET    /api/v1/jobs?status=<filter>&page=<n>&page_size=<n>
POST   /api/v1/jobs
GET    /api/v1/jobs/{job_id}
PATCH  /api/v1/jobs/{job_id}
DELETE /api/v1/jobs/{job_id}

POST   /api/v1/jobs/{job_id}/start
POST   /api/v1/jobs/{job_id}/pause
POST   /api/v1/jobs/{job_id}/resume
POST   /api/v1/jobs/{job_id}/cancel
```

### Events Endpoints

```
WebSocket: ws://localhost:8000/api/v1/events/ws
  Messages: JSON { table, operation, lsn, time_ms, payload }
```

### Health & Metrics

```
GET /api/v1/health/live
GET /api/v1/health/ready

GET :9090/metrics   # Ingestor Prometheus
GET :9091/metrics   # Control Prometheus
GET :9092/metrics   # Replayer Prometheus
```

## TypeScript Types

### Job Types (src/types/job.ts)

```typescript
export type JobStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface ReplayJob {
  id: string;
  start_time: string;      // ISO datetime
  end_time: string;        // ISO datetime
  speed_factor: number;    // 0.1 to 100
  status: JobStatus;
  target_type?: string;
  target_url?: string;
  table_filter?: string[];
  created_by?: string;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
  events_total: number;
  events_processed: number;
  events_failed: number;
  events_skipped_dedup: number;
  last_processed_id?: string;
  last_processed_time?: string;
  error_message?: string;
  error_count: number;
  replay_source?: 'redis' | 'kafka';
  worker_id?: string;
}

export interface ReplayJobCreate {
  start_time: string;
  end_time: string;
  speed_factor?: number;
  target_type?: string;
  target_url?: string;
  table_filter?: string[];
}

export interface ReplayJobListResponse {
  items: ReplayJob[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
```

### Event Types (src/types/event.ts)

```typescript
export type OperationType = 'INSERT' | 'UPDATE' | 'DELETE';

export interface CDCEvent {
  id: string;           // Unique message ID
  table: string;        // e.g., "public.events"
  schema: string;       // e.g., "public"
  operation: OperationType;
  lsn: string;          // PostgreSQL LSN
  commit_time_ms: number;
  old?: Record<string, unknown>;
  new?: Record<string, unknown>;
  pk?: Record<string, unknown>;
}
```

### Metrics Types (src/types/metrics.ts)

```typescript
export interface MetricValue {
  name: string;
  value: number;
  labels?: Record<string, string>;
  timestamp?: number;
}

export interface MetricsSnapshot {
  events_ingested_total: number;
  events_published_redis_total: number;
  events_published_kafka_total: number;
  events_replayed_total: number;
  events_duplicates_total: number;
  events_failed_total: number;
  ingest_latency_seconds: number;
  replay_latency_seconds: number;
}
```

## Key Implementation Details

### 1. API Client (src/lib/api/client.ts)

```typescript
import axios from 'axios';
import { useAuthStore } from '@/stores/authStore';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for auth token
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for 401 handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

### 2. WebSocket Hook (src/hooks/useWebSocket.ts)

```typescript
import { useEffect, useRef, useCallback, useState } from 'react';
import { useAuthStore } from '@/stores/authStore';
import type { CDCEvent } from '@/types/event';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

export function useWebSocket(onMessage: (event: CDCEvent) => void) {
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const token = useAuthStore((s) => s.token);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(`${WS_URL}/api/v1/events/ws?token=${token}`);

    ws.onopen = () => setStatus('connected');
    ws.onclose = () => {
      setStatus('disconnected');
      // Auto-reconnect after 3 seconds
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };
    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as CDCEvent;
        onMessage(event);
      } catch (err) {
        console.error('Failed to parse WebSocket message', err);
      }
    };

    wsRef.current = ws;
  }, [token, onMessage]);

  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimeoutRef.current);
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  useEffect(() => {
    if (token) connect();
    return () => disconnect();
  }, [token, connect, disconnect]);

  return { status, connect, disconnect };
}
```

### 3. Auth Store (src/stores/authStore.ts)

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  token: string | null;
  user: { username: string; email: string } | null;
  isAuthenticated: boolean;
  login: (token: string, user: { username: string; email: string }) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      login: (token, user) => set({ token, user, isAuthenticated: true }),
      logout: () => set({ token: null, user: null, isAuthenticated: false }),
    }),
    {
      name: 'walstream-auth',
      partialize: (state) => ({ token: state.token, user: state.user }),
    }
  )
);
```

### 4. Jobs React Query Hooks (src/hooks/useJobs.ts)

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as jobsApi from '@/lib/api/jobs';
import type { ReplayJob, JobStatus } from '@/types/job';

export function useJobs(status?: JobStatus, page = 1, pageSize = 20) {
  return useQuery({
    queryKey: ['jobs', { status, page, pageSize }],
    queryFn: () => jobsApi.listJobs({ status, page, page_size: pageSize }),
    refetchInterval: 5000, // Poll every 5s for status updates
  });
}

export function useJob(jobId: string) {
  return useQuery({
    queryKey: ['jobs', jobId],
    queryFn: () => jobsApi.getJob(jobId),
    refetchInterval: (data) =>
      data?.status === 'running' ? 1000 : 5000, // Faster polling for running jobs
  });
}

export function useCreateJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: jobsApi.createJob,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export function useJobAction(action: 'start' | 'pause' | 'resume' | 'cancel') {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => jobsApi[`${action}Job`](jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      queryClient.invalidateQueries({ queryKey: ['jobs', jobId] });
    },
  });
}
```

### 5. Prometheus Parser (src/lib/utils/prometheus-parser.ts)

```typescript
export interface ParsedMetric {
  name: string;
  labels: Record<string, string>;
  value: number;
}

export function parsePrometheusText(text: string): ParsedMetric[] {
  const metrics: ParsedMetric[] = [];
  const lines = text.split('\n');

  for (const line of lines) {
    // Skip comments and empty lines
    if (line.startsWith('#') || line.trim() === '') continue;

    // Match: metric_name{label="value"} 123.45
    const match = line.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}\s+(.+)$/);
    if (match) {
      const [, name, labelsStr, valueStr] = match;
      const labels: Record<string, string> = {};

      // Parse labels
      labelsStr.split(',').forEach((pair) => {
        const [key, value] = pair.split('=');
        if (key && value) {
          labels[key.trim()] = value.replace(/"/g, '').trim();
        }
      });

      metrics.push({
        name,
        labels,
        value: parseFloat(valueStr),
      });
    } else {
      // Match: metric_name 123.45
      const simpleMatch = line.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)\s+(.+)$/);
      if (simpleMatch) {
        const [, name, valueStr] = simpleMatch;
        metrics.push({
          name,
          labels: {},
          value: parseFloat(valueStr),
        });
      }
    }
  }

  return metrics;
}
```

## Component Specifications

### JobsTable Component

Features:
- Sortable columns (created_at, status, events_processed)
- Status filter dropdown
- Pagination controls
- Row actions (Start, Pause, Resume, Cancel, Delete)
- Progress bar for running jobs
- Responsive design (collapsible columns on mobile)

### EventStream Component

Features:
- Virtualized list using @tanstack/react-virtual
- Max 1000 events in memory (FIFO)
- Filter by table name (autocomplete)
- Filter by operation type (checkbox group)
- Click to expand event details
- Auto-scroll toggle
- Connection status indicator

### MetricsCharts Component

Features:
- LineChart: Events ingested over time (5min window, 10s intervals)
- BarChart: Events by operation type
- Area chart: Latency percentiles
- Gauge: Current throughput
- Auto-refresh every 10 seconds

## Docker Configuration

### Dockerfile

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
```

### docker-compose.yml Addition

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://control:8000
      - NEXT_PUBLIC_WS_URL=ws://control:8000
    depends_on:
      - control
    networks:
      - walstream
```

## Environment Variables

```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# Prometheus endpoints (optional, for server-side fetching)
PROMETHEUS_INGESTOR_URL=http://localhost:9090/metrics
PROMETHEUS_CONTROL_URL=http://localhost:9091/metrics
PROMETHEUS_REPLAYER_URL=http://localhost:9092/metrics
```

## Implementation Phases

### Phase 1: Foundation
1. Initialize NextJS 14 project with TypeScript
2. Install and configure Tailwind CSS
3. Set up shadcn/ui (init + add button, card, input, form)
4. Create API client with axios
5. Implement auth store with Zustand
6. Create login page and form
7. Implement protected route middleware
8. Create basic dashboard layout (sidebar + header)

### Phase 2: Job Management
1. Define job TypeScript types
2. Create jobs API functions
3. Implement useJobs React Query hooks
4. Build JobsTable with DataTable
5. Create JobStatusBadge component
6. Implement job actions (start/pause/resume/cancel)
7. Build JobDetailPanel with progress tracking
8. Create JobCreateForm with validation

### Phase 3: Real-time Events
1. Implement useWebSocket hook
2. Create event store with Zustand
3. Build EventStream with virtualization
4. Create EventCard component
5. Implement EventFilters
6. Build EventDetailModal
7. Add ConnectionStatus indicator

### Phase 4: Metrics Dashboard
1. Create Prometheus text parser
2. Build metrics API functions
3. Implement useMetrics hooks
4. Create EventsLineChart with Recharts
5. Build OperationsBarChart
6. Create LatencyGauge component
7. Build MetricsGrid layout
8. Add auto-refresh functionality

### Phase 5: Polish & Integration
1. Create dashboard overview page
2. Build OverviewCards component
3. Add HealthStatus indicators
4. Implement dark/light mode toggle
5. Create responsive sidebar
6. Add toast notifications
7. Build Docker configuration
8. Update main docker-compose.yml
9. Add error boundaries
10. Performance optimization (memoization, code splitting)

## Testing Strategy

### Unit Tests
- Component tests with Vitest + Testing Library
- Hook tests with renderHook
- Utility function tests

### Integration Tests
- API client tests with MSW
- Page-level tests with mock providers

### E2E Tests (Optional)
- Playwright for critical user flows
- Login flow
- Job creation and lifecycle
- Event stream filtering

## Performance Considerations

1. **Event Stream**: Limit to 1000 events, use virtualization
2. **Job Polling**: Dynamic intervals based on job status
3. **Metrics**: Client-side caching, 10s refresh
4. **Bundle Size**: Use dynamic imports for charts
5. **Images**: NextJS Image optimization
6. **Fonts**: Use next/font for optimal loading
