import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// ONE place for the URL scheme: `base` here is also what the router uses as its basename
// (via import.meta.env.BASE_URL). Default '/'. Override with VITE_BASE=/sitwise/ if it ever moves.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
  build: {
    // Vercel serves static files from /public (Flask preset), so the dashboard builds there.
    outDir: '../public',
    emptyOutDir: true,
  },
  server: {
    // The dashboard calls /api on its own origin, so there's no CORS in dev or prod.
    proxy: {
      '/api': process.env.API_PROXY ?? 'http://127.0.0.1:5001',
      // Dev-only: the Camera page's Python model (scripts/model_server.py). Frames stay on this machine.
      '/local-model': {
        target: process.env.MODEL_PROXY ?? 'http://127.0.0.1:5002',
        rewrite: (path) => path.replace(/^\/local-model/, ''),
      },
    },
  },
})
