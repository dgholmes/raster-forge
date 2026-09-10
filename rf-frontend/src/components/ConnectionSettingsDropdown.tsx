import React, { useState } from 'react';
import { Settings, RotateCcw, X, Wifi } from 'lucide-react';
import { mapGlass, type C } from '../design-system/tokens';
import { API_CONFIG } from '../config/config';
import { apiService } from '../services/api';
import type { ConnectionSettings } from '../types';

/* ============================================================================
 * ConnectionSettingsDropdown — glassmorphism popover to override the API + WS
 * URLs at runtime (persisted to localStorage 'dashboard_connection_settings').
 * A "Test" button probes the health endpoint with the entered API URL.
 * ========================================================================== */

const STORAGE_KEY = 'dashboard_connection_settings';

function loadSettings(): ConnectionSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as ConnectionSettings;
  } catch {
    /* ignore */
  }
  return { apiBaseUrl: API_CONFIG.API_BASE_URL, websocketUrl: API_CONFIG.WEBSOCKET_URL };
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  C: C;
  onSettingsChange?: (settings: ConnectionSettings) => void;
}

type TestState = 'idle' | 'testing' | 'ok' | 'fail';

export const ConnectionSettingsDropdown: React.FC<Props> = ({
  isOpen,
  onClose,
  C,
  onSettingsChange,
}) => {
  const [settings, setSettings] = useState<ConnectionSettings>(loadSettings);
  const [isValid, setIsValid] = useState(true);
  const [test, setTest] = useState<TestState>('idle');

  if (!isOpen) return null;

  const glass = mapGlass(C.dark);
  const font = "'Outfit','Pretendard Variable','Pretendard','Noto Sans KR',system-ui,sans-serif";
  const accent = C.accent;
  const infoBg = C.dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)';
  const secBg = C.pill;
  const secBdr = C.dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.10)';

  const validateUrl = (url: string) => {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  };

  const update = (key: keyof ConnectionSettings, value: string) => {
    setSettings((s) => {
      const next = { ...s, [key]: value };
      // Auto-derive WS URL from API URL when the API field changes.
      if (key === 'apiBaseUrl') {
        try {
          const u = new URL(value);
          const proto = u.protocol === 'https:' ? 'wss:' : 'ws:';
          next.websocketUrl = `${proto}//${u.host}/ws`;
        } catch {
          /* leave WS as-is until API URL is valid */
        }
      }
      return next;
    });
    setTest('idle');
  };

  const handleTest = async () => {
    if (!validateUrl(settings.apiBaseUrl)) {
      setIsValid(false);
      return;
    }
    setTest('testing');
    try {
      const base = settings.apiBaseUrl.replace(/\/$/, '');
      const res = await fetch(`${base}${API_CONFIG.ENDPOINTS.HEALTH}`);
      setTest(res.ok ? 'ok' : 'fail');
    } catch {
      setTest('fail');
    }
  };

  const handleConnect = () => {
    if (!validateUrl(settings.apiBaseUrl) || !validateUrl(settings.websocketUrl)) {
      setIsValid(false);
      return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    onSettingsChange?.(settings);
    onClose();
  };

  const handleReset = () => {
    const def: ConnectionSettings = {
      apiBaseUrl: API_CONFIG.API_BASE_URL,
      websocketUrl: API_CONFIG.WEBSOCKET_URL,
    };
    setSettings(def);
    localStorage.removeItem(STORAGE_KEY);
    setTest('idle');
    setIsValid(true);
    onSettingsChange?.(def);
  };

  const inp: React.CSSProperties = {
    width: '100%',
    padding: '7px 10px',
    borderRadius: 7,
    fontSize: 13,
    fontFamily: font,
    color: C.t1,
    background: C.inp,
    border: `1px solid ${isValid ? C.inpB : '#ff453a'}`,
    outline: 'none',
    transition: 'border-color .12s',
  };

  const lbl: React.CSSProperties = {
    display: 'block',
    fontSize: 10,
    fontWeight: 700,
    color: C.t3,
    marginBottom: 5,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    fontFamily: font,
  };

  const secBtn: React.CSSProperties = {
    height: 30,
    borderRadius: 7,
    background: secBg,
    border: `1px solid ${secBdr}`,
    color: C.t2,
    cursor: 'pointer',
    fontFamily: font,
    fontSize: 12,
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  };

  const testLabel =
    test === 'testing' ? 'Testing…' : test === 'ok' ? 'Connected' : test === 'fail' ? 'Failed' : 'Test';
  const testColor = test === 'ok' ? '#30d158' : test === 'fail' ? '#ff453a' : C.t2;

  return (
    <div
      style={{
        position: 'fixed',
        top: 56,
        right: 8,
        zIndex: 1200,
        width: 300,
        borderRadius: 12,
        overflow: 'hidden',
        ...glass,
        fontFamily: font,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 14px 10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <Settings size={13} color={C.t3} strokeWidth={1.8} />
          <span style={{ fontSize: 13, fontWeight: 700, color: C.t1, letterSpacing: '-0.01em' }}>
            Connection
          </span>
        </div>
        <button
          onClick={onClose}
          style={{
            width: 24,
            height: 24,
            borderRadius: 6,
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: C.t3,
          }}
        >
          <X size={13} strokeWidth={2} />
        </button>
      </div>

      <div style={{ height: 1, background: secBdr, margin: '0 14px' }} />

      <div style={{ padding: '12px 14px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={lbl}>API Base URL</label>
          <input
            type="text"
            value={settings.apiBaseUrl}
            onChange={(e) => update('apiBaseUrl', e.target.value)}
            style={inp}
            placeholder="http://localhost:9005"
            onFocus={(e) => (e.target.style.borderColor = accent)}
            onBlur={(e) => (e.target.style.borderColor = isValid ? C.inpB : '#ff453a')}
          />
        </div>

        <div>
          <label style={lbl}>WebSocket URL</label>
          <input
            type="text"
            value={settings.websocketUrl}
            onChange={(e) => update('websocketUrl', e.target.value)}
            style={inp}
            placeholder="ws://localhost:9005/ws"
            onFocus={(e) => (e.target.style.borderColor = accent)}
            onBlur={(e) => (e.target.style.borderColor = C.inpB)}
          />
        </div>

        <div
          style={{
            background: infoBg,
            borderRadius: 7,
            padding: '9px 11px',
            fontSize: 12,
            color: C.t3,
            lineHeight: 1.5,
          }}
        >
          • Changing the API URL auto-derives the WebSocket URL.
          <br />• Settings persist across restarts (localStorage).
        </div>

        <div style={{ display: 'flex', gap: 7 }}>
          <button
            onClick={handleConnect}
            style={{
              flex: 1,
              height: 30,
              borderRadius: 7,
              background: accent,
              border: 'none',
              color: '#fff',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              fontFamily: font,
            }}
          >
            Save
          </button>
          <button onClick={handleTest} style={{ ...secBtn, padding: '0 11px', color: testColor }}>
            <Wifi size={12} strokeWidth={1.8} />
            {testLabel}
          </button>
          <button onClick={handleReset} title="Reset to defaults" style={{ ...secBtn, width: 32 }}>
            <RotateCcw size={12} strokeWidth={1.8} />
          </button>
        </div>
      </div>
    </div>
  );
};

/** Re-notify the api layer of the current settings (called after Save). */
export function applyConnectionSettings(_settings: ConnectionSettings) {
  // apiService reads localStorage at call time, so nothing to push here.
  // Kept as an extension point for e.g. reconnecting the websocket.
  void _settings;
  void apiService;
}
