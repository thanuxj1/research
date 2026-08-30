import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// This app is now the main portal, served at / by gateway.py.
// base must be '/' so asset URLs are rooted correctly.
export default defineConfig({
  base: "/",
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 3000,
    open: true,
    proxy: {
      "/assistance":    { target: "http://51.20.34.58:5001", changeOrigin: true },
      "/budget_planner":{ target: "http://51.20.34.58:5001", changeOrigin: true },
      "/questions":     { target: "http://51.20.34.58:5001", changeOrigin: true },
      "/travellens":    { target: "http://127.0.0.1:8080",   changeOrigin: true },
      "/food":          { target: "http://127.0.0.1:8080",   changeOrigin: true },
    },
  },
});
