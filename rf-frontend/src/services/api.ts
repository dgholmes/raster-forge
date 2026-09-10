import { API_CONFIG } from '../config/config';
import type { AuthUser, ConnectionSettings } from '../types';

/* ============================================================================
 * api.ts — generic REST client singleton.
 *
 * • Base URL is read at CALL TIME from localStorage('dashboard_connection_settings')
 *   (operator override) else API_CONFIG.API_BASE_URL — so runtime URL changes take
 *   effect immediately without a rebuild.
 * • Bearer token persisted in sessionStorage('auth_token').
 * • 401 responses fire the registered unauthorized handler (AuthContext logs out).
 *
 * Add your domain endpoints by calling this.get()/this.post() from new methods.
 * ========================================================================== */

export interface LoginResponse {
  access_token: string;
  user: AuthUser;
}

const TOKEN_KEY = 'auth_token';
const SETTINGS_KEY = 'dashboard_connection_settings';

/** Resolve the active API base URL (operator override → config default). */
export function getApiBaseUrl(): string {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ConnectionSettings>;
      if (parsed.apiBaseUrl) return parsed.apiBaseUrl.replace(/\/$/, '');
    }
  } catch {
    /* fall through to default */
  }
  return API_CONFIG.API_BASE_URL.replace(/\/$/, '');
}

class ApiService {
  private token: string | null = null;
  private unauthorizedHandler: (() => void) | null = null;

  constructor() {
    const saved = sessionStorage.getItem(TOKEN_KEY);
    if (saved) this.token = saved;
  }

  setToken(token: string) {
    this.token = token;
    sessionStorage.setItem(TOKEN_KEY, token);
  }

  logout() {
    this.token = null;
    sessionStorage.removeItem(TOKEN_KEY);
  }

  getAuthHeader(): string {
    return this.token ? `Bearer ${this.token}` : '';
  }

  /** Registered by AuthContext so the api layer can trigger logout on 401. */
  setUnauthorizedHandler(handler: () => void) {
    this.unauthorizedHandler = handler;
  }

  private getHeaders(extra?: HeadersInit): HeadersInit {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    return { ...headers, ...(extra as Record<string, string>) };
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${getApiBaseUrl()}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: this.getHeaders(options.headers),
    });

    if (response.status === 401) {
      this.unauthorizedHandler?.();
      const err = await response.json().catch(() => ({ error: 'Authentication required.' }));
      throw new Error(err.error || 'Authentication required.');
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
      throw new Error(err.error || `HTTP error! status: ${response.status}`);
    }

    // Some endpoints (logout, health) may return an empty body.
    const text = await response.text();
    if (!text) return undefined as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new Error('Invalid response format');
    }
  }

  /* ── Generic helpers ──────────────────────────────────────────────────── */

  get<T = unknown>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  post<T = unknown>(endpoint: string, body?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  patch<T = unknown>(endpoint: string, body?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  delete<T = unknown>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  /** Absolute URL for a download link (the browser navigates to it directly). */
  url(endpoint: string): string {
    return `${getApiBaseUrl()}${endpoint}`;
  }

  /** Fetch a protected file and hand the browser a blob download.
   *  A plain <a href> cannot carry the Authorization header. */
  async download(endpoint: string, filename: string): Promise<void> {
    const res = await fetch(`${getApiBaseUrl()}${endpoint}`, {
      headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(err.error || `Download failed (${res.status})`);
    }
    const blob = await res.blob();
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(href);
  }

  /** Multipart upload with progress.
   *  Uses XMLHttpRequest rather than fetch: fetch cannot report upload
   *  progress, and these files are gigabytes. */
  upload<T = unknown>(
    endpoint: string,
    form: FormData,
    onProgress?: (percent: number, loaded: number, total: number) => void,
    signal?: AbortSignal,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${getApiBaseUrl()}${endpoint}`);
      if (this.token) xhr.setRequestHeader('Authorization', `Bearer ${this.token}`);

      xhr.upload.onprogress = (e) => {
        if (onProgress && e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100), e.loaded, e.total);
        }
      };

      xhr.onload = () => {
        if (xhr.status === 401) this.unauthorizedHandler?.();
        let body: unknown = undefined;
        try {
          body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
        } catch {
          /* non-JSON error body */
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(body as T);
        } else {
          const message =
            (body as { error?: string } | undefined)?.error || `Upload failed (${xhr.status})`;
          reject(new Error(message));
        }
      };

      xhr.onerror = () => reject(new Error('Upload failed: the server could not be reached.'));
      xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'));
      signal?.addEventListener('abort', () => xhr.abort());

      xhr.send(form);
    });
  }

  /* ── Auth ─────────────────────────────────────────────────────────────── */

  async login(username: string, password: string): Promise<LoginResponse> {
    const res = await this.request<LoginResponse>(API_CONFIG.ENDPOINTS.LOGIN, {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    if (res?.access_token) this.setToken(res.access_token);
    return res;
  }

  getMe(): Promise<AuthUser> {
    return this.request<AuthUser>(API_CONFIG.ENDPOINTS.ME, { method: 'GET' });
  }

  async logoutServer(): Promise<void> {
    try {
      await this.request(API_CONFIG.ENDPOINTS.LOGOUT, { method: 'POST' });
    } catch {
      /* logout is best-effort */
    } finally {
      this.logout();
    }
  }

  /* ── Health ───────────────────────────────────────────────────────────── */

  getHealth(): Promise<{ status?: string }> {
    return this.request<{ status?: string }>(API_CONFIG.ENDPOINTS.HEALTH, { method: 'GET' });
  }
}

export const apiService = new ApiService();
