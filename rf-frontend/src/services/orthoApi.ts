import { getApiBaseUrl } from './api';

/* ============================================================================
 * orthoApi.ts — dynamic ortho tile region resolution.
 *
 * Calls the backend's /api/ortho/resolve, which discovers real folders on the
 * tile server and probes for actual tile data at a given lat/lng — no
 * hardcoded bounding boxes on the frontend. Returns null if no folder has
 * coverage there (or the backend/tile server is unreachable), in which case
 * the caller should skip the hi-res overlay for this view.
 * ========================================================================== */

export async function resolveOrthoFolder(lat: number, lng: number, z = 15): Promise<string | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  try {
    const url = `${getApiBaseUrl()}/api/ortho/resolve?lat=${lat}&lng=${lng}&z=${z}`;
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) return null;
    const data = (await res.json()) as { folder: string | null };
    return data.folder ?? null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}
