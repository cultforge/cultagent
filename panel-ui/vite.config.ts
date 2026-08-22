import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/static/spa/",
  build: {
    outDir: path.resolve(__dirname, "../src/cultagent/web/static/spa"),
    emptyOutDir: true,
    assetsDir: "assets",
  },
  server: {
    proxy: {
      "/v1": "http://127.0.0.1:8720",
      "/ws": { target: "ws://127.0.0.1:8720", ws: true },
      "/static": "http://127.0.0.1:8720",
    },
  },
});
