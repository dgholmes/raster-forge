import React, { useCallback, useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet';
import type { Map as LeafletMap } from 'leaflet';
import { Crosshair, Layers, Maximize2 } from 'lucide-react';
import {
  APP,
  TRANSPARENT_TILE_DATA_URL,
  availableBasemaps,
  type Basemap,
} from '../../config/config';
import { type C } from '../../design-system/tokens';
import { ConditionalTileLayer } from '../ConditionalTileLayer';

/* ============================================================================
 * TilePreviewMap — the generated pyramid, on a real map.
 *
 * The tile-stack rules here are load-bearing and must not be relaxed
 * (see the map-dashboard-starter skill's map-mechanics reference):
 *
 *   • VWorld URLs are {z}/{y}/{x} — TMS order. OSM and the generated XYZ
 *     pyramid are {z}/{x}/{y}. Swapping either one shifts the whole map.
 *   • VWorld maxNativeZoom is 19 and never higher: z20+ returns an XML error
 *     document with HTTP 200, which Leaflet cannot detect as a failure, so
 *     the tiles render blank. OSM also stops at 19.
 *   • MapContainer itself must carry maxZoom={22} or Leaflet caps
 *     interaction around 18 regardless of per-layer settings.
 *   • Every miss-prone layer uses a transparent errorTileUrl so a missing
 *     tile reveals the layer beneath instead of a white or grey square.
 *
 * The generated layer's maxNativeZoom is the output's real max zoom, so
 * zooming past it upscales the last real tile rather than going blank.
 * ========================================================================== */

// Best available first: VWorld satellite when a key exists, else OSM.
const BASEMAPS = availableBasemaps();

interface Props {
  C: C;
  /** XYZ template, e.g. http://host/tiles/slug/{z}/{x}/{y}.png */
  tileUrl: string;
  /** [minLon, minLat, maxLon, maxLat] */
  bounds: [number, number, number, number] | null;
  center: [number, number] | null;
  minZoom: number;
  maxZoom: number;
  height?: number;
}

/** Fits the map to the raster footprint once, and on demand afterwards. */
const FitBounds: React.FC<{
  bounds: [number, number, number, number] | null;
  onMap: (m: LeafletMap) => void;
}> = ({ bounds, onMap }) => {
  const map = useMap();
  const fittedRef = useRef(false);

  useEffect(() => {
    onMap(map);
    if (fittedRef.current || !bounds) return;
    fittedRef.current = true;
    const [west, south, east, north] = bounds;
    map.fitBounds(
      [
        [south, west],
        [north, east],
      ],
      { padding: [24, 24] },
    );
  }, [map, bounds, onMap]);

  return null;
};

const CursorReadout: React.FC<{ onMove: (lat: number, lng: number, z: number) => void }> = ({
  onMove,
}) => {
  const map = useMapEvents({
    mousemove: (e) => onMove(e.latlng.lat, e.latlng.lng, map.getZoom()),
    zoomend: () => {
      const c = map.getCenter();
      onMove(c.lat, c.lng, map.getZoom());
    },
  });
  return null;
};

/** Keeps the page scrollable past the map.
 *
 * A full-width map inside a scrolling document swallows the wheel: the user
 * tries to scroll the page and instead zooms the map out. Wheel zoom is
 * therefore off until the map is clicked, and turns off again when the
 * pointer leaves -- the common pattern for embedded maps. */
const ScrollZoomGate: React.FC<{ armed: boolean; onArm: (v: boolean) => void }> = ({
  armed,
  onArm,
}) => {
  const map = useMapEvents({
    click: () => onArm(true),
    mouseout: () => onArm(false),
  });

  useEffect(() => {
    if (armed) map.scrollWheelZoom.enable();
    else map.scrollWheelZoom.disable();
  }, [armed, map]);

  return null;
};

export const TilePreviewMap: React.FC<Props> = ({
  C,
  tileUrl,
  bounds,
  center,
  minZoom,
  maxZoom,
  height = 460,
}) => {
  const mapRef = useRef<LeafletMap | null>(null);
  const [readout, setReadout] = useState<{ lat: number; lng: number; z: number } | null>(null);
  // Index into BASEMAPS; BASEMAPS.length means "no basemap".
  const [baseIndex, setBaseIndex] = useState(0);
  const [opacity, setOpacity] = useState(1);
  const [wheelArmed, setWheelArmed] = useState(false);

  const initialCenter: [number, number] = center
    ? [center[1], center[0]]
    : APP.defaultCenter;

  // Stable identity: an inline handler would make FitBounds' effect re-run on
  // every parent render and re-fit the map under the user.
  const handleMap = useCallback((m: LeafletMap) => {
    mapRef.current = m;
  }, []);

  const basemap: Basemap | null = BASEMAPS[baseIndex] ?? null;

  const cycleBasemap = useCallback(() => {
    // ...through every available basemap, then off, then back to the first.
    setBaseIndex((i) => (i + 1) % (BASEMAPS.length + 1));
  }, []);

  const refit = useCallback(() => {
    if (!mapRef.current || !bounds) return;
    const [west, south, east, north] = bounds;
    mapRef.current.fitBounds(
      [
        [south, west],
        [north, east],
      ],
      { padding: [24, 24] },
    );
  }, [bounds]);

  const chip: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    height: 28,
    padding: '0 10px',
    borderRadius: 7,
    fontSize: 11,
    fontWeight: 500,
    cursor: 'pointer',
    background: C.dark ? 'rgba(8,11,16,0.55)' : 'rgba(255,255,255,0.62)',
    backdropFilter: 'blur(28px)',
    WebkitBackdropFilter: 'blur(28px)',
    border: C.dark ? '1px solid rgba(255,255,255,0.07)' : '1px solid rgba(0,0,0,0.06)',
    color: C.t1,
  };

  return (
    <div
      className={`rf-map ${C.dark ? 'rf-map--dark' : 'rf-map--light'}`}
      style={{
        position: 'relative',
        height,
        borderRadius: 10,
        overflow: 'hidden',
        border: `1.5px solid ${C.cardB}`,
        background: C.thumbBg,
      }}
    >
      <MapContainer
        center={initialCenter}
        zoom={Math.max(APP.defaultZoom, minZoom)}
        maxZoom={22}
        minZoom={2}
        scrollWheelZoom={false}
        style={{ height: '100%', width: '100%', background: C.thumbBg }}
        // OSM's licence requires visible attribution; Leaflet collects it
        // from each layer's `attribution` prop.
        attributionControl={basemap !== null}
      >
        <FitBounds bounds={bounds} onMap={handleMap} />
        <ScrollZoomGate armed={wheelArmed} onArm={setWheelArmed} />
        <CursorReadout onMove={(lat, lng, z) => setReadout({ lat, lng, z })} />

        {/* Base context, overscaled from its native 19 up to 22. Routed
            through the closed-network proxy when VITE_USE_PROXY is set. */}
        {basemap && (
          <ConditionalTileLayer
            key={basemap.id}
            baseUrl={basemap.url}
            attribution={basemap.attribution}
            maxNativeZoom={basemap.maxNativeZoom}
            maxZoom={22}
            zIndex={100}
            errorTileUrl={TRANSPARENT_TILE_DATA_URL}
          />
        )}

        {/* The generated pyramid: {z}/{x}/{y}, upscaled past its real max zoom. */}
        <TileLayer
          key={tileUrl}
          url={tileUrl}
          maxNativeZoom={maxZoom}
          maxZoom={22}
          minZoom={0}
          opacity={opacity}
          zIndex={1000}
          errorTileUrl={TRANSPARENT_TILE_DATA_URL}
        />
      </MapContainer>

      {/* Controls — glass overlays stacked on the map, which is what makes the
          backdrop blur actually have something to blur. */}
      <div
        style={{
          position: 'absolute',
          top: 12,
          right: 12,
          zIndex: 500,
          display: 'flex',
          gap: 8,
          alignItems: 'center',
        }}
      >
        <button
          style={chip}
          onClick={cycleBasemap}
          title={
            BASEMAPS.length > 1
              ? 'Cycle basemap: ' + BASEMAPS.map((b) => b.label).join(' / ') + ' / off'
              : 'Toggle the basemap'
          }
        >
          <Layers size={13} strokeWidth={1.7} />
          {basemap ? basemap.label : 'No basemap'}
        </button>
        <button style={chip} onClick={refit} title="Zoom to the raster's extent">
          <Maximize2 size={13} strokeWidth={1.7} />
          Fit
        </button>
      </div>

      <div
        style={{
          position: 'absolute',
          bottom: 12,
          left: 12,
          right: 12,
          zIndex: 500,
          display: 'flex',
          gap: 8,
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ ...chip, cursor: 'default' }}>
          <Crosshair size={13} strokeWidth={1.7} />
          {readout
            ? `${readout.lat.toFixed(6)}, ${readout.lng.toFixed(6)}  ·  z${readout.z}`
            : `zoom ${minZoom}–${maxZoom}`}
        </div>

        {!wheelArmed && (
          <div style={{ ...chip, cursor: 'default', color: C.t2 }}>
            Click the map to enable scroll zoom
          </div>
        )}

        <label style={{ ...chip, cursor: 'default', gap: 8 }}>
          Opacity
          <input
            type="range"
            min={20}
            max={100}
            value={opacity * 100}
            onChange={(e) => setOpacity(Number(e.target.value) / 100)}
            style={{ width: 80, accentColor: C.accent }}
          />
        </label>
      </div>

      {BASEMAPS.length === 1 && basemap?.id === 'osm' && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            // Clear Leaflet's zoom control, which owns the top-left corner
            // (~34px wide plus its own inset).
            left: 56,
            zIndex: 500,
            ...chip,
            width: 'fit-content',
            maxWidth: 'calc(100% - 140px)',
            cursor: 'default',
            color: C.t2,
          }}
          title="Set VITE_VWORLD_API_KEY in rf-frontend/.env for satellite imagery instead"
        >
          OpenStreetMap basemap — add a VWorld key for satellite
        </div>
      )}
    </div>
  );
};
