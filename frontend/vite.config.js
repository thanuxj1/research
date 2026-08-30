import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: this app is served from a sub-path by the gateway (gateway.py at the
// repository root), which puts all three applications on one origin. Without
// it Vite emits asset URLs rooted at /, and the built page asks the gateway
// for /assets/... instead of /safety/assets/... -- a blank screen with 404s in
// the console. Harmless when running `npm run dev` directly.
export default defineConfig({
  base: '/safety/',
  plugins: [react()],
  server: {
    port: 3000,
    open: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/assistance': {
        target: 'http://51.20.34.58:5001',
        changeOrigin: true,
        secure: false,
      },
      '/budget_planner': {
        target: 'http://51.20.34.58:5001',
        changeOrigin: true,
        secure: false,
      },
      '/questions': {
        target: 'http://51.20.34.58:5001',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
