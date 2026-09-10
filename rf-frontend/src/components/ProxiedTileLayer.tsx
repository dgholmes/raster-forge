import React, { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import { PROXY_CONFIG } from '../config/config';
import L from 'leaflet';

/* ============================================================================
 * ProxiedTileLayer — routes tile requests through a corporate proxy for
 * closed / air-gapped networks that cannot reach the tile origin directly.
 *
 * Overrides getTileUrl to (a) clamp requests beyond maxNativeZoom to the last
 * real tile (Leaflet then upscales), and (b) wrap the URL via
 * PROXY_CONFIG.createProxiedUrl. maxZoom stays 22 for orthomosaic compatibility.
 * ========================================================================== */

interface ProxiedTileLayerProps {
  baseUrl: string;
  attribution?: string;
  opacity?: number;
  zIndex?: number;
  maxZoom?: number;
  /** Highest zoom at which real tiles exist. Requests beyond this are clamped. */
  maxNativeZoom?: number;
  minZoom?: number;
  updateWhenZooming?: boolean;
  updateWhenIdle?: boolean;
  keepBuffer?: number;
}

export const ProxiedTileLayer: React.FC<ProxiedTileLayerProps> = ({
  baseUrl,
  attribution = '',
  opacity = 1.0,
  zIndex = 0,
  maxZoom,
  maxNativeZoom,
  minZoom,
  updateWhenZooming,
  updateWhenIdle,
  keepBuffer,
}) => {
  const map = useMap();
  const tileLayerRef = useRef<L.TileLayer | null>(null);

  useEffect(() => {
    if (!map) return;

    // Skip recreation if the layer already exists with the same URL.
    if (tileLayerRef.current) {
      const currentBaseUrl = (tileLayerRef.current as any)._url || '';
      if (currentBaseUrl === baseUrl) return;
      map.removeLayer(tileLayerRef.current);
    }

    const layerOptions: L.TileLayerOptions = { attribution, opacity, zIndex };

    // nativeLimit = highest zoom where real tiles exist (maxNativeZoom if given,
    // else maxZoom — original behaviour). maxZoom stays 22 so the layer stays
    // visible and Leaflet upscales native tiles up to zoom 22.
    const nativeLimit = maxNativeZoom ?? maxZoom;
    if (nativeLimit !== undefined) {
      layerOptions.maxNativeZoom = nativeLimit;
      layerOptions.maxZoom = 22; // backward-compat: orthomosaic support
    }
    if (minZoom !== undefined) layerOptions.minZoom = minZoom;
    if (updateWhenZooming !== undefined) layerOptions.updateWhenZooming = updateWhenZooming;
    if (updateWhenIdle !== undefined) layerOptions.updateWhenIdle = updateWhenIdle;
    if (keepBuffer !== undefined) layerOptions.keepBuffer = keepBuffer;

    const layer = L.tileLayer('', layerOptions);
    tileLayerRef.current = layer;

    // Override getTileUrl to clamp zoom + proxy the request.
    const nativeLimitForUrl = maxNativeZoom ?? maxZoom;
    layer.getTileUrl = function (coords: L.Coords) {
      const effectiveZoom =
        nativeLimitForUrl !== undefined && coords.z > nativeLimitForUrl
          ? nativeLimitForUrl
          : coords.z;

      // When zooming past the native limit, reuse the last real tile.
      const zoomDiff = coords.z - effectiveZoom;
      const effectiveX = zoomDiff > 0 ? Math.floor(coords.x / Math.pow(2, zoomDiff)) : coords.x;
      const effectiveY = zoomDiff > 0 ? Math.floor(coords.y / Math.pow(2, zoomDiff)) : coords.y;

      const tileUrl = baseUrl
        .replace('{z}', effectiveZoom.toString())
        .replace('{x}', effectiveX.toString())
        .replace('{y}', effectiveY.toString());

      return PROXY_CONFIG.createProxiedUrl(tileUrl);
    };

    layer.addTo(map);
    layer.on('tileerror', (event: L.TileErrorEvent) => {
      console.error('Proxied tile load error:', event.coords);
    });

    return () => {
      if (tileLayerRef.current) map.removeLayer(tileLayerRef.current);
    };
  }, [
    map,
    baseUrl,
    attribution,
    opacity,
    zIndex,
    maxZoom,
    maxNativeZoom,
    minZoom,
    updateWhenZooming,
    updateWhenIdle,
    keepBuffer,
  ]);

  return null;
};
