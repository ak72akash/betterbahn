/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.VITE_BACKEND ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Eigene (leere) PostCSS-Konfiguration: verhindert, dass Vite eine postcss.config
  // aus einem übergeordneten Ordner aufgreift. Tailwind läuft über das Vite-Plugin.
  css: { postcss: { plugins: [] } },
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": { target: backend, changeOrigin: true, ws: true } },
  },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], globals: true, css: false },
});
