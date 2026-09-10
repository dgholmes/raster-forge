import React, { useState } from 'react';
import { useMap } from 'react-leaflet';
import { Plus, Minus, Crosshair, Layers, Maximize2 } from 'lucide-react';
import { mapGlass, type C } from '../design-system/tokens';

/* ============================================================================
 * MapControls — floating toolbar (top-right) over the map.
 *
 * Zoom in/out, locate (geolocation → flyTo), toggle the ortho overlay, and
 * fullscreen. Uses mapGlass(C.dark) so it stays legible over any imagery in
 * BOTH light and dark themes (the glass is always dark-tinted on dark maps).
 * ========================================================================== */

interface Props {
  C: C;
  orthoOn: boolean;
  onToggleOrtho: () => void;
}

export const MapControls: React.FC<Props> = ({ C, orthoOn, onToggleOrtho }) => {
  const map = useMap();
  const [locating, setLocating] = useState(false);
  const glass = mapGlass(C.dark);
  const icon = C.dark ? '#e8e8ea' : '#1c1c1e';
  const iconMuted = C.dark ? '#aeaeb2' : '#48484a';

  const locate = () => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        map.flyTo([pos.coords.latitude, pos.coords.longitude], Math.max(map.getZoom(), 16));
        setLocating(false);
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const toggleFullscreen = () => {
    const el = map.getContainer();
    if (!document.fullscreenElement) el.requestFullscreen?.();
    else document.exitFullscreen?.();
  };

  const btn = (
    key: string,
    onClick: () => void,
    children: React.ReactNode,
    active = false,
    title = ''
  ) => (
    <button
      key={key}
      onClick={onClick}
      title={title}
      style={{
        width: 34,
        height: 34,
        border: 'none',
        background: active ? C.accent : 'transparent',
        color: active ? '#fff' : icon,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'background .12s',
      }}
      onMouseEnter={(e) => {
        if (!active) e.currentTarget.style.background = C.dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.background = 'transparent';
      }}
    >
      {children}
    </button>
  );

  const divider = <div style={{ height: 1, background: C.dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)' }} />;

  return (
    <div
      className="md-float md-float-tr"
      style={{
        display: 'flex',
        flexDirection: 'column',
        borderRadius: 10,
        overflow: 'hidden',
        ...glass,
      }}
    >
      {btn('in', () => map.zoomIn(), <Plus size={16} strokeWidth={2} />, false, 'Zoom in')}
      {divider}
      {btn('out', () => map.zoomOut(), <Minus size={16} strokeWidth={2} />, false, 'Zoom out')}
      {divider}
      {btn(
        'locate',
        locate,
        <Crosshair size={15} strokeWidth={1.9} color={locating ? C.accent : iconMuted} />,
        false,
        'My location'
      )}
      {divider}
      {btn('ortho', onToggleOrtho, <Layers size={15} strokeWidth={1.9} />, orthoOn, 'Toggle hi-res overlay')}
      {divider}
      {btn('fs', toggleFullscreen, <Maximize2 size={15} strokeWidth={1.9} color={iconMuted} />, false, 'Fullscreen')}
    </div>
  );
};
