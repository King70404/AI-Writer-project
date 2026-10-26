import {
  expectApiResponseRequestId,
  expectCleanBrowserAudit,
  expectHealthyPair,
  expectNoAbsoluteLocalPath,
  expectSecurityHeaders,
  expectSystemReady,
  observeHealthPair,
} from "../support/assertions";
import { expect, test } from "../support/fixture";

// This scenario handles ephemeral session material; failure artifacts must not
// retain network response bodies or Cookie headers.
test.use({ trace: "off" });

function asRecord(value: unknown): Record<string, unknown> {
  expect(value).not.toBeNull();
  expect(typeof value).toBe("object");
  expect(Array.isArray(value)).toBe(false);
  return value as Record<string, unknown>;
}

test("E2E-INT-005 enforces the production browser security baseline", async ({
  browserAudit,
  context,
  page,
  playwright,
}) => {
  const healthPairPromise = observeHealthPair(page);
  const rootResponse = await page.goto("/");
  const healthPair = await healthPairPromise;

  expect(rootResponse?.status()).toBe(200);
  expect(rootResponse?.headers()["content-type"]).toContain("text/html");
  expectSecurityHeaders(rootResponse?.headers() ?? {}, "html");
  await expectHealthyPair(healthPair);
  expectSecurityHeaders(healthPair.live.headers(), "api");
  expectSecurityHeaders(healthPair.ready.headers(), "api");
  const readyBody = asRecord(await healthPair.ready.json());
  expect(asRecord(readyBody.checks).security).toBe("ok");
  await expectSystemReady(page);
  await expect(
    page.getByRole("heading", { name: "AI 网文助手", exact: true }),
  ).toBeVisible();

  const localClient = await playwright.request.newContext({
    baseURL: browserAudit.allowedOrigin,
    extraHTTPHeaders: { Accept: "application/json" },
  });
  try {
    for (const path of ["/docs", "/redoc", "/openapi.json"]) {
      const response = await localClient.get(path);
      expect(response.status()).toBe(404);
      expect(response.headers()["content-type"]).toContain("application/json");
      expectSecurityHeaders(response.headers(), "base");
      const body: unknown = await response.json();
      expectNoAbsoluteLocalPath(body);
    }
  } finally {
    await localClient.dispose();
  }

  const rejectedHost = "untrusted.invalid";
  const invalidHostClient = await playwright.request.newContext({
    baseURL: browserAudit.allowedOrigin,
    extraHTTPHeaders: {
      Accept: "application/json",
      Host: rejectedHost,
    },
  });
  try {
    const response = await invalidHostClient.get("/api/v1/health/live");
    expect(response.status()).toBe(400);
    expectSecurityHeaders(response.headers(), "api");
    const body = asRecord(await response.json());
    expect(asRecord(body.error).code).toBe("INVALID_HOST");
    expectApiResponseRequestId(response, body.request_id);
    expect(JSON.stringify(body).includes(rejectedHost)).toBe(false);
    expectNoAbsoluteLocalPath(body);
  } finally {
    await invalidHostClient.dispose();
  }

  browserAudit.allowOneExpectedSessionCookie();
  const sessionResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === "/api/v1/security/session",
  );
  const safeSessionResult = await page.evaluate(async () => {
    const response = await fetch("/api/v1/security/session", {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const body = (await response.json()) as {
      csrf_token?: unknown;
      expires_in_seconds?: unknown;
    };
    const csrfTokenIsValid =
      typeof body.csrf_token === "string" &&
      /^[A-Za-z0-9_-]{32,512}$/u.test(body.csrf_token);
    return {
      status: response.status,
      csrfTokenIsValid,
      expiresInSeconds: body.expires_in_seconds,
      localStorageKeys: Object.keys(localStorage),
      sessionStorageKeys: Object.keys(sessionStorage),
    };
  });
  const sessionResponse = await sessionResponsePromise;
  expect(safeSessionResult.status).toBe(200);
  expect(safeSessionResult.csrfTokenIsValid).toBe(true);
  expect(safeSessionResult.expiresInSeconds).toBe(28_800);
  expect(safeSessionResult.localStorageKeys).toEqual([]);
  expect(safeSessionResult.sessionStorageKeys).toEqual([]);
  expectSecurityHeaders(sessionResponse.headers(), "api");

  const cookies = await context.cookies(
    `${browserAudit.allowedOrigin}/api/v1/security/session`,
  );
  const sessionCookies = cookies.filter(
    (cookie) => cookie.name === "aiwebnovel_session",
  );
  expect(sessionCookies).toHaveLength(1);
  const sessionCookie = sessionCookies[0];
  expect(sessionCookie?.domain).toBe("127.0.0.1");
  expect(sessionCookie?.path).toBe("/api");
  expect(sessionCookie?.httpOnly).toBe(true);
  expect(sessionCookie?.sameSite).toBe("Strict");
  expect(sessionCookie?.secure).toBe(false);
  expect((sessionCookie?.expires ?? 0) > Date.now() / 1_000).toBe(true);

  expectCleanBrowserAudit(browserAudit);
});
