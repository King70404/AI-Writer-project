import { createRequire } from "node:module";

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const resolveFromFrontend = createRequire(import.meta.url).resolve;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      {
        find: "eslint",
        replacement: resolveFromFrontend("eslint"),
      },
      {
        find: "react/jsx-dev-runtime",
        replacement: resolveFromFrontend("react/jsx-dev-runtime"),
      },
      {
        find: "react/jsx-runtime",
        replacement: resolveFromFrontend("react/jsx-runtime"),
      },
      {
        find: "react",
        replacement: resolveFromFrontend("react"),
      },
      {
        find: "react-router",
        replacement: resolveFromFrontend("react-router"),
      },
      {
        find: "@testing-library/react",
        replacement: resolveFromFrontend("@testing-library/react"),
      },
      {
        find: "@testing-library/user-event",
        replacement: resolveFromFrontend("@testing-library/user-event"),
      },
    ],
  },
  server: {
    fs: {
      allow: [".."],
    },
  },
  test: {
    environment: "jsdom",
    environmentOptions: {
      jsdom: {
        url: "http://localhost/",
      },
    },
    setupFiles: ["./src/test/setup.ts"],
    include: [
      "../tests/frontend/**/*.test.{ts,tsx}",
      "./tests/**/*.test.{ts,tsx}",
    ],
    clearMocks: true,
    mockReset: true,
    restoreMocks: true,
    coverage: {
      provider: "v8",
      reportsDirectory: "./coverage",
      reporter: ["text", "json-summary"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/test/**", "src/vite-env.d.ts", "tests/**"],
      thresholds: {
        statements: 80,
        branches: 75,
        functions: 80,
        lines: 80,
      },
    },
  },
});
