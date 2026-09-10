import { API_CONFIG, WEBSOCKET_CONFIG } from '../config/config';

/* ============================================================================
 * websocket.ts — global WebSocket singleton with auto-reconnect.
 *
 * Ported/generalised from websocketManager. Reconnect limits come from
 * WEBSOCKET_CONFIG. Register typed listeners by message `type`:
 *
 *   websocketManager.addEventListener('my_event', (msg) => { ... });
 *
 * The default URL is read from localStorage('dashboard_connection_settings')
 * (operator override) else API_CONFIG.WEBSOCKET_URL.
 * ========================================================================== */

const SETTINGS_KEY = 'dashboard_connection_settings';

export type WsMessage = { type?: string; [k: string]: unknown };
export type WsListener = (msg: WsMessage) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = WEBSOCKET_CONFIG.MAX_RECONNECT_ATTEMPTS;
  private readonly reconnectDelay = WEBSOCKET_CONFIG.RECONNECT_DELAY;
  private listeners = new Map<string, WsListener[]>();
  private isConnecting = false;

  private resolveUrl(customUrl?: string): string {
    if (customUrl) return customUrl;
    try {
      const raw = localStorage.getItem(SETTINGS_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { websocketUrl?: string };
        if (parsed.websocketUrl) return parsed.websocketUrl;
      }
    } catch {
      /* fall through */
    }
    return API_CONFIG.WEBSOCKET_URL;
  }

  connect(customUrl?: string) {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) return;
    this.isConnecting = true;
    const url = this.resolveUrl(customUrl);

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.isConnecting = false;
        this.reconnectAttempts = 0;
      };

      this.ws.onmessage = (event) => {
        try {
          this.handleMessage(JSON.parse(event.data) as WsMessage);
        } catch (error) {
          console.error('WebSocket message parse error:', error);
        }
      };

      this.ws.onclose = (event) => {
        this.isConnecting = false;
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          setTimeout(() => this.connect(), this.reconnectDelay);
        }
      };

      this.ws.onerror = () => {
        this.isConnecting = false;
      };
    } catch (error) {
      console.error('WebSocket connection failed:', error);
      this.isConnecting = false;
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close(1000, 'User disconnect');
      this.ws = null;
    }
  }

  addEventListener(type: string, cb: WsListener) {
    const list = this.listeners.get(type) ?? [];
    list.push(cb);
    this.listeners.set(type, list);
  }

  removeEventListener(type: string, cb: WsListener) {
    const list = this.listeners.get(type);
    if (!list) return;
    const i = list.indexOf(cb);
    if (i > -1) list.splice(i, 1);
  }

  private handleMessage(data: WsMessage) {
    const type = data.type || 'message';
    this.listeners.get(type)?.forEach((cb) => {
      try {
        cb(data);
      } catch (error) {
        console.error('WebSocket handler error:', error);
      }
    });
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  getConnectionState(): 'connected' | 'connecting' | 'closing' | 'closed' | 'disconnected' {
    if (!this.ws) return 'disconnected';
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'connecting';
      case WebSocket.OPEN:
        return 'connected';
      case WebSocket.CLOSING:
        return 'closing';
      default:
        return 'closed';
    }
  }
}

export const websocketManager = new WebSocketManager();

// NOTE: auto-connect is intentionally NOT run on import in the template — enable
// it per project once your backend exposes a WS endpoint:
//   if (typeof window !== 'undefined') websocketManager.connect();
