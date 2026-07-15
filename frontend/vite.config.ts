import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const defaultBackendOrigin = "http://127.0.0.1:8000";

function resolveBackendOrigin(): string {
  const configuredOrigin = process.env.AIWEBNOVEL_VITE_BACKEND_URL;
  if (configuredOrigin === undefined) {
    return defaultBackendOrigin;
  }

  let parsedOrigin: URL;
  try {
    parsedOrigin = new URL(configuredOrigin);
  } catch {
    throw new Error(
      "AIWEBNOVEL_VITE_BACKEND_URL must be a valid loopback HTTP origin.",
    );
  }

  const port = Number(parsedOrigin.port);
  const isAllowedOrigin =
    parsedOrigin.protocol === "http:" &&
    parsedOrigin.hostname === "127.0.0.1" &&
    parsedOrigin.username === "" &&
    parsedOrigin.password === "" &&
    parsedOrigin.pathname === "/" &&
    parsedOrigin.search === "" &&
    parsedOrigin.hash === "" &&
    Number.isInteger(port) &&
    port >= 1 &&
    port <= 65_535;

  if (!isAllowedOrigin) {
    throw new Error(
      "AIWEBNOVEL_VITE_BACKEND_URL must use http://127.0.0.1 with an explicit valid port.",
    );
  }

  return parsedOrigin.origin;
}

const disableE2EHmr = process.env.AIWEBNOVEL_E2E_DISABLE_HMR === "1";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    hmr: disableE2EHmr ? false : undefined,
    proxy: {
      "/api": {
        target: resolveBackendOrigin(),
        changeOrigin: false,
        ws: false,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
  },
  build: {
    outDir: "dist",
  },
});
