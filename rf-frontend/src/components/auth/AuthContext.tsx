import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { apiService } from '../../services/api';
import type { AuthUser } from '../../types';

/* ============================================================================
 * AuthContext — generic auth provider.
 *
 * • VITE_AUTH_ENABLED=false → auth is a pass-through (no login required).
 * • VITE_DEMO_MODE=true     → any username/password logs in as a local demo
 *   user WITHOUT hitting a backend (great for previewing the template).
 * • Otherwise               → real login/getMe/logout against the API.
 *
 * Registers a 401 handler with apiService so an expired token logs the user out.
 * ========================================================================== */

const AUTH_ENABLED = import.meta.env.VITE_AUTH_ENABLED === 'true';
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

const DEMO_USER: AuthUser = {
  id: 0,
  username: 'demo',
  email: 'demo@example.com',
  role: 'admin',
  is_active: true,
};

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  authEnabled: boolean;
  demoMode: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const logoutRef = useRef<() => void>(() => {});

  const logout = useCallback(() => {
    apiService.logout();
    setUser(null);
  }, []);

  // Keep the ref in sync so the api.ts 401 interceptor can call it.
  useEffect(() => {
    logoutRef.current = logout;
    apiService.setUnauthorizedHandler(logout);
  }, [logout]);

  const refreshUser = useCallback(async () => {
    if (DEMO_MODE) return;
    try {
      const me = await apiService.getMe();
      setUser(me);
    } catch {
      setUser(null);
      apiService.logout();
    }
  }, []);

  // On mount: resolve initial auth state.
  useEffect(() => {
    // Auth disabled → nobody needs to log in; don't block rendering.
    if (!AUTH_ENABLED) {
      setIsLoading(false);
      return;
    }
    // Demo mode → restore a demo session if a token flag exists.
    if (DEMO_MODE) {
      if (sessionStorage.getItem('auth_token')) setUser(DEMO_USER);
      setIsLoading(false);
      return;
    }
    // Real mode → validate any stored token.
    if (!sessionStorage.getItem('auth_token')) {
      setIsLoading(false);
      return;
    }
    refreshUser().finally(() => setIsLoading(false));
  }, [refreshUser]);

  const login = useCallback(async (username: string, password: string) => {
    if (DEMO_MODE) {
      // Accept any credentials; store a marker token so refresh persists.
      apiService.setToken('demo-token');
      setUser({ ...DEMO_USER, username: username || DEMO_USER.username });
      void password;
      return;
    }
    await apiService.login(username, password);
    const me = await apiService.getMe();
    setUser(me);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: AUTH_ENABLED ? !!user : true,
        isLoading,
        authEnabled: AUTH_ENABLED,
        demoMode: DEMO_MODE,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
