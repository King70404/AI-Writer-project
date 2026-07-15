import type { PlaywrightTestConfig } from "@playwright/test";

type E2EMode = "development" | "integrated";

interface E2EConfigOptions {
  defaultBaseURL: string;
  mode: E2EMode;
  testMatch?: string | string[];
}

function resolveBaseURL(defaultBaseURL: string): string {
  const configuredBaseURL =
    process.env.AIWEBNOVEL_E2E_BASE_URL ?? defaultBaseURL;

  let parsedBaseURL: URL;
  try {
    parsedBaseURL = new URL(configuredBaseURL);
  } catch {
    throw new Error(
      "AIWEBNOVEL_E2E_BASE_URL must be a valid loopback HTTP origin.",
    );
  }

  const port = Number(parsedBaseURL.port);
  const isAllowedOrigin =
    parsedBaseURL.protocol === "http:" &&
    parsedBaseURL.hostname === "127.0.0.1" &&
    parsedBaseURL.username === "" &&
    parsedBaseURL.password === "" &&
    parsedBaseURL.pathname === "/" &&
    parsedBaseURL.search === "" &&
    parsedBaseURL.hash === "" &&
    Number.isInteger(port) &&
    port >= 1 &&
    port <= 65_535;

  if (!isAllowedOrigin) {
    throw new Error(
      "AIWEBNOVEL_E2E_BASE_URL must use http://127.0.0.1 with an explicit valid port.",
    );
  }

  return parsedBaseURL.origin;
}

export function createE2EConfig({
  defaultBaseURL,
  mode,
  testMatch = `${mode}/**/*.spec.ts`,
}: E2EConfigOptions): PlaywrightTestConfig {
  return {
    testDir: "../tests/e2e",
    testMatch,
    outputDir: `playwright-results/${mode}`,
    fullyParallel: false,
    forbidOnly: true,
    retries: 0,
    workers: 1,
    timeout: 30_000,
    expect: {
      timeout: 7_500,
    },
    reporter: [
      ["line"],
      [
        "html",
        {
          open: "never",
          outputFolder: `playwright-report/${mode}`,
        },
      ],
    ],
    use: {
      acceptDownloads: false,
      baseURL: resolveBaseURL(defaultBaseURL),
      headless: true,
      ignoreHTTPSErrors: false,
      permissions: [],
      screenshot: "only-on-failure",
      serviceWorkers: "block",
      trace: "retain-on-failure",
      video: "off",
    },
    projects: [
      {
        name: "chromium",
        use: {
          browserName: "chromium",
        },
      },
    ],
  };
}
