import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layers, Search } from 'lucide-react';
import { type C } from '../design-system/tokens';
import { useTheme } from '../hooks/useTheme';
import { rf } from '../services/rasterforge';
import type { Dataset } from '../types/rasterforge';
import { StatusPill } from '../components/rf/StatusPill';
import { formatBytes, formatDimensions, formatGsd, formatRelative } from '../components/rf/format';
import { Card, EmptyState, FONT, Notice, Spinner } from '../components/rf/ui';

/* ============================================================================
 * DatasetsPage — every dataset, with the fields an operator scans for.
 * ========================================================================== */

const TH: React.FC<{ C: C; children: React.ReactNode; align?: 'left' | 'right' }> = ({
  C,
  children,
  align = 'left',
}) => (
  <th
    style={{
      textAlign: align,
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

const DatasetsPage: React.FC = () => {
  const { C } = useTheme();
  const navigate = useNavigate();

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const load = useCallback(async () => {
    try {
      setDatasets(await rf.listDatasets());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load datasets.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const hasActive = datasets.some((d) =>
    ['queued', 'processing', 'publishing', 'inspecting'].includes(d.status),
  );
  useEffect(() => {
    if (!hasActive) return;
    const id = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(id);
  }, [hasActive, load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return datasets;
    return datasets.filter(
      (d) =>
        d.display_name.toLowerCase().includes(q) ||
        d.slug.toLowerCase().includes(q) ||
        d.source_filename.toLowerCase().includes(q),
    );
  }, [datasets, query]);

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
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            marginBottom: 24,
            flexWrap: 'wrap',
          }}
        >
          <h1
            style={{
              fontSize: 22,
              fontWeight: 700,
              letterSpacing: '-0.02em',
              color: C.t1,
              margin: 0,
            }}
          >
            Datasets
          </h1>
          <div style={{ marginLeft: 'auto', position: 'relative' }}>
            <Search
              size={14}
              color={C.t3}
              strokeWidth={1.7}
              style={{ position: 'absolute', left: 10, top: 9 }}
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search datasets"
              style={{
                height: 32,
                width: 240,
                padding: '0 12px 0 30px',
                background: C.inp,
                border: `1px solid ${C.inpB}`,
                borderRadius: 7,
                color: C.t1,
                fontFamily: FONT,
                fontSize: 13,
                outline: 'none',
              }}
            />
          </div>
        </div>

        {error && (
          <div style={{ marginBottom: 16 }}>
            <Notice C={C} tone="error" title="Could not load datasets">
              {error}
            </Notice>
          </div>
        )}

        <Card C={C} padding={16}>
          {loading ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', color: C.t3, fontSize: 13 }}>
              <Spinner size={14} /> Loading…
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState C={C} icon={Layers} title={query ? 'No matches' : 'No datasets yet'}>
              {query ? 'Try a different search.' : 'Upload a GeoTIFF from the dashboard.'}
            </EmptyState>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                <thead>
                  <tr>
                    <TH C={C}>Name</TH>
                    <TH C={C}>Status</TH>
                    <TH C={C}>CRS</TH>
                    <TH C={C}>Dimensions</TH>
                    <TH C={C}>GSD</TH>
                    <TH C={C}>Zoom</TH>
                    <TH C={C} align="right">Source</TH>
                    <TH C={C} align="right">Tiles</TH>
                    <TH C={C}>Owner</TH>
                    <TH C={C}>Created</TH>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((d) => {
                    const out = d.published_output;
                    return (
                      <tr
                        key={d.id}
                        className="rf-row-hover"
                        onClick={() => navigate(`/datasets/${d.id}`)}
                        style={{ cursor: 'pointer' }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = C.row)}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                      >
                        <td style={{ ...td, color: C.t1, fontWeight: 600, maxWidth: 240 }}>
                          <div
                            style={{
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {d.display_name}
                          </div>
                          <div style={{ fontSize: 10, color: C.t3, fontWeight: 400 }}>{d.slug}</div>
                        </td>
                        <td style={td}>
                          <StatusPill C={C} status={d.status} size="sm" />
                        </td>
                        <td style={td}>{d.metadata?.epsg ? `EPSG:${d.metadata.epsg}` : '—'}</td>
                        <td style={td}>
                          {formatDimensions(d.metadata?.width ?? null, d.metadata?.height ?? null)}
                        </td>
                        <td style={td}>{formatGsd(d.metadata?.gsd_m ?? null)}</td>
                        <td style={td}>{out ? `${out.min_zoom}–${out.max_zoom}` : '—'}</td>
                        <td style={{ ...td, textAlign: 'right' }}>{formatBytes(d.source_size)}</td>
                        <td style={{ ...td, textAlign: 'right' }}>
                          {out ? formatBytes(out.size_bytes) : '—'}
                        </td>
                        <td style={td}>{d.owner ?? '—'}</td>
                        <td style={td}>{formatRelative(d.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};

export default DatasetsPage;
