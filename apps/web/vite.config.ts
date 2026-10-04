import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const api = process.env.HAMSA_API ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": { target: api, ws: true, changeOrigin: true } },
  },
  test: { environment: "node" },
});
