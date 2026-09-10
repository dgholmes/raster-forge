import React, { useState } from 'react';
import { MapContainer, CircleMarker, Popup, useMapEvents } from 'react-leaflet';
import { API_CONFIG, APP } from '../config/config';
import { STATUS, type C } from '../design-system/tokens';
import { ConditionalTileLayer } from './ConditionalTileLayer';
import { OrthoTileLayerByRegion } from './OrthoTileLayer';
import { MapControls } from './MapControls';
import { BottomBar } from './BottomBar';
import type { ItemStatus, MapMarkerItem } from '../types';

/* ============================================================================
 * MapView — the reusable map surface.
 *
 * Renders (bottom → top):
 *   1. VWorld Satellite base    (maxNativeZoom=19, maxZoom=22)
 *   2. Ortho overlay stack      (when showOrtho — see OrthoTileLayer)
 *   3. Markers (CircleMarker)   with popups
 *   4. MapControls + BottomBar  (floating glass)
 *
 * CRITICAL: MapContainer sets maxZoom={22} (Leaflet caps at ~18 otherwise) and
 * the VWorld layer freezes at native zoom 19.
 * ========================================================================== */

interface Props {
  C: C;
  markers?: MapMarkerItem[];
  selectedId?: string | null;
  onMarkerClick?: (item: MapMarkerItem) => void;
  showOrtho?: boolean;
  children?: React.ReactNode;
}

const statusColor = (s?: ItemStatus): string => {
  switch (s) {
    case 'ok':
      return STATUS.green;
    case 'warn':
      return STATUS.amber;
    case 'alert':
      return STATUS.red;
    default:
      return '#0a84ff';
  }
};

/** Reports zoom + center to the parent so BottomBar can display them. */
const MapEvents: React.FC<{ onChange: (zoom: number, center: [number, number]) => void }> = ({
  onChange,
}) => {
  const map = useMapEvents({
    moveend: () => {
      const c = map.getCenter();
      onChange(map.getZoom(), [c.lat, c.lng]);
    },
    zoomend: () => {
      const c = map.getCenter();
      onChange(map.getZoom(), [c.lat, c.lng]);
    },
  });
  return null;
};

export const MapView: React.FC<Props> = ({
  C,
  markers = [],
  selectedId,
  onMarkerClick,
  showOrtho: showOrthoProp = true,
  children,
}) => {
  const [showOrtho, setShowOrtho] = useState(showOrthoProp);
  const [zoom, setZoom] = useState(APP.defaultZoom);
  const [center, setCenter] = useState<[number, number]>(APP.defaultCenter);

  return (
    <div className="md-map-fill" style={{ position: 'relative' }}>
      <MapContainer
        center={APP.defaultCenter}
        zoom={APP.defaultZoom}
        maxZoom={API_CONFIG.MAP_MAX_ZOOM}
        minZoom={5}
        zoomControl={false}
        attributionControl={false}
        style={{ height: '100%', width: '100%' }}
      >
        <MapEvents
          onChange={(z, c) => {
            setZoom(z);
            setCenter(c);
          }}
        />

        {/* VWorld Satellite base — native zoom 19, upscaled to 22. */}
        <ConditionalTileLayer
          baseUrl={API_CONFIG.VWORLD_MAP_URLS.satellite}
          maxNativeZoom={API_CONFIG.VWORLD_MAX_NATIVE_ZOOM}
          maxZoom={API_CONFIG.MAP_MAX_ZOOM}
          minZoom={5}
          zIndex={100}
        />

        {/* Hi-res ortho overlay (bundled + server tiles). */}
        {showOrtho && <OrthoTileLayerByRegion />}

        {/* Markers */}
        {markers.map((m) => {
          const selected = m.id === selectedId;
          const color = statusColor(m.status);
          return (
            <CircleMarker
              key={m.id}
              center={[m.lat, m.lng]}
              radius={selected ? 11 : 8}
              pathOptions={{
                color: '#fff',
                weight: selected ? 3 : 2,
                fillColor: color,
                fillOpacity: 0.9,
              }}
              eventHandlers={{ click: () => onMarkerClick?.(m) }}
            >
              <Popup>
                <div style={{ minWidth: 140 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#1c1c1e' }}>{m.name}</div>
                  <div style={{ fontSize: 11, color: '#636366', marginTop: 2 }}>
                    {m.lat.toFixed(5)}, {m.lng.toFixed(5)}
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}

        {children}

        <MapControls C={C} orthoOn={showOrtho} onToggleOrtho={() => setShowOrtho((v) => !v)} />
        <BottomBar C={C} zoom={zoom} center={center} />
      </MapContainer>
    </div>
  );
};
