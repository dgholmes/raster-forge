import { useEffect, useRef, useState } from 'react';
import { TileLayer, useMap } from 'react-leaflet';
import { resolveOrthoTileBase, TRANSPARENT_TILE_DATA_URL } from '../config/config';
import { resolveOrthoFolder } from '../services/orthoApi';

/* ============================================================================
 * OrthoTileLayerByRegion — the orthomosaic (hi-res drone/aerial) overlay stack.
 *
 * Tile stack (bottom → top), all with a transparent errorTileUrl so a missing
 * tile reveals the layer beneath (never a white/grey square):
 *
 *   [base]  VWorld Satellite (rendered by MapView, maxNativeZoom=19)  — online fallback
 *   [500]   Bundled tiles    (maxNativeZoom=20)                        — offline fallback
 *   [1000]  Server tiles     (maxNativeZoom=22)                        — primary hi-res
 *
 * Bundled tiles ship in public/assets/tiles/orthomosaic ({z}/{x}/{y}.png, z5–20)
 * so the map still shows imagery with no network.
 *
 * Server tiles: rather than a hardcoded bbox → folder map, the map center is
 * sent to the backend's /api/ortho/resolve (debounced, on moveend), which
 * discovers real folders on the tile server and probes for actual tile data
 * at that location. If a folder covers the area, its tiles render; if none
 * do, the server layer is skipped entirely for this view (VWorld + bundled
 * tiles still show beneath) instead of guessing or showing a wall of 404s.
 * This replaced an earlier hardcoded-bbox approach (ORTHO_REGIONS in
 * config.ts) — see reference/map-mechanics.md for the full rationale;
 * real orthomosaic coverage is rarely a clean rectangle, so probing the
 * exact tile is both simpler to configure AND more correct than a bbox guess.
 *
 * NOTE: ortho tiles use {z}/{x}/{y} order (unlike VWorld's {z}/{y}/{x}).
 * ========================================================================== */

/** Bundled tiles top out at z20 and OVERSCALE to z21-22 (don't request z21+). */
const BUNDLED_MAX_NATIVE_ZOOM = 20;

/** Fixed probe zoom for the folder-existence check — independent of the
 *  user's current zoom, so panning/zooming doesn't flicker the overlay in
 *  and out near tile edges. */
const PROBE_ZOOM = 15;

/** How long to wait after the map stops moving before re-resolving — avoids
 *  hitting the backend on every intermediate frame of a drag/zoom. */
const DEBOUNCE_MS = 400;

export function OrthoTileLayerByRegion() {
  const map = useMap();
  const [serverUrl, setServerUrl] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const resolve = async () => {
      const thisRequest = ++requestIdRef.current;
      const c = map.getCenter();
      const folder = await resolveOrthoFolder(c.lat, c.lng, PROBE_ZOOM);
      if (thisRequest !== requestIdRef.current) return; // a newer move superseded this one
      setServerUrl(folder ? `${resolveOrthoTileBase()}/${folder}/{z}/{x}/{y}.png` : null);
    };

    const scheduleResolve = () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(resolve, DEBOUNCE_MS);
    };

    resolve(); // initial check on mount, no debounce
    map.on('moveend', scheduleResolve);
    return () => {
      map.off('moveend', scheduleResolve);
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [map]);

  const localUrl = `${import.meta.env.BASE_URL || ''}assets/tiles/orthomosaic/{z}/{x}/{y}.png`;

  return (
    <>
      {/* Bundled fallback — offline-capable; z20 tiles overscale to z21-22. */}
      <TileLayer
        url={localUrl}
        minZoom={5}
        maxZoom={22}
        maxNativeZoom={BUNDLED_MAX_NATIVE_ZOOM}
        zIndex={500}
        opacity={1}
        errorTileUrl={TRANSPARENT_TILE_DATA_URL}
      />

      {/* Server tiles — only rendered once a real folder is confirmed to
          cover this location; remounts (via key) when the folder changes. */}
      {serverUrl && (
        <TileLayer
          key={serverUrl}
          url={serverUrl}
          minZoom={5}
          maxZoom={22}
          maxNativeZoom={22}
          zIndex={1000}
          opacity={1}
          updateWhenZooming
          updateWhenIdle
          keepBuffer={2}
          errorTileUrl={TRANSPARENT_TILE_DATA_URL}
        />
      )}
    </>
  );
}
