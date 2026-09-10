import React from 'react';
import { mapGlass, type C } from '../design-system/tokens';
import { APP } from '../config/config';

/* ============================================================================
 * BottomBar — floating status strip along the bottom of the map.
 * Left: current zoom · Center: lat, lng (6dp) · Right: copyright.
 * Dark-glass, legible over any imagery in both themes.
 * ========================================================================== */

interface Props {
  C: C;
  zoom: number;
  center: [number, number];
}

export const BottomBar: React.FC<Props> = ({ C, zoom, center }) => {
  const glass = mapGlass(C.dark);
  const t1 = C.dark ? '#e8e8ea' : '#1c1c1e';
  const t2 = C.dark ? '#aeaeb2' : '#48484a';
  const font = "'Outfit','Pretendard Variable','Pretendard','Noto Sans KR',system-ui,sans-serif";

  const cell: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 500,
    color: t2,
    fontFamily: font,
    fontVariantNumeric: 'tabular-nums',
  };

  return (
    <div
      style={{
        position: 'absolute',
        bottom: 16,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 600,
        display: 'flex',
        alignItems: 'center',
        gap: 18,
        padding: '7px 16px',
        borderRadius: 10,
        ...glass,
      }}
    >
      <span style={cell}>
        Zoom <span style={{ color: t1, fontWeight: 600 }}>{zoom.toFixed(0)}</span>
      </span>
      <span style={{ width: 1, height: 12, background: C.dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)' }} />
      <span style={{ ...cell, color: t1, fontWeight: 600 }}>
        {center[0].toFixed(6)}, {center[1].toFixed(6)}
      </span>
      <span style={{ width: 1, height: 12, background: C.dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.12)' }} />
      <span style={cell}>{APP.copyright}</span>
    </div>
  );
};
