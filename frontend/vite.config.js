import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend for /assistance, /budget_planner and /questions.
// Run with BACKEND_URL=http://127.0.0.1:5001 to use a local backend instead of AWS.
const BACKEND_URL = process.env.BACKEND_URL || 'http://54.234.54.197:5001'

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
        target: BACKEND_URL,
        changeOrigin: true,
        secure: false,
      },
      '/budget_planner': {
        target: BACKEND_URL,
        changeOrigin: true,
        secure: false,
      },
      '/questions': {
        target: BACKEND_URL,
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
