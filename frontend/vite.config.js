import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
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
