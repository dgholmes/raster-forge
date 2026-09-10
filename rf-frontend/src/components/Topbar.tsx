import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Sun, Moon, MapPin, LogOut, ChevronDown } from 'lucide-react';
import { type C } from '../design-system/tokens';
import { APP } from '../config/config';
import { ConnectionSettingsDropdown } from './ConnectionSettingsDropdown';
import { useAuth } from './auth/AuthContext';
import type { BackendStatus, NavItem } from '../types';

/* ============================================================================
 * Topbar — shared across all pages. ~52px fixed height, glass over the map.
 *
 * Left:   logo (APP.logo or MapPin) + system name.
 * Nav:    NavItem[] with active state from useLocation.
 * Right:  backend status dot + Connection dropdown, theme toggle, and (when
 *         auth enabled) an account menu with logout.
 * ========================================================================== */

interface Props {
  C: C;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  nav: NavItem[];
  backendStatus: BackendStatus;
  /** Absolute-position over the map (true) or sticky in flow (false). */
  overlay?: boolean;
}

export const Topbar: React.FC<Props> = ({
  C,
  theme,
  onToggleTheme,
  nav,
  backendStatus,
  overlay = false,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { authEnabled, isAuthenticated, user, logout } = useAuth();
  const [showConn, setShowConn] = useState(false);
  const [showAcct, setShowAcct] = useState(false);

  const font = "'Outfit','Pretendard Variable','Pretendard','Noto Sans KR',system-ui,sans-serif";
  const isDark = theme === 'dark';
  const bg = isDark ? 'rgba(8,11,16,0.82)' : 'rgba(248,248,250,0.88)';
  const border = isDark ? 'rgba(255,255,255,0.09)' : 'rgba(0,0,0,0.08)';
  const rowHov = C.row;
  const statusColor =
    backendStatus === 'online' ? '#30d158' : backendStatus === 'checking' ? '#ff9f0a' : '#ff453a';
  const statusLabel =
    backendStatus === 'online' ? 'Connected' : backendStatus === 'checking' ? 'Checking…' : 'Offline';

  const posStyle: React.CSSProperties = overlay
    ? { position: 'absolute', top: 0, left: 0, right: 0 }
    : { position: 'sticky', top: 0 };

  return (
    <header
      style={{
        ...posStyle,
        height: 52,
        zIndex: 1100,
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        gap: 8,
        background: bg,
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderBottom: `1px solid ${border}`,
        fontFamily: font,
      }}
    >
      {/* Logo + name */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {import.meta.env.VITE_APP_LOGO_URL ? (
          <img src={import.meta.env.VITE_APP_LOGO_URL} alt="" style={{ height: 22, width: 'auto' }} />
        ) : (
          <MapPin size={18} color={C.accent} strokeWidth={2.2} />
        )}
        <span style={{ fontSize: 14, fontWeight: 700, color: C.t1, letterSpacing: '-0.01em' }}>
          {APP.name}
        </span>
      </div>

      {/* Nav */}
      <nav style={{ display: 'flex', gap: 2, marginLeft: 18 }}>
        {nav.map(({ label, path, icon: Icon }) => {
          const active = location.pathname === path;
          return (
            <button
              key={path}
              onClick={() => navigate(path)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '5px 12px',
                borderRadius: 6,
                fontSize: 13,
                fontWeight: active ? 600 : 400,
                color: active ? C.t1 : C.t3,
                background: active ? C.activeBg : 'transparent',
                border: 'none',
                cursor: 'pointer',
                fontFamily: font,
                transition: 'background .12s,color .12s',
              }}
              onMouseEnter={(e) => {
                if (!active) e.currentTarget.style.background = rowHov;
              }}
              onMouseLeave={(e) => {
                if (!active) e.currentTarget.style.background = 'transparent';
              }}
            >
              {Icon && <Icon size={14} strokeWidth={1.9} />}
              {label}
            </button>
          );
        })}
      </nav>

      <div style={{ flex: 1 }} />

      {/* Backend status + connection settings */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, position: 'relative' }}>
        <span
          style={{
            position: 'relative',
            width: 9,
            height: 9,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          {backendStatus === 'online' && (
            <span
              style={{
                position: 'absolute',
                inset: 0,
                borderRadius: '50%',
                background: '#30d158',
                opacity: 0.7,
                animation: 'md-ping 1.5s ease infinite',
              }}
            />
          )}
          <span
            style={{ width: 9, height: 9, borderRadius: '50%', background: statusColor, display: 'block', position: 'relative' }}
          />
        </span>
        <button
          onClick={() => setShowConn((v) => !v)}
          style={{
            fontSize: 12,
            fontWeight: 500,
            color: C.t2,
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            fontFamily: font,
            padding: '4px 8px',
            borderRadius: 6,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = rowHov)}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        >
          {statusLabel}
        </button>
        <ConnectionSettingsDropdown isOpen={showConn} onClose={() => setShowConn(false)} C={C} />
      </div>

      <div style={{ width: 1, height: 16, background: border }} />

      {/* Theme toggle — single button, icon reflects the current mode. (An
          earlier version of this was a two-button segmented Moon|Sun
          control; a single button reads faster at a glance and is less
          topbar real estate — prefer this unless a project specifically
          wants both options visible at once.) */}
      <button
        onClick={onToggleTheme}
        title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        style={{
          width: 28,
          height: 28,
          borderRadius: 6,
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: C.t2,
          transition: 'background .12s',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = rowHov)}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
      >
        {isDark ? <Moon size={15} strokeWidth={1.9} /> : <Sun size={15} strokeWidth={1.9} />}
      </button>

      {/* Account menu (auth enabled) */}
      {authEnabled && isAuthenticated && (
        <>
          <div style={{ width: 1, height: 16, background: border }} />
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setShowAcct((v) => !v)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '5px 8px',
                borderRadius: 7,
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                fontFamily: font,
                color: C.t1,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = rowHov)}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <span
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: C.accent,
                  color: '#fff',
                  fontSize: 12,
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {(user?.username || '?').charAt(0).toUpperCase()}
              </span>
              <span style={{ fontSize: 13, fontWeight: 500 }}>{user?.username}</span>
              <ChevronDown size={13} color={C.t3} strokeWidth={2} />
            </button>
            {showAcct && (
              <div
                style={{
                  position: 'absolute',
                  top: 40,
                  right: 0,
                  width: 180,
                  borderRadius: 10,
                  background: C.card,
                  border: `1px solid ${C.cardB}`,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
                  overflow: 'hidden',
                  zIndex: 1200,
                }}
              >
                <div style={{ padding: '10px 12px', borderBottom: `1px solid ${C.b}` }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: C.t1 }}>{user?.username}</div>
                  <div style={{ fontSize: 11, color: C.t3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {user?.role}
                  </div>
                </div>
                <button
                  onClick={() => {
                    setShowAcct(false);
                    logout();
                    navigate('/login');
                  }}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '9px 12px',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: font,
                    fontSize: 13,
                    color: '#ff453a',
                    textAlign: 'left',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = rowHov)}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <LogOut size={14} strokeWidth={1.9} />
                  Sign out
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </header>
  );
};
