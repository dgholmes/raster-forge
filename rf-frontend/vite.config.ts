import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Dev-server proxy config.
 *
 * '/2Dtile' → ortho tile upstream (default http://localhost:9000). On HTTPS pages
 *   resolveOrthoTileBase() returns '/2Dtile' to avoid mixed-content blocking; this
 *   proxy forwards those requests to the real (HTTP) tile server during dev.
 * '/api'    → backend REST API (default http://localhost:9005).
 *
 * changeOrigin keeps closed-network / self-signed tile servers happy.
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const orthoUpstream = env.VITE_ORTHO_TILE_UPSTREAM || 'http://localhost:9000';
  const apiUpstream = env.VITE_API_BASE_URL || 'http://localhost:9005';

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/2Dtile': {
          target: orthoUpstream,
          changeOrigin: true,
          secure: false,
        },
        '/api': {
          target: apiUpstream,
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});
