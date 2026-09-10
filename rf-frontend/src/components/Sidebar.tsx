import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { chromeGlass, type C } from '../design-system/tokens';
import type { NavItem } from '../types';

/* ============================================================================
 * Sidebar — left sidebar for pages that prefer the classic sidebar layout
 * over floating bars. Pages pick FloatingPanel OR Sidebar.
 *
 * Solid (C.side) by default. Pass `glass` when this Sidebar is positioned as
 * an absolute/fixed overlay on top of full-bleed map/content, alongside an
 * overlay Topbar (see Topbar's `overlay` prop) — that combination is what
 * lets its backdrop-filter blur actually show something (see chromeGlass in
 * tokens.ts for why). Don't pass `glass` for a Sidebar laid out in normal
 * flow beside the map; there's nothing behind it to blur and it'll just look
 * like a flat tinted box.
 * ========================================================================== */

interface Props {
  C: C;
  nav?: NavItem[];
  width?: number;
  header?: React.ReactNode;
  children?: React.ReactNode;
  /** Use the overlay-glass treatment instead of a solid fill — see note above. */
  glass?: boolean;
}

export const Sidebar: React.FC<Props> = ({ C, nav, width = 220, header, children, glass = false }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const font = "'Outfit','Pretendard Variable','Pretendard','Noto Sans KR',system-ui,sans-serif";

  const glassStyle = glass ? chromeGlass(C.dark) : null;
  const borderColor = glassStyle ? glassStyle.border : `1px solid ${C.b}`;

  return (
    <aside
      style={{
        width,
        height: '100%',
        ...(glassStyle ?? { background: C.side }),
        borderRight: borderColor,
        border: undefined,
        display: 'flex',
        flexDirection: 'column',
        fontFamily: font,
        flexShrink: 0,
      }}
    >
      {header && <div style={{ padding: '14px 16px', borderBottom: borderColor }}>{header}</div>}

      {nav && (
        <nav style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {nav.map((item) => {
            const active = location.pathname === item.path;
            const Icon = item.icon;
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 12px',
                  borderRadius: 8,
                  border: 'none',
                  cursor: 'pointer',
                  fontFamily: font,
                  fontSize: 13,
                  fontWeight: active ? 600 : 500,
                  color: active ? C.t1 : C.t2,
                  background: active ? C.activeBg : 'transparent',
                  textAlign: 'left',
                  transition: 'background .12s',
                }}
                onMouseEnter={(e) => {
                  if (!active) e.currentTarget.style.background = C.row;
                }}
                onMouseLeave={(e) => {
                  if (!active) e.currentTarget.style.background = 'transparent';
                }}
              >
                {Icon && <Icon size={16} strokeWidth={1.9} />}
                {item.label}
              </button>
            );
          })}
        </nav>
      )}

      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>{children}</div>
    </aside>
  );
};
