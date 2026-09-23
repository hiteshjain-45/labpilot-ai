import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8000. Proxying /api keeps the browser on one origin (no CORS setup needed).
const backend = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: backend, changeOrigin: true } } },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["tests/**/*.test.jsx"],
    testTimeout: 30000,
    env: { VITE_API_URL: process.env.SMOKE_API_URL || "http://127.0.0.1:8000" },
  },
  preview: { port: 4173, proxy: { "/api": { target: backend, changeOrigin: true } } },
});
