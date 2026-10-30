import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Ban,
  Download,
  FileJson,
  FileImage,
  Play,
  RefreshCw,
  Trash2,
  UploadCloud,
} from 'lucide-react';
import { NODATA_MODES, RESAMPLING_METHODS, TILE_CONFIG, ZOOM_LIMITS } from '../config/config';
import { STATUS } from '../design-system/tokens';
import { useTheme } from '../hooks/useTheme';
import { useJobPolling } from '../hooks/useJobPolling';
import { rf } from '../services/rasterforge';
import type {
  Dataset,
  NoDataMode,
  ResamplingMethod,
} from '../types/rasterforge';
import { JobProgress } from '../components/rf/JobProgress';
import { LogViewer } from '../components/rf/LogViewer';
import { MetadataPanel } from '../components/rf/MetadataPanel';
import { StatusPill } from '../components/rf/StatusPill';
import { TilePreviewMap } from '../components/rf/TilePreviewMap';
import { TileUrlBox } from '../components/rf/TileUrlBox';
import { formatBytes, formatDateTime, formatInt } from '../components/rf/format';
import {
  Button,
  Card,
  Field,
  KeyValue,
  Notice,
  NumberInput,
  PanelTitle,
  Pill,
  SectionLabel,
  Select,
  Spinner,
} from '../components/rf/ui';

/* ============================================================================
 * DatasetDetailPage — one route, four states, driven by dataset.status:
 *
 *   ready           -> analysis + configuration
 *   queued/…        -> live processing
 *   completed       -> map preview, tile URL, downloads
 *   failed          -> human error + technical log
 *   publish_failed  -> "processed, not published" with a publish-only retry
 *
 * That last state is the point of separating publishing from processing: a
 * cheap failure must never force a re-run of the expensive part.
 * ========================================================================== */

const ACTIVE = ['queued', 'processing', 'publishing'];

const DatasetDetailPage: React.FC = () => {
  const { C } = useTheme();
  const { id = '' } = useParams();
  const navigate = useNavigate();

  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showLog, setShowLog] = useState(false);

  // Configuration form
  const [minZoom, setMinZoom] = useState(14);
  const [maxZoom, setMaxZoom] = useState(18);
  const [resampling, setResampling] = useState<ResamplingMethod>('bilinear');
  const [nodataMode, setNodataMode] = useState<NoDataMode>('auto');
  const [zoomTouched, setZoomTouched] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const next = await rf.getDataset(id);
      setDataset(next);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load this dataset.');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  // Default the max zoom to the raster's native resolution, but never
  // overwrite a choice the user has already made.
  const recommended = dataset?.metadata?.recommended_max_zoom ?? null;
  useEffect(() => {
    if (!zoomTouched && recommended !== null) setMaxZoom(recommended);
  }, [recommended, zoomTouched]);

  const activeJob = dataset?.latest_job && ACTIVE.includes(dataset.latest_job.status)
    ? dataset.latest_job
    : null;

  const onJobFinished = useCallback(() => {
    void load();
  }, [load]);

  const { job: liveJob } = useJobPolling(activeJob?.id ?? null, {
    onFinished: onJobFinished,
    enabled: Boolean(activeJob),
  });

  const job = liveJob ?? dataset?.latest_job ?? null;

  const startJob = useCallback(async () => {
    if (!dataset) return;
    setBusy(true);
    setActionError(null);
    try {
      await rf.createTileJob(dataset.id, {
        min_zoom: minZoom,
        max_zoom: maxZoom,
        resampling,
        nodata_mode: nodataMode,
      });
      await load();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not start the job.');
    } finally {
      setBusy(false);
    }
  }, [dataset, minZoom, maxZoom, resampling, nodataMode, load]);

  const cancelJob = useCallback(async () => {
    if (!job) return;
    setBusy(true);
    try {
      await rf.cancelJob(job.id);
      await load();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not cancel the job.');
    } finally {
      setBusy(false);
    }
  }, [job, load]);

  const retryPublish = useCallback(async () => {
    if (!dataset) return;
    setBusy(true);
    setActionError(null);
    try {
      await rf.publish(dataset.id);
      await load();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Publishing failed again.');
    } finally {
      setBusy(false);
    }
  }, [dataset, load]);

  const remove = useCallback(async () => {
    if (!dataset) return;
    if (!window.confirm(`Delete "${dataset.display_name}" and all of its tiles? This cannot be undone.`)) {
      return;
    }
    setBusy(true);
    try {
      await rf.deleteDataset(dataset.id);
      navigate('/datasets');
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not delete the dataset.');
      setBusy(false);
    }
  }, [dataset, navigate]);

  const download = useCallback(
    async (kind: 'source' | 'tiles' | 'working' | 'metadata') => {
      if (!dataset) return;
      setActionError(null);
      try {
        if (kind === 'source') await rf.downloadSource(dataset.id, dataset.slug);
        if (kind === 'tiles') await rf.downloadTiles(dataset.id, dataset.slug);
        if (kind === 'working') await rf.downloadWorking(dataset.id, dataset.slug);
        if (kind === 'metadata') await rf.downloadMetadata(dataset.id, dataset.slug);
      } catch (e) {
        setActionError(e instanceof Error ? e.message : 'Download failed.');
      }
    },
    [dataset],
  );

  const sampleTileUrl = useMemo(() => {
    const out = dataset?.published_output;
    const bounds = dataset?.metadata?.bounds;
    if (!out?.public_url_template || !bounds) return null;
    // Centre tile at the pyramid's minimum zoom — always present if anything is.
    const z = out.min_zoom;
    const lon = (bounds[0] + bounds[2]) / 2;
    const lat = (bounds[1] + bounds[3]) / 2;
    const n = 2 ** z;
    const x = Math.floor(((lon + 180) / 360) * n);
    const latRad = (lat * Math.PI) / 180;
    const y = Math.floor(
      ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n,
    );
    return out.public_url_template
      .replace('{z}', String(z))
      .replace('{x}', String(x))
      .replace('{y}', String(y));
  }, [dataset]);

  /* ── render ────────────────────────────────────────────────────────────── */

  if (loading) {
    return (
      <div className="rf-page" style={{ background: C.main }}>
        <div className="rf-container" style={{ display: 'flex', gap: 8, alignItems: 'center', color: C.t3 }}>
          <Spinner size={14} /> Loading dataset…
        </div>
      </div>
    );
  }

  if (error || !dataset) {
    return (
      <div className="rf-page" style={{ background: C.main }}>
        <div className="rf-container">
          <Notice C={C} tone="error" title="Dataset unavailable">
            {error ?? 'Not found.'}
          </Notice>
        </div>
      </div>
    );
  }

  const meta = dataset.metadata;
  const output = dataset.published_output;
  const isActive = ACTIVE.includes(dataset.status);
  const overNative = recommended !== null && maxZoom > recommended;
  const canConfigure = dataset.status === 'ready' || dataset.status === 'failed' || dataset.status === 'cancelled';

  return (
    <div className="rf-page" style={{ background: C.main }}>
      <div className="rf-container">
        {/* Header */}
        <button
          onClick={() => navigate('/datasets')}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            background: 'transparent',
            border: 'none',
            color: C.t3,
            fontSize: 12,
            cursor: 'pointer',
            padding: 0,
            marginBottom: 16,
          }}
        >
          <ArrowLeft size={14} strokeWidth={1.8} /> All datasets
        </button>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            marginBottom: 8,
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
            {dataset.display_name}
          </h1>
          <StatusPill C={C} status={dataset.status} />
          <Pill C={C}>{dataset.slug}</Pill>
        </div>
        <p style={{ fontSize: 12, color: C.t3, marginBottom: 24 }}>
          {dataset.source_filename} · {formatBytes(dataset.source_size)} · uploaded{' '}
          {formatDateTime(dataset.created_at)}
        </p>

        {actionError && (
          <div style={{ marginBottom: 16 }}>
            <Notice C={C} tone="error" title="Action failed">
              {actionError}
            </Notice>
          </div>
        )}

        {/* ── FAILED ─────────────────────────────────────────────────────── */}
        {dataset.status === 'failed' && job?.error_message && (
          <div style={{ marginBottom: 24 }}>
            <Notice
              C={C}
              tone="error"
              title="Processing failed"
              action={
                <Button C={C} variant="secondary" onClick={() => setShowLog((v) => !v)}>
                  {showLog ? 'Hide log' : 'View technical log'}
                </Button>
              }
            >
              {job.error_message}
            </Notice>
          </div>
        )}

        {/* ── PUBLISH FAILED ─────────────────────────────────────────────── */}
        {dataset.status === 'publish_failed' && (
          <div style={{ marginBottom: 24 }}>
            <Notice
              C={C}
              tone="warn"
              title="Processing completed · Publishing failed"
              action={
                <Button C={C} variant="primary" icon={UploadCloud} onClick={retryPublish} disabled={busy}>
                  Retry publish
                </Button>
              }
            >
              The tiles generated successfully and are still on disk. Only the publishing step
              failed, so retrying it will not re-run the raster processing.
              {dataset.error_message && (
                <div style={{ marginTop: 8, color: C.t3 }}>{dataset.error_message}</div>
              )}
            </Notice>
          </div>
        )}

        {/* ── PROCESSING ─────────────────────────────────────────────────── */}
        {isActive && job && (
          <div style={{ marginBottom: 24 }}>
            <Card C={C}>
              <PanelTitle
                C={C}
                right={
                  <Button C={C} variant="danger" icon={Ban} onClick={cancelJob} disabled={busy}>
                    Cancel
                  </Button>
                }
              >
                Generating XYZ tiles
              </PanelTitle>
              <JobProgress C={C} job={job} />
              <div style={{ marginTop: 16, fontSize: 11, color: C.t3 }}>
                You can close this page. Processing continues on the server.
              </div>
            </Card>

            <div style={{ marginTop: 16 }}>
              <Card C={C}>
                <LogViewer C={C} jobId={job.id} live height={240} />
              </Card>
            </div>
          </div>
        )}

        {/* ── COMPLETED ──────────────────────────────────────────────────── */}
        {dataset.status === 'completed' && output?.public_url_template && (
          <div style={{ marginBottom: 24 }}>
            {/* The stored URL is fixed at publish time. If the server's tile
                host (TILE_PUBLIC_BASE) has moved since, say so instead of
                leaving a dead URL in the Copy box. */}
            {!output.public_url_template.startsWith(`${TILE_CONFIG.PUBLIC_BASE}/`) && (
              <div style={{ marginBottom: 16 }}>
                <Notice
                  C={C}
                  tone="warn"
                  title="Published at a previous tile address"
                  action={
                    <Button C={C} variant="primary" icon={UploadCloud} onClick={retryPublish} disabled={busy}>
                      Re-publish
                    </Button>
                  }
                >
                  The tile host is now {TILE_CONFIG.PUBLIC_BASE}. Re-publishing refreshes the
                  URL and mirrors the tiles to the new host without re-running the processing.
                </Notice>
              </div>
            )}
            <Card C={C}>
              <PanelTitle
                C={C}
                right={
                  <Button C={C} variant="secondary" icon={UploadCloud} onClick={retryPublish} disabled={busy}>
                    Re-publish
                  </Button>
                }
              >
                Preview
              </PanelTitle>
              <TilePreviewMap
                C={C}
                tileUrl={output.public_url_template}
                bounds={meta?.bounds ?? output.bounds ?? null}
                center={meta?.center ?? null}
                minZoom={output.min_zoom}
                maxZoom={output.max_zoom}
              />

              <div style={{ marginTop: 24 }}>
                <SectionLabel C={C}>Tile endpoint</SectionLabel>
                <TileUrlBox C={C} url={output.public_url_template} sampleUrl={sampleTileUrl} />
              </div>

              <div
                style={{
                  marginTop: 24,
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                  gap: 16,
                }}
              >
                <KeyValue stacked C={C} label="Zoom" value={`${output.min_zoom}–${output.max_zoom}`} />
                <KeyValue stacked C={C} label="Format" value={`${output.scheme.toUpperCase()} · ${output.profile}`} />
                <KeyValue stacked C={C} label="Resampling" value={output.resampling} />
                <KeyValue stacked C={C} label="Tiles" value={formatInt(output.tile_count)} />
                <KeyValue stacked C={C} label="Size" value={formatBytes(output.size_bytes)} />
                <KeyValue stacked C={C} label="Published" value={formatDateTime(output.published_at)} />
                <KeyValue
                  stacked
                  C={C}
                  label="NoData"
                  value={output.normalised ? 'Normalised working copy' : 'Source preserved'}
                />
              </div>

              <div style={{ marginTop: 24, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Button C={C} variant="primary" icon={Download} onClick={() => void download('tiles')}>
                  Download tiles
                </Button>
                <Button C={C} icon={FileImage} onClick={() => void download('source')}>
                  Download GeoTIFF
                </Button>
                <Button C={C} icon={FileJson} onClick={() => void download('metadata')}>
                  Metadata
                </Button>
                {output.normalised && (
                  <Button C={C} icon={FileImage} onClick={() => void download('working')}>
                    Cleaned GeoTIFF
                  </Button>
                )}
              </div>
            </Card>
          </div>
        )}

        {/* ── ANALYSIS ───────────────────────────────────────────────────── */}
        {meta && (
          <div style={{ marginBottom: 24 }}>
            <MetadataPanel
              C={C}
              metadata={meta}
              sourceFilename={dataset.source_filename}
              sourceSize={dataset.source_size}
            />
          </div>
        )}

        {/* ── CONFIGURE ──────────────────────────────────────────────────── */}
        {canConfigure && (
          <Card C={C}>
            <PanelTitle C={C}>Generate web tiles</PanelTitle>

            <SectionLabel C={C}>Output</SectionLabel>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 24 }}>
              <Pill C={C} tone="accent">
                XYZ tiles
              </Pill>
              {['Cloud Optimized GeoTIFF', 'MBTiles', 'PMTiles', 'Cesium Terrain'].map((label) => (
                <span
                  key={label}
                  title="Coming later"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    background: C.pill,
                    border: `1px solid ${C.b}`,
                    borderRadius: 5,
                    padding: '2px 8px',
                    fontSize: 11,
                    fontWeight: 500,
                    color: C.t3,
                    opacity: 0.6,
                  }}
                >
                  {label}
                  <span style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    soon
                  </span>
                </span>
              ))}
            </div>

            <SectionLabel C={C}>Zoom</SectionLabel>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                gap: 16,
              }}
            >
              <Field C={C} label="Minimum zoom" htmlFor="rf-minzoom">
                <NumberInput
                  id="rf-minzoom"
                  C={C}
                  value={minZoom}
                  min={ZOOM_LIMITS.MIN}
                  max={ZOOM_LIMITS.MAX}
                  onChange={(v) => {
                    setZoomTouched(true);
                    setMinZoom(v);
                  }}
                />
              </Field>
              <Field
                C={C}
                label="Maximum zoom"
                htmlFor="rf-maxzoom"
                hint={recommended !== null ? `Native recommendation: ${recommended}` : undefined}
              >
                <NumberInput
                  id="rf-maxzoom"
                  C={C}
                  value={maxZoom}
                  min={ZOOM_LIMITS.MIN}
                  max={ZOOM_LIMITS.MAX}
                  onChange={(v) => {
                    setZoomTouched(true);
                    setMaxZoom(v);
                  }}
                />
              </Field>
            </div>

            {overNative && (
              <div style={{ marginBottom: 16 }}>
                <Notice C={C} tone="warn">
                  Zoom {maxZoom} exceeds the source raster's native resolution
                  {meta?.gsd_m ? ` (~${(meta.gsd_m * 100).toFixed(1)} cm/pixel)` : ''}. The extra
                  levels will be upscaled, not sharper. You can still generate them.
                </Notice>
              </div>
            )}
            {minZoom > maxZoom && (
              <div style={{ marginBottom: 16 }}>
                <Notice C={C} tone="error">
                  Minimum zoom cannot be greater than maximum zoom.
                </Notice>
              </div>
            )}

            <SectionLabel C={C}>Raster handling</SectionLabel>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 16,
              }}
            >
              <Field
                C={C}
                label="NoData"
                htmlFor="rf-nodata"
                hint={
                  meta?.nodata_warning
                    ? 'Auto will write a NoData-stripped working copy for this raster.'
                    : 'Auto tiles the source directly for this raster.'
                }
              >
                <Select
                  id="rf-nodata"
                  C={C}
                  value={nodataMode}
                  onChange={(v) => setNodataMode(v as NoDataMode)}
                  options={NODATA_MODES}
                />
              </Field>
              <Field C={C} label="Resampling" htmlFor="rf-resampling">
                <Select
                  id="rf-resampling"
                  C={C}
                  value={resampling}
                  onChange={(v) => setResampling(v as ResamplingMethod)}
                  options={RESAMPLING_METHODS}
                />
              </Field>
            </div>

            <div
              style={{
                marginTop: 8,
                padding: 16,
                background: C.inp,
                borderRadius: 8,
                border: `1px solid ${C.b}`,
              }}
            >
              <SectionLabel C={C}>Summary</SectionLabel>
              <KeyValue C={C} label="Dataset" value={dataset.display_name} />
              <KeyValue
                C={C}
                label="CRS"
                value={
                  meta?.epsg
                    ? `EPSG:${meta.epsg} → EPSG:3857 (Web Mercator)`
                    : 'Unknown → EPSG:3857'
                }
              />
              <KeyValue C={C} label="Output" value="XYZ tiles · mercator profile" />
              <KeyValue C={C} label="Zoom" value={`${minZoom}–${maxZoom}`} />
              <KeyValue
                C={C}
                label="NoData handling"
                value={NODATA_MODES.find((m) => m.value === nodataMode)?.label ?? nodataMode}
              />
              <KeyValue C={C} label="Tile URL" value={`${TILE_CONFIG.PUBLIC_BASE}/${dataset.slug}/{z}/{x}/{y}.png`} />
            </div>

            <div style={{ marginTop: 24, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Button
                C={C}
                variant="primary"
                icon={Play}
                onClick={startJob}
                disabled={busy || minZoom > maxZoom || !meta}
              >
                {busy ? 'Starting…' : 'Generate tiles'}
              </Button>
              <Button C={C} icon={RefreshCw} onClick={() => void rf.reinspect(dataset.id).then(load)}>
                Re-inspect
              </Button>
              <Button C={C} icon={FileImage} onClick={() => void download('source')}>
                Download source
              </Button>
              <div style={{ marginLeft: 'auto' }}>
                <Button C={C} variant="danger" icon={Trash2} onClick={remove} disabled={busy}>
                  Delete
                </Button>
              </div>
            </div>
          </Card>
        )}

        {/* ── LOG ────────────────────────────────────────────────────────── */}
        {showLog && job && (
          <div style={{ marginTop: 24 }}>
            <Card C={C}>
              <LogViewer C={C} jobId={job.id} height={360} />
            </Card>
          </div>
        )}

        {/* Completed datasets keep a delete affordance too. */}
        {dataset.status === 'completed' && (
          <div style={{ marginTop: 24, display: 'flex', gap: 8 }}>
            <Button C={C} onClick={() => setShowLog((v) => !v)}>
              {showLog ? 'Hide processing log' : 'View processing log'}
            </Button>
            <div style={{ marginLeft: 'auto' }}>
              <Button C={C} variant="danger" icon={Trash2} onClick={remove} disabled={busy}>
                Delete dataset
              </Button>
            </div>
          </div>
        )}

        {dataset.status === 'completed' && (
          <div style={{ marginTop: 16, fontSize: 11, color: STATUS.green }}>
            Published — this URL is live and ready to paste into another application.
          </div>
        )}
      </div>
    </div>
  );
};

export default DatasetDetailPage;
