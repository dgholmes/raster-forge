import React, { useEffect, useState } from 'react';
import { Check, Circle, Loader2, X } from 'lucide-react';
import { STATUS, type C } from '../../design-system/tokens';
import type { ProcessingJob } from '../../types/rasterforge';
import { formatDuration } from './format';
import { ProgressBar, SectionLabel } from './ui';

/* ============================================================================
 * JobProgress — the processing screen's live view.
 *
 * The step list mirrors the pipeline's real stages, and each one is derived
 * from the job's reported progress rather than guessed at, so the checklist
 * and the bar can never disagree.
 * ========================================================================== */

interface Step {
  key: string;
  label: string;
  /** Progress at which this step is considered finished. */
  doneAt: number;
}

const STEPS: Step[] = [
  { key: 'upload', label: 'Upload complete', doneAt: 0 },
  { key: 'inspect', label: 'Metadata inspected', doneAt: 2 },
  { key: 'normalise', label: 'Raster normalised', doneAt: 15 },
  { key: 'tiles', label: 'Generating tiles', doneAt: 95 },
  { key: 'validate', label: 'Validating output', doneAt: 97 },
  { key: 'publish', label: 'Publishing', doneAt: 99 },
  { key: 'complete', label: 'Complete', doneAt: 100 },
];

type StepState = 'done' | 'active' | 'pending' | 'failed';

function stepStates(job: ProcessingJob): Record<string, StepState> {
  const out: Record<string, StepState> = {};
  const stopped = job.status === 'failed' || job.status === 'cancelled';
  const finished = job.status === 'completed';
  let markedCurrent = false;

  for (const step of STEPS) {
    if (finished || job.progress >= step.doneAt) {
      out[step.key] = 'done';
    } else if (!markedCurrent) {
      // The first unreached step is where the job is now — or where it died.
      out[step.key] = stopped ? 'failed' : 'active';
      markedCurrent = true;
    } else {
      out[step.key] = 'pending';
    }
  }
  return out;
}

const StepIcon: React.FC<{ C: C; state: StepState }> = ({ C, state }) => {
  const size = 15;
  if (state === 'done') return <Check size={size} color={STATUS.green} strokeWidth={2.2} />;
  if (state === 'failed') return <X size={size} color={STATUS.red} strokeWidth={2.2} />;
  if (state === 'active')
    return <Loader2 size={size} color={STATUS.amber} strokeWidth={2} className="rf-spin" />;
  return <Circle size={size} color={C.t3} strokeWidth={1.6} />;
};

export const PipelineSteps: React.FC<{ C: C; job: ProcessingJob }> = ({ C, job }) => {
  const states = stepStates(job);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {STEPS.map((step) => {
        const state = states[step.key];
        return (
          <div key={step.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <StepIcon C={C} state={state} />
            <span
              style={{
                fontSize: 13,
                fontWeight: state === 'active' ? 500 : 400,
                color:
                  state === 'pending' ? C.t3 : state === 'failed' ? STATUS.red : C.t1,
              }}
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
};

/** Elapsed time that keeps ticking while the job runs. */
function useElapsed(job: ProcessingJob): number | null {
  const [, force] = useState(0);
  const active = job.status === 'queued' || job.status === 'processing' || job.status === 'publishing';

  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => force((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [active]);

  if (job.duration_seconds !== null && !active) return job.duration_seconds;
  if (!job.started_at) return null;
  return (Date.now() - new Date(job.started_at).getTime()) / 1000;
}

export const JobProgress: React.FC<{ C: C; job: ProcessingJob }> = ({ C, job }) => {
  const elapsed = useElapsed(job);

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}
      >
        <div style={{ fontSize: 24, fontWeight: 700, color: C.t1, letterSpacing: '-0.02em' }}>
          {job.progress}%
        </div>
        <div style={{ fontSize: 12, color: C.t3, fontVariantNumeric: 'tabular-nums' }}>
          {formatDuration(elapsed)}
        </div>
      </div>

      <ProgressBar C={C} percent={job.progress} />

      <div style={{ fontSize: 13, color: C.t2, marginTop: 12, minHeight: 20 }}>
        {job.current_step || 'Waiting…'}
      </div>

      <div style={{ marginTop: 24 }}>
        <SectionLabel C={C}>Pipeline</SectionLabel>
        <PipelineSteps C={C} job={job} />
      </div>
    </div>
  );
};
