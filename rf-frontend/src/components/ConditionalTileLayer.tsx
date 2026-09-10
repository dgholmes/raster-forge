import React from 'react';
import { TileLayer } from 'react-leaflet';
import { ProxiedTileLayer } from './ProxiedTileLayer';
import { PROXY_CONFIG } from '../config/config';

/* ============================================================================
 * ConditionalTileLayer — renders ProxiedTileLayer when VITE_USE_PROXY=true
 * (closed networks), else a plain react-leaflet TileLayer (direct fetch).
 *
 * maxNativeZoom is the native tile limit; Leaflet upscales beyond it up to
 * maxZoom. For VWorld base use maxNativeZoom=19; for ortho use 22.
 * ========================================================================== */

interface ConditionalTileLayerProps {
  baseUrl: string;
  attribution?: string;
  opacity?: number;
  zIndex?: number;
  maxZoom?: number;
  /** Native tile limit — Leaflet upscales beyond this. VWorld=19, ortho=22. */
  maxNativeZoom?: number;
  minZoom?: number;
  updateWhenZooming?: boolean;
  updateWhenIdle?: boolean;
  keepBuffer?: number;
  errorTileUrl?: string;
}

export const ConditionalTileLayer: React.FC<ConditionalTileLayerProps> = (props) => {
  const resolvedMaxNativeZoom = props.maxNativeZoom ?? props.maxZoom;

  if (PROXY_CONFIG.USE_PROXY) {
    return (
      <ProxiedTileLayer
        baseUrl={props.baseUrl}
        attribution={props.attribution}
        opacity={props.opacity}
        zIndex={props.zIndex}
        maxZoom={props.maxZoom}
        maxNativeZoom={resolvedMaxNativeZoom}
        minZoom={props.minZoom}
        updateWhenZooming={props.updateWhenZooming}
        updateWhenIdle={props.updateWhenIdle}
        keepBuffer={props.keepBuffer}
      />
    );
  }

  return (
    <TileLayer
      url={props.baseUrl}
      attribution={props.attribution}
      opacity={props.opacity}
      zIndex={props.zIndex}
      maxZoom={props.maxZoom}
      maxNativeZoom={resolvedMaxNativeZoom}
      minZoom={props.minZoom}
      updateWhenZooming={props.updateWhenZooming}
      updateWhenIdle={props.updateWhenIdle}
      keepBuffer={props.keepBuffer}
      errorTileUrl={props.errorTileUrl}
    />
  );
};
