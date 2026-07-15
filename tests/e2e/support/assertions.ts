import type { APIResponse, Page, Response } from "@playwright/test";
import { expect } from "@playwright/test";

import type { BrowserAudit } from "./network-guard";
import { HEALTH_LIVE_PATH, HEALTH_READY_PATH } from "./network-guard";

export interface HealthPair {
  readonly live: Response;
  readonly ready: Response;
  readonly liveRequestId: string;
  readonly readyRequestId: string;
}

export interface BrowserFetchResult {
  readonly status: number;
  readonly contentType: string;
  readonly requestId: string | null;
  readonly body: unknown;
  readonly textPreview: string;
}

const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/u;
const WINDOWS_PATH_PATTERN = /(?:\b[A-Za-z]:[\\/]|\\\\[^\\\s]+\\)/u;
const UNIX_USER_PATH_PATTERN = /(?:\/Users\/|\/home\/|\/tmp\/)/u;

function responsePath(response: Response): string {
  return new URL(response.url()).pathname;
}

function responseRequestId(response: Response): string {
  const requestId = response.headers()["x-request-id"];
  expect(
    requestId,
    `${responsePath(response)} must return X-Request-ID`,
  ).toMatch(REQUEST_ID_PATTERN);
  return requestId;
}

export function observeHealthPair(page: Page): Promise<HealthPair> {
  const live = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      responsePath(response) === HEALTH_LIVE_PATH,
  );
  const ready = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      responsePath(response) === HEALTH_READY_PATH,
  );

  return Promise.all([live, ready]).then(([liveResponse, readyResponse]) => ({
    live: liveResponse,
    ready: readyResponse,
    liveRequestId: responseRequestId(liveResponse),
    readyRequestId: responseRequestId(readyResponse),
  }));
}

export async function expectHealthyPair(pair: HealthPair): Promise<void> {
  expect(pair.live.status()).toBe(200);
  expect(pair.live.headers()["content-type"]).toContain("application/json");
  const liveBody: unknown = await pair.live.json();
  expect(liveBody).toMatchObject({
    status: "ok",
    service: "AIWebNovel",
  });
  expect(pair.ready.status()).toBe(200);
  expect(pair.ready.headers()["content-type"]).toContain("application/json");
  const readyBody: unknown = await pair.ready.json();
  expect(readyBody).toMatchObject({
    status: "ready",
    checks: {
      configuration: "ok",
      application: "ok",
      storage: "ok",
      database: "ok",
    },
  });
  expectNoAbsoluteLocalPath(liveBody);
  expectNoAbsoluteLocalPath(readyBody);
  expect(pair.liveRequestId).not.toBe(pair.readyRequestId);
}

export async function expectSystemReady(page: Page): Promise<void> {
  await expect(
    page.getByText("本地后端已连接，数据库基础检查通过。", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "重新检查" })).toBeEnabled();
}

export function expectCleanBrowserAudit(audit: BrowserAudit): void {
  expect(audit.externalAttempts).toEqual([]);
  expect(audit.consoleErrors).toEqual([]);
  expect(audit.pageErrors).toEqual([]);
  expect(audit.unexpectedRequestFailures).toEqual([]);
  expect(audit.unexpectedDownloads).toEqual([]);
  expect(audit.unexpectedCookies).toEqual([]);
}

export function expectNoAbsoluteLocalPath(value: unknown): void {
  const serialized = typeof value === "string" ? value : JSON.stringify(value);
  expect(serialized).not.toMatch(WINDOWS_PATH_PATTERN);
  expect(serialized).not.toMatch(UNIX_USER_PATH_PATTERN);
  expect(serialized).not.toContain("file://");
  expect(serialized).not.toContain("AppData");
}

export function expectApiResponseRequestId(
  response: APIResponse,
  bodyRequestId?: unknown,
): string {
  const requestId = response.headers()["x-request-id"];
  expect(requestId).toMatch(REQUEST_ID_PATTERN);
  if (bodyRequestId !== undefined) {
    expect(bodyRequestId).toBe(requestId);
  }
  return requestId;
}

export async function fetchInBrowser(
  page: Page,
  path: string,
  options: { readonly method?: string; readonly accept?: string } = {},
): Promise<BrowserFetchResult> {
  return page.evaluate(
    async ({ targetPath, method, accept }) => {
      const response = await fetch(targetPath, {
        method,
        headers: { Accept: accept },
      });
      const text = await response.text();
      let body: unknown = null;
      if (response.headers.get("content-type")?.includes("application/json")) {
        try {
          body = JSON.parse(text) as unknown;
        } catch {
          body = null;
        }
      }
      return {
        status: response.status,
        contentType: response.headers.get("content-type") ?? "",
        requestId: response.headers.get("x-request-id"),
        body,
        textPreview: text.slice(0, 512),
      };
    },
    {
      targetPath: path,
      method: options.method ?? "GET",
      accept: options.accept ?? "application/json",
    },
  );
}

export function healthResponseCount(
  audit: BrowserAudit,
  path: typeof HEALTH_LIVE_PATH | typeof HEALTH_READY_PATH,
): number {
  return audit.responses.filter(
    (response) =>
      response.method === "GET" &&
      response.path === path &&
      response.status === 200,
  ).length;
}

export function healthEventsSince(
  audit: BrowserAudit,
  startIndex: number,
): readonly string[] {
  return audit.events
    .slice(startIndex)
    .filter(
      (event) =>
        event.path === HEALTH_LIVE_PATH || event.path === HEALTH_READY_PATH,
    )
    .map((event) => `${event.type}:${event.path}`);
}
