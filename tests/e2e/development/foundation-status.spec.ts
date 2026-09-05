import {
  expectCleanBrowserAudit,
  expectHealthyPair,
  expectSystemReady,
  healthEventsSince,
  healthResponseCount,
  observeHealthPair,
} from "../support/assertions";
import { expect, test } from "../support/fixture";
import { HEALTH_LIVE_PATH, HEALTH_READY_PATH } from "../support/network-guard";
import { gateFirstRequest } from "../support/request-gate";

test.describe("development foundation status", () => {
  test("E2E-DEV-001 renders the foundation page from real local health responses", async ({
    browserAudit,
    page,
  }) => {
    browserAudit.allowOneExpectedHealthCancellation();
    const readyGate = await gateFirstRequest(page, HEALTH_READY_PATH);
    const healthPairPromise = observeHealthPair(page);
    const navigationPromise = page.goto("/");

    await readyGate.reached;
    try {
      await expect(
        page.getByText("正在检查本地后端状态。", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "重新检查" }),
      ).toBeDisabled();
    } finally {
      readyGate.release();
    }

    const [navigationResponse, pair] = await Promise.all([
      navigationPromise,
      healthPairPromise,
    ]);
    expect(navigationResponse?.status()).toBe(200);
    expect(navigationResponse?.headers()["content-type"]).toContain(
      "text/html",
    );
    await expectHealthyPair(pair);
    await expectSystemReady(page);

    await expect(
      page.getByRole("heading", { name: "AIWebNovel", exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("当前版本：V1")).toBeVisible();
    await expect(
      page.getByRole("link", { name: "开始使用：进入项目" }),
    ).toHaveAttribute("href", "/projects");
    await expect(
      page.getByRole("heading", { name: "AIWebNovel 前端基础已启动" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "开始创作" })).toHaveCount(0);
    await expect(
      page.getByText(/项目总数|章节总数|今日字数|创作进度/u),
    ).toHaveCount(0);
    expect(pair.live.url()).toBe(
      `${browserAudit.allowedOrigin}${HEALTH_LIVE_PATH}`,
    );
    expect(pair.ready.url()).toBe(
      `${browserAudit.allowedOrigin}${HEALTH_READY_PATH}`,
    );
    expectCleanBrowserAudit(browserAudit);
  });

  test("E2E-DEV-002 performs exactly one new real health pair on manual recheck", async ({
    browserAudit,
    page,
  }) => {
    browserAudit.allowOneExpectedHealthCancellation();
    const firstPairPromise = observeHealthPair(page);
    await page.goto("/");
    const firstPair = await firstPairPromise;
    await expectHealthyPair(firstPair);
    await expectSystemReady(page);

    const baselineLive = healthResponseCount(browserAudit, HEALTH_LIVE_PATH);
    const baselineReady = healthResponseCount(browserAudit, HEALTH_READY_PATH);
    const baselineEventIndex = browserAudit.events.length;
    const recheckGate = await gateFirstRequest(page, HEALTH_READY_PATH);
    const secondPairPromise = observeHealthPair(page);
    const recheckButton = page.getByRole("button", { name: "重新检查" });
    await recheckButton.click();

    await recheckGate.reached;
    try {
      await expect(recheckButton).toBeDisabled();
      await expect(
        page.getByText("正在检查本地后端状态。", { exact: true }),
      ).toBeVisible();
    } finally {
      recheckGate.release();
    }

    const secondPair = await secondPairPromise;
    await expectHealthyPair(secondPair);
    await expectSystemReady(page);
    expect(secondPair.liveRequestId).not.toBe(firstPair.liveRequestId);
    expect(secondPair.readyRequestId).not.toBe(firstPair.readyRequestId);
    expect(healthResponseCount(browserAudit, HEALTH_LIVE_PATH)).toBe(
      baselineLive + 1,
    );
    expect(healthResponseCount(browserAudit, HEALTH_READY_PATH)).toBe(
      baselineReady + 1,
    );
    expect(healthEventsSince(browserAudit, baselineEventIndex)).toEqual([
      `request:${HEALTH_LIVE_PATH}`,
      `response:${HEALTH_LIVE_PATH}`,
      `request:${HEALTH_READY_PATH}`,
      `response:${HEALTH_READY_PATH}`,
    ]);

    await expect(
      page.waitForRequest(
        (request) => {
          const path = new URL(request.url()).pathname;
          return path === HEALTH_LIVE_PATH || path === HEALTH_READY_PATH;
        },
        { timeout: 2_000 },
      ),
    ).rejects.toThrow(/Timeout 2000ms exceeded/u);
    await expect(recheckButton).toBeEnabled();
    expectCleanBrowserAudit(browserAudit);
  });
});
