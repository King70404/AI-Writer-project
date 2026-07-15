import {
  expectCleanBrowserAudit,
  expectHealthyPair,
  expectSystemReady,
  observeHealthPair,
} from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-DEV-003 serves the React 404 directly and returns without full navigation", async ({
  browserAudit,
  page,
}) => {
  browserAudit.allowOneExpectedHealthCancellation();
  const directResponse = await page.goto("/missing-client-route");
  expect(directResponse?.status()).toBe(200);
  expect(directResponse?.headers()["content-type"]).toContain("text/html");
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible();
  await expect(
    page.getByText("该地址不属于当前阶段的前端基础范围。", { exact: true }),
  ).toBeVisible();
  expect(page.url()).toBe(`${browserAudit.allowedOrigin}/missing-client-route`);

  const navigationEntriesBefore = await page.evaluate(
    () => performance.getEntriesByType("navigation").length,
  );
  const healthPairPromise = observeHealthPair(page);
  await page.getByRole("link", { name: "返回基础页" }).click();
  const pair = await healthPairPromise;
  await expect(page).toHaveURL(`${browserAudit.allowedOrigin}/`);
  await expectHealthyPair(pair);
  await expectSystemReady(page);
  expect(
    await page.evaluate(
      () => performance.getEntriesByType("navigation").length,
    ),
  ).toBe(navigationEntriesBefore);
  expectCleanBrowserAudit(browserAudit);
});
