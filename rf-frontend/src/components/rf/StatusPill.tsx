import React from 'react';
import { STATUS, type C } from '../../design-system/tokens';
import type { DatasetStatus, JobStatus } from '../../types/rasterforge';

/* ============================================================================
 * StatusPill — one visual language for every dataset and job state.
 *
 * Status colour carries meaning and nothing else (design system rule):
 *   green = done, amber = in flight, red = failed, muted = not started.
 * ========================================================================== */

type AnyStatus = DatasetStatus | JobStatus | string;

interface Tone {
  label: string;
  fg: string;
  bg: string;
  /** In-flight states pulse so a glance distinguishes them from a settled one. */
  pulse?: boolean;
}

export function statusTone(status: AnyStatus, C: C): Tone {
  switch (status) {
    case 'completed':
      return { label: 'Completed', fg: STATUS.green, bg: STATUS.greenBg };
    case 'ready':
      return { label: 'Ready', fg: STATUS.green, bg: STATUS.greenBg };
    case 'processing':
      return { label: 'Processing', fg: STATUS.amber, bg: STATUS.amberBg, pulse: true };
    case 'queued':
      return { label: 'Queued', fg: STATUS.amber, bg: STATUS.amberBg, pulse: true };
    case 'publishing':
      return { label: 'Publishing', fg: STATUS.amber, bg: STATUS.amberBg, pulse: true };
    case 'inspecting':
      return { label: 'Inspecting', fg: STATUS.amber, bg: STATUS.amberBg, pulse: true };
    case 'failed':
      return { label: 'Failed', fg: STATUS.red, bg: STATUS.redBg };
    case 'publish_failed':
      return { label: 'Publish failed', fg: STATUS.red, bg: STATUS.redBg };
    case 'cancelled':
      return { label: 'Cancelled', fg: C.t3, bg: C.pill };
    case 'uploaded':
      return { label: 'Uploaded', fg: C.t3, bg: C.pill };
    default:
      return { label: String(status), fg: C.t3, bg: C.pill };
  }
}

export const StatusPill: React.FC<{ C: C; status: AnyStatus; size?: 'sm' | 'md' }> = ({
  C,
  status,
  size = 'md',
}) => {
  const tone = statusTone(status, C);
  const dot = size === 'sm' ? 6 : 7;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        background: tone.bg,
        border: `1px solid ${tone.fg}`,
        borderRadius: 5,
        padding: size === 'sm' ? '1px 7px' : '2px 8px',
        fontSize: size === 'sm' ? 10 : 11,
        fontWeight: 600,
        color: tone.fg,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        className={tone.pulse ? 'rf-pulse' : undefined}
        style={{
          width: dot,
          height: dot,
          borderRadius: '50%',
          background: tone.fg,
          flexShrink: 0,
        }}
      />
      {tone.label}
    </span>
  );
};
