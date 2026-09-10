/* Formatting helpers shared across RasterForge screens. */

export function formatBytes(bytes: number | null | undefined, decimals = 1): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024)));
  const value = bytes / 1024 ** i;
  return `${value.toFixed(i === 0 ? 0 : decimals)} ${units[i]}`;
}

export function formatInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString();
}

/** Ground sample distance, in the unit an operator actually thinks in. */
export function formatGsd(metres: number | null | undefined): string {
  if (!metres || metres <= 0) return '—';
  if (metres < 1) return `${(metres * 100).toFixed(1)} cm/px`;
  return `${metres.toFixed(2)} m/px`;
}

export function formatPixelSize(x: number | null, y: number | null): string {
  if (!x || !y) return '—';
  const fmt = (v: number) => (v < 0.01 ? v.toExponential(2) : v.toFixed(4).replace(/0+$/, ''));
  return `${fmt(x)} x ${fmt(y)}`;
}

export function formatDimensions(w: number | null, h: number | null): string {
  if (!w || !h) return '—';
  return `${w.toLocaleString()} x ${h.toLocaleString()} px`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** hh:mm:ss elapsed, the format the processing screen shows. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '—';
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':');
}

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diff = Math.max(0, Date.now() - then) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return formatDate(iso);
}

export function formatCrs(epsg: number | null, name: string | null): string {
  if (epsg && name) return `EPSG:${epsg}`;
  if (epsg) return `EPSG:${epsg}`;
  return name || '—';
}
