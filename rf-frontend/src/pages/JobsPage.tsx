import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Ban, ListChecks } from 'lucide-react';
import { type C } from '../design-system/tokens';
import { useTheme } from '../hooks/useTheme';
import { rf } from '../services/rasterforge';
import { ACTIVE_JOB_STATUSES, type ProcessingJob } from '../types/rasterforge';
import { StatusPill } from '../components/rf/StatusPill';
import { formatDuration, formatRelative } from '../components/rf/format';
import { Button, Card, EmptyState, Notice, ProgressBar, Spinner } from '../components/rf/ui';

/* ============================================================================
 * JobsPage — every processing run, so a failure is never invisible.
 * ========================================================================== */

const TH: React.FC<{ C: C; children: React.ReactNode }> = ({ C, children }) => (
  <th
    style={{
      textAlign: 'left',
      fontSize: 10,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: C.t3,
      padding: '0 12px 12px',
      whiteSpace: 'nowrap',
    }}
  >
    {children}
  </th>
);

const JobsPage: React.FC = () => {
  const { C } = useTheme();
  const navigate = useNavigate();

  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setJobs(await rf.listJobs(200));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load jobs.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const hasActive = jobs.some((j) => ACTIVE_JOB_STATUSES.includes(j.status));
  useEffect(() => {
    if (!hasActive) return;
    const id = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(id);
  }, [hasActive, load]);

  const cancel = useCallback(
    async (jobId: string) => {
      try {
        await rf.cancelJob(jobId);
        await load();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not cancel the job.');
      }
    },
    [load],
  );

  const td: React.CSSProperties = {
    fontSize: 12,
    color: C.t2,
    padding: '12px',
    borderTop: `1px solid ${C.b}`,
    whiteSpace: 'nowrap',
  };

  return (
    <div className="rf-page" style={{ background: C.main }}>
      <div className="rf-container">
        <h1
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: '-0.02em',
            color: C.t1,
            marginBottom: 24,
          }}
        >
          Jobs
        </h1>

        {error && (
          <div style={{ marginBottom: 16 }}>
            <Notice C={C} tone="error" title="Job list unavailable">
              {error}
            </Notice>
          </div>
        )}

        <Card C={C} padding={16}>
          {loading ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', color: C.t3, fontSize: 13 }}>
              <Spinner size={14} /> Loading…
            </div>
          ) : jobs.length === 0 ? (
            <EmptyState C={C} icon={ListChecks} title="No jobs yet">
              Start tile generation from a dataset to see it here.
            </EmptyState>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 820 }}>
                <thead>
                  <tr>
                    <TH C={C}>Dataset</TH>
                    <TH C={C}>Status</TH>
                    <TH C={C}>Progress</TH>
                    <TH C={C}>Step</TH>
                    <TH C={C}>Zoom</TH>
                    <TH C={C}>Duration</TH>
                    <TH C={C}>Started</TH>
                    <TH C={C}> </TH>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => (
                    <tr
                      key={j.id}
                      className="rf-row-hover"
                      onMouseEnter={(e) => (e.currentTarget.style.background = C.row)}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                    >
                      <td
                        style={{ ...td, color: C.t1, fontWeight: 600, cursor: 'pointer', maxWidth: 220 }}
                        onClick={() => navigate(`/datasets/${j.dataset_id}`)}
                      >
                        <div
                          style={{
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {j.dataset_name ?? j.dataset_id}
                        </div>
                        {j.error_message && (
                          <div
                            style={{
                              fontSize: 10,
                              color: C.t3,
                              fontWeight: 400,
                              maxWidth: 200,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                            }}
                          >
                            {j.error_message}
                          </div>
                        )}
                      </td>
                      <td style={td}>
                        <StatusPill C={C} status={j.status} size="sm" />
                      </td>
                      <td style={{ ...td, minWidth: 120 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ flex: 1 }}>
                            <ProgressBar C={C} percent={j.progress} height={4} />
                          </div>
                          <span style={{ fontSize: 11, color: C.t3, minWidth: 30 }}>
                            {j.progress}%
                          </span>
                        </div>
                      </td>
                      <td style={{ ...td, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {j.current_step ?? '—'}
                      </td>
                      <td style={td}>
                        {j.params ? `${j.params.min_zoom}–${j.params.max_zoom}` : '—'}
                      </td>
                      <td style={td}>{formatDuration(j.duration_seconds)}</td>
                      <td style={td}>{formatRelative(j.started_at ?? j.created_at)}</td>
                      <td style={td}>
                        {ACTIVE_JOB_STATUSES.includes(j.status) && (
                          <Button C={C} variant="ghost" icon={Ban} onClick={() => void cancel(j.id)}>
                            Cancel
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};

export default JobsPage;
