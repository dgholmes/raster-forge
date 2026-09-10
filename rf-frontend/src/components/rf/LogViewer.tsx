import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, ScrollText } from 'lucide-react';
import { STATUS, type C } from '../../design-system/tokens';
import { rf } from '../../services/rasterforge';
import { Button, PanelTitle, Spinner } from './ui';

/* ============================================================================
 * LogViewer — the technical log, one click from every failure message.
 *
 * Auto-follows while a job is live, but stops following the moment the user
 * scrolls up: yanking the viewport back to the bottom while someone is
 * reading an error is the fastest way to make a log viewer useless.
 * ========================================================================== */

interface Props {
  C: C;
  jobId: string;
  live?: boolean;
  height?: number;
  pollMs?: number;
}

const LEVEL_COLORS: Record<string, string> = {
  ERROR: STATUS.red,
  WARN: STATUS.amber,
};

export const LogViewer: React.FC<Props> = ({ C, jobId, live = false, height = 320, pollMs = 3000 }) => {
  const [lines, setLines] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [follow, setFollow] = useState(true);
  const boxRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await rf.getJobLogs(jobId, 1000);
      setLines(res.lines);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not read the log.');
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void load();
    if (!live) return;
    const id = window.setInterval(() => void load(), pollMs);
    return () => window.clearInterval(id);
  }, [load, live, pollMs]);

  useEffect(() => {
    if (follow && boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
    }
  }, [lines, follow]);

  const onScroll = useCallback(() => {
    const el = boxRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    setFollow(atBottom);
  }, []);

  return (
    <div>
      <PanelTitle
        C={C}
        icon={ScrollText}
        right={
          <Button C={C} variant="ghost" icon={RefreshCw} onClick={() => void load()}>
            Refresh
          </Button>
        }
      >
        Processing log
      </PanelTitle>

      <div
        ref={boxRef}
        onScroll={onScroll}
        style={{
          height,
          overflowY: 'auto',
          overflowX: 'auto',
          background: C.dark ? '#111113' : '#fafafc',
          border: `1px solid ${C.b}`,
          borderRadius: 8,
          padding: 12,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
          fontSize: 11,
          lineHeight: 1.7,
          whiteSpace: 'pre',
        }}
      >
        {loading && (
          <div style={{ color: C.t3, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Spinner size={12} /> Loading log…
          </div>
        )}
        {error && <div style={{ color: STATUS.red }}>{error}</div>}
        {!loading && !error && lines.length === 0 && (
          <div style={{ color: C.t3 }}>No log output yet.</div>
        )}
        {lines.map((line, i) => {
          const level = line.slice(21, 26).trim();
          return (
            <div key={i} style={{ color: LEVEL_COLORS[level] ?? C.t2 }}>
              {line}
            </div>
          );
        })}
      </div>

      {live && !follow && (
        <button
          onClick={() => setFollow(true)}
          style={{
            marginTop: 8,
            background: 'transparent',
            border: 'none',
            color: C.accent,
            fontSize: 11,
            cursor: 'pointer',
            padding: 0,
          }}
        >
          Jump to latest
        </button>
      )}
    </div>
  );
};
