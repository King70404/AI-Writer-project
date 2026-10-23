import {
  expectCleanBrowserAudit,
  expectNoAbsoluteLocalPath,
  expectHealthyPair,
  expectSystemReady,
  fetchInBrowser,
  observeHealthPair,
} from "../support/assertions";
import { expect, test } from "../support/fixture";
import { HEALTH_LIVE_PATH, HEALTH_READY_PATH } from "../support/network-guard";

function asRecord(value: unknown): Record<string, unknown> {
  expect(value).not.toBeNull();
  expect(typeof value).toBe("object");
  expect(Array.isArray(value)).toBe(false);
  return value as Record<string, unknown>;
}

function requestIdFromErrorBody(value: unknown): unknown {
  return asRecord(value).request_id;
}

function errorCode(value: unknown): unknown {
  return asRecord(asRecord(value).error).code;
}

test.describe("integrated route isolation", () => {
  test("E2E-INT-003 isolates JSON APIs, static assets, and HTML SPA fallback", async ({
    browserAudit,
    page,
  }) => {
    const initialPairPromise = observeHealthPair(page);
    const rootResponse = await page.goto("/");
    await expectHealthyPair(await initialPairPromise);
    await expectSystemReady(page);
    expect(rootResponse?.status()).toBe(200);
    expect(rootResponse?.headers()["content-type"]).toContain("text/html");

    const live = await fetchInBrowser(page, HEALTH_LIVE_PATH);
    expect(live.status).toBe(200);
    expect(live.contentType).toContain("application/json");
    expect(live.requestId).toMatch(/^[A-Za-z0-9._:-]{1,128}$/u);
    expect(asRecord(live.body).status).toBe("ok");

    const ready = await fetchInBrowser(page, HEALTH_READY_PATH);
    expect(ready.status).toBe(200);
    expect(ready.contentType).toContain("application/json");
    expect(ready.requestId).toMatch(/^[A-Za-z0-9._:-]{1,128}$/u);
    const readyBody = asRecord(ready.body);
    expect(readyBody.status).toBe("ready");
    expect(asRecord(readyBody.checks).frontend).toBe("ok");

    browserAudit.allowExpectedConsoleHttpFailure("/api/v1/missing", 404);
    const missingApi = await fetchInBrowser(page, "/api/v1/missing");
    expect(missingApi.status).toBe(404);
    expect(missingApi.contentType).toContain("application/json");
    expect(errorCode(missingApi.body)).toBe("NOT_FOUND");
    expect(requestIdFromErrorBody(missingApi.body)).toBe(missingApi.requestId);

    browserAudit.allowExpectedConsoleHttpFailure("/assets/missing.js", 404);
    const missingAsset = await fetchInBrowser(page, "/assets/missing.js", {
      accept: "text/html",
    });
    expect(missingAsset.status).toBe(404);
    expect(missingAsset.contentType).toContain("application/json");
    expect(missingAsset.contentType).not.toContain("text/html");
    expect(errorCode(missingAsset.body)).toBe("NOT_FOUND");
    expect(requestIdFromErrorBody(missingAsset.body)).toBe(
      missingAsset.requestId,
    );
    expect(missingAsset.textPreview.toLowerCase()).not.toContain("<!doctype");
    expect(missingAsset.textPreview).not.toContain('id="root"');

    browserAudit.allowExpectedConsoleHttpFailure("/future-client-route", 405);
    const postedClientRoute = await fetchInBrowser(
      page,
      "/future-client-route",
      { method: "POST", accept: "text/html" },
    );
    expect([404, 405]).toContain(postedClientRoute.status);
    expect(postedClientRoute.contentType).toContain("application/json");
    expect(postedClientRoute.contentType).not.toContain("text/html");
    expect(requestIdFromErrorBody(postedClientRoute.body)).toBe(
      postedClientRoute.requestId,
    );
    expect(postedClientRoute.textPreview.toLowerCase()).not.toContain(
      "<!doctype",
    );

    for (const response of [
      live,
      ready,
      missingApi,
      missingAsset,
      postedClientRoute,
    ]) {
      expectNoAbsoluteLocalPath(response.body);
      expectNoAbsoluteLocalPath(response.textPreview);
    }
    expectCleanBrowserAudit(browserAudit);
  });

  test("E2E-INT-004 remounts after refresh and performs a new real status check", async ({
    browserAudit,
    page,
  }) => {
    const firstPairPromise = observeHealthPair(page);
    await page.goto("/");
    const firstPair = await firstPairPromise;
    await expectHealthyPair(firstPair);
    await expectSystemReady(page);

    const secondPairPromise = observeHealthPair(page);
    const refreshedResponse = await page.reload();
    const secondPair = await secondPairPromise;
    expect(refreshedResponse?.status()).toBe(200);
    expect(refreshedResponse?.headers()["content-type"]).toContain("text/html");
    await expectHealthyPair(secondPair);
    await expectSystemReady(page);
    expect(secondPair.liveRequestId).not.toBe(firstPair.liveRequestId);
    expect(secondPair.readyRequestId).not.toBe(firstPair.readyRequestId);
    await expect(page.locator("#root")).toHaveCount(1);
    await expect(
      page.getByRole("heading", { name: "AI 网文助手", exact: true }),
    ).toHaveCount(1);
    expectCleanBrowserAudit(browserAudit);
  });
});
