/* ============================================================================
 * config.ts — central configuration for the map dashboard.
 *
 * The skill customises the marked sections per project:
 *   • APP.name / APP.copyright        → project identity
 *   • env vars (.env)                 → API/WS/VWorld/tile/proxy endpoints
 *
 * Ortho tile region coverage is NOT configured here — it's resolved
 * dynamically per-view by the backend's /api/ortho/resolve (see
 * backend/app/tiles.py and components/OrthoTileLayer.tsx), which discovers
 * real folders on the tile server and probes for actual tile data at the
 * current location instead of relying on hardcoded bounding boxes. See
 * reference/map-mechanics.md for why this replaced the old ORTHO_REGIONS
 * bbox-list approach.
 *
 * Nothing else here should need editing for a new project.
 * ========================================================================== */

/* ── Project identity (customised by the skill) ───────────────────────────── */
export const APP = {
  name: import.meta.env.VITE_APP_NAME || 'RasterForge',
  logo: `${import.meta.env.BASE_URL}assets/logo.png`,
  copyright: import.meta.env.VITE_APP_COPYRIGHT || '© 2026',
  /** Default map center [lat, lon] and zoom */
  defaultCenter: [
    Number(import.meta.env.VITE_MAP_CENTER_LAT ?? 37.5665),
    Number(import.meta.env.VITE_MAP_CENTER_LON ?? 126.9780),
  ] as [number, number],
  defaultZoom: Number(import.meta.env.VITE_MAP_ZOOM ?? 13),
};

/* ── Backend / VWorld config ──────────────────────────────────────────────── */
export const API_CONFIG = {
  API_BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:9010',
  WEBSOCKET_URL: import.meta.env.VITE_WEBSOCKET_URL || 'ws://localhost:9010/ws',

  VWORLD_API_KEY: import.meta.env.VITE_VWORLD_API_KEY,

  // VWorld WMTS — NOTE: VWorld uses {z}/{y}/{x} order (TMS-style), not {z}/{x}/{y}
  VWORLD_MAP_URLS: {
    base:      `https://api.vworld.kr/req/wmts/1.0.0/${import.meta.env.VITE_VWORLD_API_KEY}/Base/{z}/{y}/{x}.png`,
    satellite: `https://api.vworld.kr/req/wmts/1.0.0/${import.meta.env.VITE_VWORLD_API_KEY}/Satellite/{z}/{y}/{x}.jpeg`,
    hybrid:    `https://api.vworld.kr/req/wmts/1.0.0/${import.meta.env.VITE_VWORLD_API_KEY}/Hybrid/{z}/{y}/{x}.png`,
  },

  // VWorld imagery ends at native zoom 19; z20+ returns an XML error (HTTP 200).
  // We freeze at 19 and let Leaflet upscale to maxZoom (22). See MapView.
  VWORLD_MAX_NATIVE_ZOOM: 19,
  MAP_MAX_ZOOM: 22,

  ENDPOINTS: {
    LOGIN:  '/api/auth/login',
    ME:     '/api/auth/me',
    LOGOUT: '/api/auth/logout',
    HEALTH: '/api/health',

    DATASETS:     '/api/datasets',
    JOBS:         '/api/jobs',
    ADMIN_STATS:  '/api/admin/stats',
    ADMIN_USERS:  '/api/admin/users',
  },
};

/* ── Proxy config (closed / air-gapped networks) ──────────────────────────────
 * When VITE_USE_PROXY=true, VWorld tiles are routed through a corporate proxy so
 * the deployment server (which cannot reach the internet directly) can fetch them.
 * -------------------------------------------------------------------------- */
export const PROXY_CONFIG = {
  USE_PROXY: import.meta.env.VITE_USE_PROXY === 'true',
  PROXY_BASE_URL: import.meta.env.VITE_PROXY_BASE_URL || '',

  createProxiedUrl(originalUrl: string): string {
    if (!PROXY_CONFIG.USE_PROXY || !PROXY_CONFIG.PROXY_BASE_URL) return originalUrl;
    return `${PROXY_CONFIG.PROXY_BASE_URL}${encodeURIComponent(originalUrl)}`;
  },
};

/* ── Ortho tile helpers ───────────────────────────────────────────────────── */

// 1×1 fully-transparent PNG. Used as errorTileUrl so a missing ortho/VWorld tile
// reveals the layer beneath it (never a white or grey square).
export const TRANSPARENT_TILE_DATA_URL =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

/** Resolve the ortho tile server base URL (no trailing slash).
 *  Priority: env override → same-origin /2Dtile on HTTPS (avoids mixed content)
 *  → direct HTTP base in dev. */
export function resolveOrthoTileBase(): string {
  const env = import.meta.env.VITE_ORTHO_TILE_BASE_URL as string | undefined;
  if (env?.trim()) return env.trim().replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location.protocol === 'https:') return '/2Dtile';
  return import.meta.env.VITE_ORTHO_TILE_BASE_URL_DEV || 'http://localhost:9090/2Dtile';
}

export const ENV_CONFIG = {
  isDevelopment: import.meta.env.DEV,
  isProduction: import.meta.env.PROD,
  useProxy: PROXY_CONFIG.USE_PROXY,
};

export const WEBSOCKET_CONFIG = {
  MAX_RECONNECT_ATTEMPTS: 5,
  RECONNECT_DELAY: 3000,
  HEARTBEAT_INTERVAL: 30000,
};


/* ── RasterForge tile publishing ──────────────────────────────────────────────
 * Base URL the backend advertises generated pyramids at. Must match the
 * backend's TILE_PUBLIC_BASE, since that is what Copy URL hands the user.
 * -------------------------------------------------------------------------- */
export const TILE_CONFIG = {
  PUBLIC_BASE: (
    import.meta.env.VITE_TILE_PUBLIC_BASE || 'http://localhost:9010/tiles'
  ).replace(/\/$/, ''),

  /** Highest zoom the map allows. Leaflet upscales past a layer's
   *  maxNativeZoom, so a pyramid ending at 19 still pans smoothly to 22. */
  MAX_ZOOM: 22,
};

/** Zoom limits offered in the configuration UI. */
export const ZOOM_LIMITS = { MIN: 0, MAX: 22 };

/** Resampling methods gdal2tiles accepts. Mirrors the backend enum — the
 *  backend re-validates, so this list is UI convenience, not the guard. */
export const RESAMPLING_METHODS = [
  { value: 'nearest', label: 'Nearest', hint: 'Fastest; hard pixel edges' },
  { value: 'bilinear', label: 'Bilinear', hint: 'Recommended for orthophotos' },
  { value: 'cubic', label: 'Cubic', hint: 'Smoother, slower' },
  { value: 'cubicspline', label: 'Cubic Spline', hint: 'Very smooth, slowest' },
  { value: 'lanczos', label: 'Lanczos', hint: 'Sharpest, slowest' },
] as const;

export const NODATA_MODES = [
  { value: 'auto', label: 'Auto', hint: 'Recommended - RasterForge decides' },
  { value: 'preserve', label: 'Preserve source NoData', hint: 'Tile the raster as supplied' },
  { value: 'remove', label: 'Remove NoData metadata', hint: 'Always write a clean working copy' },
] as const;

/* ── Basemaps under the generated tiles ───────────────────────────────────────
 * VWorld satellite is preferred — satellite imagery is the right context for
 * an orthomosaic — but it needs a registered key. OpenStreetMap is the
 * keyless fallback so the preview always has geographic context.
 *
 * Two things differ between them and both matter:
 *   • URL order. VWorld is {z}/{y}/{x} (TMS-style); OSM is {z}/{x}/{y}.
 *     Swapping either one shifts the whole map.
 *   • Attribution. The OSM tile usage policy REQUIRES visible attribution,
 *     so the preview map enables Leaflet's attribution control whenever a
 *     basemap is active.
 *
 * Both stop at native zoom 19 and are overscaled to 22 by Leaflet, so the
 * map stays continuous above their real imagery.
 * -------------------------------------------------------------------------- */

export interface Basemap {
  id: 'vworld' | 'osm';
  label: string;
  url: string;
  maxNativeZoom: number;
  attribution: string;
  /** Needs the internet — unavailable on a closed network without a proxy. */
  needsInternet: boolean;
}

export const BASEMAPS: Record<Basemap['id'], Basemap> = {
  vworld: {
    id: 'vworld',
    label: 'Satellite',
    url: API_CONFIG.VWORLD_MAP_URLS.satellite,
    maxNativeZoom: API_CONFIG.VWORLD_MAX_NATIVE_ZOOM, // 19 — z20+ returns XML at HTTP 200
    attribution: '&copy; <a href="https://www.vworld.kr/" target="_blank" rel="noopener">VWorld</a>',
    needsInternet: true,
  },
  osm: {
    id: 'osm',
    label: 'Street',
    // Single hostname, not the legacy {s}.tile.* subdomain rotation, which
    // OSM deprecated in favour of one HTTP/2 host.
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    maxNativeZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
    needsInternet: true,
  },
};

/** Basemaps usable in this deployment, best first. VWorld only counts when a
 *  key is configured; OSM always qualifies because it needs no key. */
export function availableBasemaps(): Basemap[] {
  const out: Basemap[] = [];
  if (API_CONFIG.VWORLD_API_KEY) out.push(BASEMAPS.vworld);
  out.push(BASEMAPS.osm);
  return out;
}
