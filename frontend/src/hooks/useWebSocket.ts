'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useAuthStore } from '@/stores/authStore';

export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  reconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

interface UseWebSocketReturn {
  status: WebSocketStatus;
  lastMessage: unknown | null;
  send: (data: unknown) => void;
  connect: () => void;
  disconnect: () => void;
  reconnectAttempts: number;
}

export function useWebSocket({
  url,
  onMessage,
  onOpen,
  onClose,
  onError,
  reconnect = true,
  reconnectInterval = 3000,
  maxReconnectAttempts = 10,
}: UseWebSocketOptions): UseWebSocketReturn {
  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const [lastMessage, setLastMessage] = useState<unknown | null>(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const mountedRef = useRef(true);

  const { token } = useAuthStore();

  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    clearReconnectTimeout();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('disconnected');
  }, [clearReconnectTimeout]);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    // Add auth token to URL if available
    const wsUrl = new URL(url);
    if (token) {
      wsUrl.searchParams.set('token', token);
    }

    setStatus('connecting');
    const ws = new WebSocket(wsUrl.toString());

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setStatus('connected');
      setReconnectAttempts(0);
      onOpen?.();
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const data = JSON.parse(event.data);
        setLastMessage(data);
        onMessage?.(data);
      } catch {
        // If not JSON, pass raw data
        setLastMessage(event.data);
        onMessage?.(event.data);
      }
    };

    ws.onerror = (error) => {
      if (!mountedRef.current) return;
      setStatus('error');
      onError?.(error);
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setStatus('disconnected');
      onClose?.();

      // Attempt reconnection with exponential backoff
      if (reconnect && reconnectAttempts < maxReconnectAttempts) {
        const backoffTime = Math.min(
          reconnectInterval * Math.pow(2, reconnectAttempts),
          30000 // Max 30 seconds
        );

        reconnectTimeoutRef.current = setTimeout(() => {
          if (mountedRef.current) {
            setReconnectAttempts((prev) => prev + 1);
            connect();
          }
        }, backoffTime);
      }
    };

    wsRef.current = ws;
  }, [url, token, reconnect, reconnectInterval, maxReconnectAttempts, reconnectAttempts, onMessage, onOpen, onClose, onError]);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      clearReconnectTimeout();
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect, clearReconnectTimeout]);

  return {
    status,
    lastMessage,
    send,
    connect,
    disconnect,
    reconnectAttempts,
  };
}
