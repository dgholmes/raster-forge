import { useState, useCallback, useEffect } from 'react';
import { DARK, LIGHT, type C } from '../design-system/tokens';

/* ============================================================================
 * useTheme — theme persistence + cross-tab sync.
 *
 * Ported/generalised from useThemeV6. Returns the resolved token object `C`
 * (DARK or LIGHT) so components never import DARK/LIGHT directly:
 *
 *   const { theme, toggle, C } = useTheme();
 *   <div style={{ background: C.appBg, color: C.t1 }} />
 * ========================================================================== */

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'dashboard-theme';

export interface UseThemeResult {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggle: () => void;
  /** Resolved token object for the current theme. */
  C: C;
}

function isTheme(v: unknown): v is Theme {
  return v === 'dark' || v === 'light';
}

export function useTheme(): UseThemeResult {
  // Dark is the default whenever there's no stored preference yet, AND
  // whenever the stored value is anything other than exactly 'dark'/'light'.
  // A loose `|| 'dark'` fallback only catches an empty value — any stray
  // invalid string in localStorage would silently resolve to light (anything
  // !== 'dark' maps to LIGHT below), so validate strictly instead.
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isTheme(stored) ? stored : 'dark';
  });

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    localStorage.setItem(STORAGE_KEY, t);
    // Broadcast so other open tabs stay in sync.
    window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY, newValue: t }));
  }, []);

  const toggle = useCallback(() => {
    setThemeState((prev) => {
      const next: Theme = prev === 'dark' ? 'light' : 'dark';
      localStorage.setItem(STORAGE_KEY, next);
      window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY, newValue: next }));
      return next;
    });
  }, []);

  // Listen for changes from other tabs/pages.
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && isTheme(e.newValue)) {
        setThemeState(e.newValue);
      }
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  return { theme, setTheme, toggle, C: theme === 'dark' ? DARK : LIGHT };
}
