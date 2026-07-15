import {
  expectCleanBrowserAudit,
  expectHealthyPair,
  expectSystemReady,
  observeHealthPair,
} from "../support/assertions";
import { expect, test } from "../support/fixture";

test.describe("integrated application delivery", () => {
  test("E2E-INT-001 serves the built React application and real readiness from FastAPI", async ({
    browserAudit,
    page,
  }) => {
    const healthPairPromise = observeHealthPair(page);
    const rootResponse = await page.goto("/");
    const pair = await healthPairPromise;

    expect(rootResponse?.status()).toBe(200);
    expect(rootResponse?.headers()["content-type"]).toContain("text/html");
    expect(new URL(rootResponse?.url() ?? "").origin).toBe(
      browserAudit.allowedOrigin,
    );
    await expectHealthyPair(pair);
    await expectSystemReady(page);
    const readyBody = (await pair.ready.json()) as {
      readonly checks?: { readonly frontend?: unknown };
    };
    expect(readyBody.checks?.frontend).toBe("ok");

    await expect(
      page.getByRole("heading", { name: "AIWebNovel", exact: true }),
    ).toBeVisible();
    await expect(page.locator('script[src*="/@vite/client"]')).toHaveCount(0);
    const scriptUrls = await page
      .locator("script[src]")
      .evaluateAll((scripts) =>
        scripts.map((script) => (script as HTMLScriptElement).src),
      );
    expect(scriptUrls.length).toBeGreaterThan(0);
    expect(
      scriptUrls.every((url) => {
        const script = new URL(url);
        return (
          script.origin === browserAudit.allowedOrigin &&
          script.pathname.startsWith("/assets/")
        );
      }),
    ).toBe(true);
    expectCleanBrowserAudit(browserAudit);
  });

  test("E2E-INT-002 applies SPA fallback to a direct client route and loads built assets", async ({
    browserAudit,
    page,
  }) => {
    const directResponse = await page.goto("/future-client-location");
    expect(directResponse?.status()).toBe(200);
    expect(directResponse?.headers()["content-type"]).toContain("text/html");
    await expect(
      page.getByRole("heading", { name: "页面不存在" }),
    ).toBeVisible();

    const successfulAssets = browserAudit.responses.filter(
      (response) =>
        response.method === "GET" &&
        response.path.startsWith("/assets/") &&
        response.status === 200,
    );
    expect(successfulAssets.length).toBeGreaterThan(0);
    expect(
      successfulAssets.every(
        (response) => response.contentType?.includes("text/html") === false,
      ),
    ).toBe(true);

    const healthPairPromise = observeHealthPair(page);
    await page.getByRole("link", { name: "返回基础页" }).click();
    const pair = await healthPairPromise;
    await expect(page).toHaveURL(`${browserAudit.allowedOrigin}/`);
    await expectHealthyPair(pair);
    await expectSystemReady(page);
    expectCleanBrowserAudit(browserAudit);
  });
});
