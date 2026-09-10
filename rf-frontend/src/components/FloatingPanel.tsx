import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { mapGlass, type C } from '../design-system/tokens';

/* ============================================================================
 * FloatingPanel — a glass card that floats over the map (for the "bars over
 * map" layout). Optional collapse. Position via className (md-float-tl etc.)
 * or wrap it yourself.
 * ========================================================================== */

interface Props {
  C: C;
  title?: string;
  icon?: React.ReactNode;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  width?: number;
  className?: string;
  style?: React.CSSProperties;
  headerRight?: React.ReactNode;
  children: React.ReactNode;
}

export const FloatingPanel: React.FC<Props> = ({
  C,
  title,
  icon,
  collapsible = false,
  defaultCollapsed = false,
  width = 300,
  className,
  style,
  headerRight,
  children,
}) => {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const glass = mapGlass(C.dark);
  const t1 = C.dark ? '#e8e8ea' : '#1c1c1e';
  const t3 = '#636366';
  const font = "'Outfit','Pretendard Variable','Pretendard','Noto Sans KR',system-ui,sans-serif";
  const divider = C.dark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)';

  return (
    <div
      className={className}
      style={{
        width,
        borderRadius: 12,
        overflow: 'hidden',
        ...glass,
        fontFamily: font,
        ...style,
      }}
    >
      {title && (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '11px 14px',
              cursor: collapsible ? 'pointer' : 'default',
            }}
            onClick={() => collapsible && setCollapsed((v) => !v)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {icon}
              <span style={{ fontSize: 13, fontWeight: 700, color: t1, letterSpacing: '-0.01em' }}>
                {title}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {headerRight}
              {collapsible && (
                <ChevronDown
                  size={15}
                  color={t3}
                  strokeWidth={2}
                  style={{ transform: collapsed ? 'rotate(-90deg)' : 'none', transition: 'transform .15s' }}
                />
              )}
            </div>
          </div>
          {!collapsed && <div style={{ height: 1, background: divider }} />}
        </>
      )}
      {!collapsed && <div>{children}</div>}
    </div>
  );
};
