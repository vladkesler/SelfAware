import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server on :5173 (CORS-allowed by the backend). The WS URL is read from
// VITE_WS_URL at runtime (default ws://localhost:8000/ws) — no proxy needed.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
