import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: this app is served from a sub-path by the gateway (gateway.py at the
// repository root), which puts all three applications on one origin. Without
// it Vite emits asset URLs rooted at /, and the built page asks the gateway
// for /assets/... instead of /food/assets/... -- a blank screen with 404s in
// the console. Harmless when running `npm run dev` directly.
export default defineConfig({
  base: '/food/',
  plugins: [react()],
  server: {
    port: 5173,
    // The API sets permissive CORS, so the client talks to it directly via
    // VITE_API_URL rather than through a dev proxy. That keeps dev and
    // production request paths identical.
    open: false,
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
