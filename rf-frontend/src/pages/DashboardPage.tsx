import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  CheckCircle2,
  HardDrive,
  Layers,
  type LucideIcon,
} from 'lucide-react';
import { STATUS, type C } from '../design-system/tokens';
import { useTheme } from '../hooks/useTheme';
import { rf } from '../services/rasterforge';
import { apiService } from '../services/api';
import type { Dataset } from '../types/rasterforge';
import { StatusPill } from '../components/rf/StatusPill';
import { UploadZone } from '../components/rf/UploadZone';
import { formatBytes, formatGsd, formatRelative } from '../components/rf/format';
import { Card, EmptyState, Notice, PanelTitle, SectionLabel, Spinner } from '../components/rf/ui';

/* ============================================================================
 * DashboardPage — the landing screen: what exists, what is running, and the
 * one action that matters (upload a GeoTIFF).
 * ========================================================================== */

const StatTile: React.FC<{
  C: C;
  icon: LucideIcon;
  label: string;
  value: string;
  hint?: string;
  tone?: string;
}> = ({ C, icon: Icon, label, value, hint, tone }) => (
  <Card C={C} padding={16}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
      <Icon size={15} color={tone ?? C.t3} strokeWidth={1.7} />
      <span
        style={{
          fontSize: 10,
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          color: C.t3,
        }}
      >
        {label}
      </span>
    </div>
    <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-0.02em', color: C.t1 }}>
      {value}
    </div>
    {hint && <div style={{ fontSize: 11, color: C.t3, marginTop: 4 }}>{hint}</div>}
  </Card>
);

const DashboardPage: React.FC = () => {
  const { C } = useTheme();
  const navigate = useNavigate();

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [freeBytes, setFreeBytes] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await rf.listDatasets();
      setDatasets(rows);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load datasets.');
    } finally {
      setLoading(false);
    }
    try {
      const stats = await apiService.get<{ free_bytes: number }>('/api/datasets/storage-stats');
      setFreeBytes(stats.free_bytes);
    } catch {
      /* storage stats are informational only */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Refresh while anything is in flight, so the dashboard reflects reality.
  const hasActive = datasets.some((d) =>
    ['queued', 'processing', 'publishing', 'inspecting'].includes(d.status),
  );
  useEffect(() => {
    if (!hasActive) return;
    const id = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(id);
  }, [hasActive, load]);

  const handleUpload = useCallback(
    async (file: File, displayName: string, onProgress: (p: number) => void) => {
      const created = await rf.uploadDataset(file, displayName, (percent) => onProgress(percent));
      navigate(`/datasets/${created.id}`);
    },
    [navigate],
  );

  const published = datasets.filter((d) => d.status === 'completed').length;
  const running = datasets.filter((d) =>
    ['queued', 'processing', 'publishing'].includes(d.status),
  ).length;
  const totalTiles = datasets.reduce((sum, d) => sum + (d.published_output?.size_bytes ?? 0), 0);
  const recent = datasets.slice(0, 6);

  return (
    <div className="rf-page" style={{ background: C.main }}>
      <div className="rf-container">
        <h1
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: '-0.02em',
            color: C.t1,
            marginBottom: 4,
          }}
        >
          Dashboard
        </h1>
        <p style={{ fontSize: 13, color: C.t3, marginBottom: 24 }}>
          Turn a GeoTIFF into published XYZ tiles without leaving the browser.
        </p>

        {error && (
          <div style={{ marginBottom: 16 }}>
            <Notice C={C} tone="error" title="Could not reach the backend">
              {error}
            </Notice>
          </div>
        )}

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 16,
            marginBottom: 24,
          }}
        >
          <StatTile C={C} icon={Layers} label="Datasets" value={String(datasets.length)} />
          <StatTile
            C={C}
            icon={CheckCircle2}
            label="Published"
            value={String(published)}
            tone={STATUS.green}
          />
          <StatTile
            C={C}
            icon={Activity}
            label="Running jobs"
            value={String(running)}
            tone={running > 0 ? STATUS.amber : undefined}
          />
          <StatTile
            C={C}
            icon={HardDrive}
            label="Tile storage"
            value={formatBytes(totalTiles)}
            hint={freeBytes !== null ? `${formatBytes(freeBytes)} free on disk` : undefined}
          />
        </div>

        <div style={{ marginBottom: 24 }}>
          <SectionLabel C={C}>New dataset</SectionLabel>
          <UploadZone C={C} onUpload={handleUpload} />
        </div>

        <Card C={C}>
          <PanelTitle C={C} icon={Layers}>
            Recent datasets
          </PanelTitle>

          {loading ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', color: C.t3, fontSize: 13 }}>
              <Spinner size={14} /> Loading…
            </div>
          ) : recent.length === 0 ? (
            <EmptyState C={C} icon={Layers} title="No datasets yet">
              Upload a GeoTIFF above to get started.
            </EmptyState>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {recent.map((d, i) => (
                <button
                  key={d.id}
                  className="rf-row-hover rf-card-in"
                  onClick={() => navigate(`/datasets/${d.id}`)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '12px 12px',
                    background: 'transparent',
                    border: 'none',
                    borderTop: i === 0 ? 'none' : `1px solid ${C.b}`,
                    borderRadius: 7,
                    cursor: 'pointer',
                    textAlign: 'left',
                    width: '100%',
                    animationDelay: `${i * 24}ms`,
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = C.row)}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: C.t1,
                        letterSpacing: '-0.01em',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {d.display_name}
                    </div>
                    <div style={{ fontSize: 11, color: C.t3, marginTop: 2 }}>
                      {d.metadata?.epsg ? `EPSG:${d.metadata.epsg}` : 'No CRS'}
                      {d.metadata?.gsd_m ? ` · ${formatGsd(d.metadata.gsd_m)}` : ''}
                      {` · ${formatBytes(d.source_size)}`}
                      {` · ${formatRelative(d.created_at)}`}
                    </div>
                  </div>
                  <StatusPill C={C} status={d.status} size="sm" />
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};

export default DashboardPage;
