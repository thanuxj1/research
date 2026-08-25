import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
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
