import { useEffect, useState } from 'react';
import { apiService } from '../services/api';
import type { BackendStatus } from '../types';

/* ============================================================================
 * useBackendStatus — polls the health endpoint every 15s.
 * Returns 'checking' | 'online' | 'offline' for the topbar status dot.
 * ========================================================================== */

const POLL_INTERVAL = 15_000;

export function useBackendStatus(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>('checking');

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        await apiService.getHealth();
        if (!cancelled) setStatus('online');
      } catch {
        if (!cancelled) setStatus('offline');
      }
    };

    check();
    const id = window.setInterval(check, POLL_INTERVAL);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return status;
}
