/* ============================================================================
 * types/index.ts — generic shared types for the map dashboard shell.
 * Extend these per project; nothing here is domain-specific.
 * ========================================================================== */

import type { LucideIcon } from 'lucide-react';

/** Authenticated user returned by the backend `/auth/me` endpoint. */
export interface AuthUser {
  id: number | string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
}

/** Status severity used to colour markers/badges. Maps to STATUS tokens. */
export type ItemStatus = 'ok' | 'warn' | 'alert' | 'neutral';

/** A point rendered on the map. `meta` carries arbitrary domain fields. */
export interface MapMarkerItem {
  id: string;
  name: string;
  lat: number;
  lng: number;
  status?: ItemStatus;
  meta?: Record<string, unknown>;
}

/** A topbar navigation entry. */
export interface NavItem {
  label: string;
  path: string;
  icon?: LucideIcon;
}

/** Persisted connection override (localStorage 'dashboard_connection_settings'). */
export interface ConnectionSettings {
  apiBaseUrl: string;
  websocketUrl: string;
}

/** Backend reachability, polled by useBackendStatus. */
export type BackendStatus = 'online' | 'offline' | 'checking';
