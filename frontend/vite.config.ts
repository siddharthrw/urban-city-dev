import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The dev server proxies API calls to the FastAPI backend, so the browser only talks to one origin.
const API = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // MapLibre 6 loads its web worker from a file next to its main module; pre-bundling breaks that path.
  optimizeDeps: { exclude: ["maplibre-gl"] },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": API,
      "/health": API,
    },
  },
});
