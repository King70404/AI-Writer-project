import type {
  BrowserContext,
  Page,
  Request,
  Response,
  TestInfo,
} from "@playwright/test";

export const HEALTH_LIVE_PATH = "/api/v1/health/live";
export const HEALTH_READY_PATH = "/api/v1/health/ready";

export type AuditEventType = "request" | "response" | "request-failed";

export interface AuditEvent {
  readonly type: AuditEventType;
  readonly method: string;
  readonly path: string;
  readonly status?: number;
}

export interface AuditedResponse {
  readonly method: string;
  readonly path: string;
  readonly status: number;
  readonly contentType: string | null;
  readonly requestId: string | null;
}

export interface BrowserAudit {
  readonly allowedOrigin: string;
  readonly events: AuditEvent[];
  readonly responses: AuditedResponse[];
  readonly externalAttempts: string[];
  readonly consoleErrors: string[];
  readonly reviewedConsoleErrors: string[];
  readonly pageErrors: string[];
  readonly unexpectedRequestFailures: string[];
  readonly unexpectedDownloads: string[];
  readonly unexpectedCookies: string[];
  readonly allowOneExpectedHealthCancellation: () => void;
  readonly allowOneExpectedLocalCancellation: (path: string) => void;
  readonly allowOneExpectedSessionCookie: () => void;
  readonly allowOneExpectedManuscriptDownload: (filename: string) => void;
  readonly allowExpectedConsoleHttpFailure: (
    path: string,
    status: number,
  ) => void;
}

interface LocalEndpoint {
  readonly origin: string;
  readonly hostname: "127.0.0.1";
  readonly port: string;
}

const INSTALLED_PAGE_GUARDS = new WeakSet<Page>();

interface ExpectedConsoleHttpFailure {
  readonly path: string;
  readonly status: number;
}

export function parseLocalEndpoint(
  value: string,
  label: string,
): LocalEndpoint {
  let endpoint: URL;
  try {
    endpoint = new URL(value);
  } catch {
    throw new Error(`${label} must be an absolute URL.`);
  }

  if (
    endpoint.protocol !== "http:" ||
    endpoint.hostname !== "127.0.0.1" ||
    endpoint.port.length === 0 ||
    endpoint.username.length > 0 ||
    endpoint.password.length > 0 ||
    endpoint.pathname !== "/" ||
    endpoint.search.length > 0 ||
    endpoint.hash.length > 0
  ) {
    throw new Error(
      `${label} must be an explicit http://127.0.0.1:<port> origin.`,
    );
  }

  return {
    origin: endpoint.origin,
    hostname: "127.0.0.1",
    port: endpoint.port,
  };
}

export function requiredLocalEnvironmentUrl(name: string): string {
  const value = process.env[name]?.trim();
  if (value === undefined || value.length === 0) {
    throw new Error(`${name} is required for this E2E mode.`);
  }
  return parseLocalEndpoint(value, name).origin;
}

function safeTarget(rawUrl: string): string {
  try {
    const target = new URL(rawUrl);
    if (target.protocol === "file:") {
      return "file://<blocked-local-path>";
    }
    if (!["http:", "https:", "ws:", "wss:"].includes(target.protocol)) {
      return `${target.protocol}<blocked>`;
    }
    const port = target.port.length > 0 ? `:${target.port}` : "";
    return `${target.protocol}//${target.hostname}${port}${target.pathname}`;
  } catch {
    return "<invalid-url>";
  }
}

function sanitizeDiagnostic(message: string): string {
  return message
    .replace(/(?:https?|wss?|file):\/\/[^\s'"<>]+/giu, (value) =>
      safeTarget(value),
    )
    .replace(/\b[A-Za-z]:[\\/][^\s'"<>]*/gu, "<local-path>")
    .slice(0, 1_000);
}

function pathOnly(rawUrl: string): string {
  try {
    return new URL(rawUrl).pathname;
  } catch {
    return "<invalid-path>";
  }
}

function isAllowedHttp(rawUrl: string, endpoint: LocalEndpoint): boolean {
  try {
    const target = new URL(rawUrl);
    return target.protocol === "http:" && target.origin === endpoint.origin;
  } catch {
    return false;
  }
}

function isAllowedWebSocket(rawUrl: string, endpoint: LocalEndpoint): boolean {
  try {
    const target = new URL(rawUrl);
    return (
      target.protocol === "ws:" &&
      target.hostname === endpoint.hostname &&
      target.port === endpoint.port &&
      target.username.length === 0 &&
      target.password.length === 0
    );
  } catch {
    return false;
  }
}

function isExpectedLocalHealthCancellation(
  request: Request,
  endpoint: LocalEndpoint,
  remainingAllowances: { count: number },
): boolean {
  const failure = request.failure()?.errorText ?? "";
  const path = pathOnly(request.url());
  const expected =
    remainingAllowances.count > 0 &&
    isAllowedHttp(request.url(), endpoint) &&
    (path === HEALTH_LIVE_PATH || path === HEALTH_READY_PATH) &&
    /(?:ERR_ABORTED|NS_BINDING_ABORTED|cancelled)/iu.test(failure);
  if (expected) {
    remainingAllowances.count -= 1;
  }
  return expected;
}

function isExpectedLocalCancellation(
  request: Request,
  endpoint: LocalEndpoint,
  expectedPaths: string[],
): boolean {
  const failure = request.failure()?.errorText ?? "";
  const path = pathOnly(request.url());
  const expectedIndex = expectedPaths.indexOf(path);
  const expected =
    expectedIndex >= 0 &&
    isAllowedHttp(request.url(), endpoint) &&
    /(?:ERR_ABORTED|NS_BINDING_ABORTED|cancelled)/iu.test(failure);
  if (expected) expectedPaths.splice(expectedIndex, 1);
  return expected;
}

function addPageDiagnostics(
  page: Page,
  audit: BrowserAudit,
  endpoint: LocalEndpoint,
  expectedConsoleHttpFailures: ExpectedConsoleHttpFailure[],
  expectedDownloads: string[],
): void {
  if (INSTALLED_PAGE_GUARDS.has(page)) {
    return;
  }
  INSTALLED_PAGE_GUARDS.add(page);

  page.on("console", (message) => {
    if (message.type() === "error") {
      const statusMatch = message
        .text()
        .match(/server responded with a status of (\d{3})/iu);
      const locationPath = pathOnly(message.location().url);
      const status =
        statusMatch?.[1] === undefined ? 0 : Number(statusMatch[1]);
      const expectedIndex = expectedConsoleHttpFailures.findIndex(
        (expected) =>
          expected.path === locationPath && expected.status === status,
      );
      if (expectedIndex >= 0) {
        expectedConsoleHttpFailures.splice(expectedIndex, 1);
        audit.reviewedConsoleErrors.push(
          `Reviewed local HTTP ${status}: ${locationPath}`,
        );
        return;
      }
      audit.consoleErrors.push(sanitizeDiagnostic(message.text()));
    }
  });
  page.on("pageerror", (error) => {
    audit.pageErrors.push(sanitizeDiagnostic(error.message));
  });
  page.on("framenavigated", (frame) => {
    const target = frame.url();
    if (target !== "about:blank" && !isAllowedHttp(target, endpoint)) {
      audit.externalAttempts.push(
        `Blocked non-local frame navigation: ${safeTarget(target)}`,
      );
    }
  });
  page.on("download", (download) => {
    if (
      expectedDownloads.length === 1 &&
      download.suggestedFilename() === expectedDownloads[0] &&
      download.url().startsWith(`blob:${endpoint.origin}/`)
    ) {
      expectedDownloads.pop();
      return;
    }
    audit.unexpectedDownloads.push(
      `Unexpected download: ${sanitizeDiagnostic(download.suggestedFilename())}`,
    );
    void download.cancel();
  });
}

function allViolations(audit: BrowserAudit): string[] {
  return [
    ...audit.externalAttempts,
    ...audit.consoleErrors.map((value) => `Console error: ${value}`),
    ...audit.pageErrors.map((value) => `Page error: ${value}`),
    ...audit.unexpectedRequestFailures,
    ...audit.unexpectedDownloads,
    ...audit.unexpectedCookies,
  ];
}

function diagnosticBody(audit: BrowserAudit): string {
  return JSON.stringify(
    {
      allowedOrigin: audit.allowedOrigin,
      violations: allViolations(audit),
      events: audit.events.slice(-100),
    },
    null,
    2,
  );
}

export async function installBrowserAudit(
  context: BrowserContext,
  baseURL: string,
  testInfo: TestInfo,
): Promise<{
  readonly audit: BrowserAudit;
  readonly finalize: () => Promise<void>;
}> {
  const endpoint = parseLocalEndpoint(baseURL, "Playwright baseURL");
  const expectedConsoleHttpFailures: ExpectedConsoleHttpFailure[] = [];
  const expectedHealthCancellations = { count: 0 };
  const expectedLocalCancellationPaths: string[] = [];
  const expectedSessionCookies = { count: 0 };
  const expectedDownloads: string[] = [];
  let downloadAllowanceIssued = false;
  const audit: BrowserAudit = {
    allowedOrigin: endpoint.origin,
    events: [],
    responses: [],
    externalAttempts: [],
    consoleErrors: [],
    reviewedConsoleErrors: [],
    pageErrors: [],
    unexpectedRequestFailures: [],
    unexpectedDownloads: [],
    unexpectedCookies: [],
    allowOneExpectedManuscriptDownload: (filename) => {
      if (
        !testInfo.title.startsWith("E2E-INT-020 ") ||
        downloadAllowanceIssued ||
        !filename.endsWith(".txt") ||
        filename.length <= 4 ||
        /[<>:"/\\|?*]/u.test(filename) ||
        Array.from(filename).some((character) => character.charCodeAt(0) < 32)
      ) {
        throw new Error(
          "Only INT-020 may permit one safe manuscript download.",
        );
      }
      downloadAllowanceIssued = true;
      expectedDownloads.push(filename);
    },
    allowOneExpectedHealthCancellation: () => {
      expectedHealthCancellations.count += 1;
    },
    allowOneExpectedLocalCancellation: (path) => {
      if (!path.startsWith("/") || path.includes("?") || path.includes("#")) {
        throw new Error(
          "Expected local cancellation must use one absolute path.",
        );
      }
      expectedLocalCancellationPaths.push(path);
    },
    allowOneExpectedSessionCookie: () => {
      expectedSessionCookies.count += 1;
    },
    allowExpectedConsoleHttpFailure: (path, status) => {
      if (
        !path.startsWith("/") ||
        path.includes("?") ||
        path.includes("#") ||
        !Number.isInteger(status) ||
        status < 400 ||
        status > 599
      ) {
        throw new Error(
          "Expected console HTTP failures must use a safe path and error status.",
        );
      }
      expectedConsoleHttpFailures.push({ path, status });
    },
  };

  await context.clearPermissions();
  await context.route("**/*", async (route) => {
    const request = route.request();
    if (!isAllowedHttp(request.url(), endpoint)) {
      audit.externalAttempts.push(
        `Blocked external request: ${safeTarget(request.url())}`,
      );
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  await context.routeWebSocket(/.*/u, async (webSocket) => {
    if (!isAllowedWebSocket(webSocket.url(), endpoint)) {
      audit.externalAttempts.push(
        `Blocked external WebSocket: ${safeTarget(webSocket.url())}`,
      );
      await webSocket.close({ code: 1008, reason: "Local E2E only" });
      return;
    }
    webSocket.connectToServer();
  });

  context.on("page", (page) =>
    addPageDiagnostics(
      page,
      audit,
      endpoint,
      expectedConsoleHttpFailures,
      expectedDownloads,
    ),
  );
  for (const page of context.pages()) {
    addPageDiagnostics(
      page,
      audit,
      endpoint,
      expectedConsoleHttpFailures,
      expectedDownloads,
    );
  }

  context.on("request", (request) => {
    const headers = request.headers();
    const path = pathOnly(request.url());
    audit.events.push({ type: "request", method: request.method(), path });
    if (headers.authorization !== undefined) {
      audit.externalAttempts.push(
        `Authorization header is forbidden for local E2E request: ${path}`,
      );
    }
  });
  context.on("response", (response: Response) => {
    const request = response.request();
    const headers = response.headers();
    const path = pathOnly(response.url());
    audit.events.push({
      type: "response",
      method: request.method(),
      path,
      status: response.status(),
    });
    audit.responses.push({
      method: request.method(),
      path,
      status: response.status(),
      contentType: headers["content-type"] ?? null,
      requestId: headers["x-request-id"] ?? null,
    });
  });
  context.on("requestfailed", (request) => {
    const path = pathOnly(request.url());
    audit.events.push({
      type: "request-failed",
      method: request.method(),
      path,
    });
    if (
      !isExpectedLocalHealthCancellation(
        request,
        endpoint,
        expectedHealthCancellations,
      ) &&
      !isExpectedLocalCancellation(
        request,
        endpoint,
        expectedLocalCancellationPaths,
      )
    ) {
      audit.unexpectedRequestFailures.push(
        `Request failed: ${safeTarget(request.url())} (${sanitizeDiagnostic(
          request.failure()?.errorText ?? "unknown failure",
        )})`,
      );
    }
  });

  return {
    audit,
    finalize: async () => {
      if (expectedDownloads.length > 0) {
        audit.unexpectedDownloads.push(
          "Expected manuscript download was not observed.",
        );
      }
      const cookies = await context.cookies();
      for (const cookie of cookies) {
        const isExpectedSessionCookie =
          expectedSessionCookies.count > 0 &&
          cookie.name === "aiwebnovel_session" &&
          cookie.domain === endpoint.hostname &&
          cookie.path === "/api" &&
          cookie.httpOnly &&
          cookie.sameSite === "Strict" &&
          !cookie.secure &&
          cookie.expires > Date.now() / 1_000;
        if (isExpectedSessionCookie) {
          expectedSessionCookies.count -= 1;
          continue;
        }
        audit.unexpectedCookies.push(
          `Unexpected cookie for ${cookie.domain}${cookie.path}`,
        );
      }
      if (expectedSessionCookies.count > 0) {
        audit.unexpectedCookies.push(
          "Expected secure local session cookie was not observed.",
        );
      }

      const violations = allViolations(audit);
      if (
        violations.length > 0 ||
        testInfo.status !== testInfo.expectedStatus
      ) {
        await testInfo.attach("sanitized-e2e-diagnostics", {
          body: diagnosticBody(audit),
          contentType: "application/json",
        });
      }
      if (violations.length > 0) {
        throw new Error(`E2E browser audit failed:\n${violations.join("\n")}`);
      }
    },
  };
}
