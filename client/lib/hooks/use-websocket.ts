'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { WS_URL, JOB_POLL_INTERVAL_MS, WS_RECONNECT_DELAY_MS } from '../constants';
import { api } from '../api-client';
import type { JobStatus } from '../types';

interface UseJobProgressResult {
  progress: JobStatus | null;
  error: string | null;
}

export function useJobProgress(jobId: string | null): UseJobProgressResult {
  const [progress, setProgress] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const closeWs = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      try {
        wsRef.current.close();
      } catch {
        // ignore
      }
      wsRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (id: string) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const status = await api.getJobStatus(id);
          if (!mountedRef.current) return;
          setProgress(status);
          if (status.status === 'complete' || status.status === 'error') {
            stopPolling();
          }
        } catch (err) {
          if (!mountedRef.current) return;
          setError(err instanceof Error ? err.message : 'Polling failed');
          stopPolling();
        }
      }, JOB_POLL_INTERVAL_MS);
    },
    [stopPolling],
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!jobId) {
      setProgress(null);
      setError(null);
      closeWs();
      stopPolling();
      return;
    }

    setError(null);
    closeWs();
    stopPolling();

    const wsUrl = `${WS_URL}/studio/progress/${jobId}`;
    let ws: WebSocket;

    try {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (evt) => {
        if (!mountedRef.current) return;
        try {
          const data: JobStatus = JSON.parse(evt.data as string);
          setProgress(data);
          if (data.status === 'complete' || data.status === 'error') {
            closeWs();
          }
        } catch {
          // non-JSON message, ignore
        }
      };

      ws.onerror = () => {
        if (!mountedRef.current) return;
        // WS failed — fall back to polling after a short delay
        setTimeout(() => {
          if (mountedRef.current) {
            startPolling(jobId);
          }
        }, WS_RECONNECT_DELAY_MS);
      };

      ws.onclose = (evt) => {
        if (!mountedRef.current) return;
        if (evt.code !== 1000 && evt.code !== 1001) {
          // Unexpected close — fall back to polling
          startPolling(jobId);
        }
      };
    } catch {
      // WebSocket constructor failed (e.g., invalid URL) — fall back to polling
      startPolling(jobId);
    }

    return () => {
      closeWs();
      stopPolling();
    };
  }, [jobId, closeWs, stopPolling, startPolling]);

  return { progress, error };
}
