import React, { useCallback, useRef, useState } from 'react';
import { UploadCloud, X, FileImage } from 'lucide-react';
import { type C } from '../../design-system/tokens';
import { formatBytes } from './format';
import { Button, FONT, ProgressBar } from './ui';

/* ============================================================================
 * UploadZone — drag-and-drop GeoTIFF intake.
 *
 * Follows the design system's Upload Zone recipe exactly: 1.5px dashed accent
 * at 40% opacity, radius 10, a 3%-accent fill, brightening on drag-over.
 *
 * Client-side extension checking is a courtesy, not a control: the server
 * re-checks the extension, the magic bytes, and whether gdalinfo can open it.
 * ========================================================================== */

const ACCEPT = '.tif,.tiff';

interface Props {
  C: C;
  /** Receives a progress callback so the zone can render real upload progress
   *  — these files are gigabytes and a spinner alone is not enough feedback. */
  onUpload: (
    file: File,
    displayName: string,
    onProgress: (percent: number) => void,
  ) => Promise<void>;
  disabled?: boolean;
}

export const UploadZone: React.FC<Props> = ({ C, onUpload, disabled }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [busy, setBusy] = useState(false);
  const [percent, setPercent] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const accept = useCallback((picked: File | null | undefined) => {
    setError(null);
    if (!picked) return;
    if (!/\.tiff?$/i.test(picked.name)) {
      setError('RasterForge accepts .tif and .tiff files.');
      return;
    }
    setFile(picked);
    setDisplayName(picked.name.replace(/\.tiff?$/i, ''));
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (disabled) return;
      accept(e.dataTransfer.files?.[0]);
    },
    [accept, disabled],
  );

  const start = useCallback(async () => {
    if (!file) return;
    setBusy(true);
    setPercent(0);
    setError(null);
    try {
      await onUpload(file, displayName.trim() || file.name, setPercent);
      setFile(null);
      setDisplayName('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed.');
    } finally {
      setBusy(false);
    }
  }, [file, displayName, onUpload]);

  // -- selected state ----------------------------------------------------
  if (file) {
    return (
      <div
        style={{
          border: `1.5px solid ${C.cardB}`,
          borderRadius: 10,
          background: C.card,
          padding: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <FileImage size={20} color={C.accent} strokeWidth={1.6} />
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
              {file.name}
            </div>
            <div style={{ fontSize: 11, color: C.t3, marginTop: 2 }}>{formatBytes(file.size)}</div>
          </div>
          {!busy && (
            <button
              onClick={() => {
                setFile(null);
                setError(null);
              }}
              title="Remove"
              style={{
                width: 28,
                height: 28,
                borderRadius: 6,
                border: 'none',
                background: 'transparent',
                color: C.t3,
                cursor: 'pointer',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <X size={15} strokeWidth={1.8} />
            </button>
          )}
        </div>

        <div style={{ marginTop: 16 }}>
          <label
            htmlFor="rf-upload-name"
            style={{ display: 'block', fontSize: 12, color: C.t2, marginBottom: 8 }}
          >
            Dataset name
          </label>
          <input
            id="rf-upload-name"
            value={displayName}
            disabled={busy}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="e.g. 메인행사장"
            style={{
              width: '100%',
              height: 32,
              padding: '0 12px',
              background: C.inp,
              border: `1px solid ${C.inpB}`,
              borderRadius: 7,
              color: C.t1,
              fontFamily: FONT,
              fontSize: 13,
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {busy && (
          <div style={{ marginTop: 16 }}>
            <ProgressBar C={C} percent={percent} />
            <div style={{ fontSize: 11, color: C.t3, marginTop: 8 }}>
              {percent < 100
                ? `Uploading… ${percent}%`
                : 'Upload complete — inspecting the raster…'}
            </div>
          </div>
        )}

        {error && (
          <div style={{ marginTop: 12, fontSize: 12, color: '#ff453a' }}>{error}</div>
        )}

        <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
          <Button C={C} variant="primary" icon={UploadCloud} onClick={start} disabled={busy}>
            {busy ? 'Uploading…' : 'Upload GeoTIFF'}
          </Button>
        </div>
      </div>
    );
  }

  // -- empty state -------------------------------------------------------
  return (
    <>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
        }}
        style={{
          border: `1.5px dashed ${dragOver ? 'rgba(10,132,255,0.65)' : 'rgba(10,132,255,0.40)'}`,
          borderRadius: 10,
          background: dragOver ? 'rgba(10,132,255,0.08)' : 'rgba(10,132,255,0.03)',
          padding: '32px 20px',
          textAlign: 'center',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.5 : 1,
          transition: 'background 0.15s ease, border-color 0.15s ease',
        }}
      >
        <UploadCloud size={28} color={C.accent} strokeWidth={1.6} />
        <div style={{ fontSize: 13, fontWeight: 600, color: C.t1, marginTop: 12 }}>
          Drop a GeoTIFF here
        </div>
        <div style={{ fontSize: 12, fontWeight: 500, color: C.t2, marginTop: 4 }}>
          or click to browse
        </div>
        <div style={{ fontSize: 11, color: C.t3, marginTop: 12 }}>.tif / .tiff</div>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => accept(e.target.files?.[0])}
      />

      {error && <div style={{ marginTop: 12, fontSize: 12, color: '#ff453a' }}>{error}</div>}
    </>
  );
};
