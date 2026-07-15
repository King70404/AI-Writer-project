import {
  expectApiResponseRequestId,
  expectNoAbsoluteLocalPath,
} from "../support/assertions";
import { expect, test } from "../support/fixture";
import { requiredLocalEnvironmentUrl } from "../support/network-guard";

function asRecord(value: unknown): Record<string, unknown> {
  expect(value).not.toBeNull();
  expect(typeof value).toBe("object");
  expect(Array.isArray(value)).toBe(false);
  return value as Record<string, unknown>;
}

test("E2E-STARTUP-001 exposes safe health failures when the real frontend build is missing", async ({
  playwright,
}) => {
  const missingBuildBaseURL = requiredLocalEnvironmentUrl(
    "AIWEBNOVEL_E2E_MISSING_BUILD_BASE_URL",
  );
  const client = await playwright.request.newContext({
    baseURL: missingBuildBaseURL,
    extraHTTPHeaders: { Accept: "application/json" },
  });

  try {
    const live = await client.get("/api/v1/health/live");
    expect(live.status()).toBe(200);
    expect(live.headers()["content-type"]).toContain("application/json");
    expectApiResponseRequestId(live);
    const liveBody: unknown = await live.json();
    expect(asRecord(liveBody).status).toBe("ok");

    const ready = await client.get("/api/v1/health/ready");
    expect(ready.status()).toBe(503);
    expect(ready.headers()["content-type"]).toContain("application/json");
    expectApiResponseRequestId(ready);
    const readyBody: unknown = await ready.json();
    expect(asRecord(readyBody).status).toBe("not_ready");
    const readyChecks = asRecord(asRecord(readyBody).checks);
    expect(readyChecks.storage).toBe("ok");
    expect(readyChecks.database).toBe("ok");
    expect(readyChecks.frontend).toBe("failed");

    const root = await client.get("/", {
      headers: { Accept: "text/html" },
    });
    expect(root.status()).toBe(503);
    expect(root.headers()["content-type"]).toContain("application/json");
    const rootBody: unknown = await root.json();
    const rootRecord = asRecord(rootBody);
    expectApiResponseRequestId(root, rootRecord.request_id);
    expect(asRecord(rootRecord.error).code).toBe("FRONTEND_BUILD_UNAVAILABLE");

    expectNoAbsoluteLocalPath(liveBody);
    expectNoAbsoluteLocalPath(readyBody);
    expectNoAbsoluteLocalPath(rootBody);
    expect(JSON.stringify(rootBody)).not.toContain(missingBuildBaseURL);
  } finally {
    await client.dispose();
  }
});
