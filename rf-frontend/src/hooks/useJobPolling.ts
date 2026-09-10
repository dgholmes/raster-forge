import { useCallback, useEffect, useRef, useState } from 'react';
import { rf } from '../services/rasterforge';
import { ACTIVE_JOB_STATUSES, type ProcessingJob } from '../types/rasterforge';

/* ============================================================================
 * useJobPolling — follow a job to completion.
 *
 * Polling, not sockets, is the authoritative channel: it is correct across a
 * page reload, a dropped connection, and a server restart, which is exactly
 * what "leave the page and come back" requires. The backend also pushes
 * `job:progress` over SocketIO, but that is an optimisation layered on top,
 * never the source of truth.
 * ========================================================================== */

interface Options {
  intervalMs?: number;
  /** Fired once when the job reaches a terminal state. */
  onFinished?: (job: ProcessingJob) => void;
  enabled?: boolean;
}

export interface UseJobPollingResult {
  job: ProcessingJob | null;
  error: string | null;
  isPolling: boolean;
  refresh: () => Promise<void>;
}

export function useJobPolling(
  jobId: string | null | undefined,
  { intervalMs = 1500, onFinished, enabled = true }: Options = {},
): UseJobPollingResult {
  const [job, setJob] = useState<ProcessingJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  // Held in a ref so a caller passing an inline arrow function does not
  // restart the interval on every render.
  const onFinishedRef = useRef(onFinished);
  useEffect(() => {
    onFinishedRef.current = onFinished;
  }, [onFinished]);

  const finishedRef = useRef(false);
  const timerRef = useRef<number | null>(null);

  const fetchJob = useCallback(async () => {
    if (!jobId) return;
    try {
      const next = await rf.getJob(jobId);
      setJob(next);
      setError(null);
      if (!ACTIVE_JOB_STATUSES.includes(next.status) && !finishedRef.current) {
        finishedRef.current = true;
        setIsPolling(false);
        onFinishedRef.current?.(next);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not read job status.');
    }
  }, [jobId]);

  useEffect(() => {
    finishedRef.current = false;
    setJob(null);
    setError(null);

    if (!jobId || !enabled) {
      setIsPolling(false);
      return;
    }

    setIsPolling(true);
    void fetchJob();

    timerRef.current = window.setInterval(() => {
      if (finishedRef.current) {
        if (timerRef.current !== null) window.clearInterval(timerRef.current);
        timerRef.current = null;
        return;
      }
      void fetchJob();
    }, intervalMs);

    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      timerRef.current = null;
    };
  }, [jobId, enabled, intervalMs, fetchJob]);

  return { job, error, isPolling, refresh: fetchJob };
}
