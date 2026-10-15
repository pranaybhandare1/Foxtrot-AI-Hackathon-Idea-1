import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `make om-dev` serves the UI on :5174 and proxies /api to the API on :8770.
// Prod: `make om` builds into dist/, which the API serves directly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8770" },
  },
  build: {
    chunkSizeWarningLimit: 2000, // echarts is large; the app is local-only so a single chunk is fine
  },
});
