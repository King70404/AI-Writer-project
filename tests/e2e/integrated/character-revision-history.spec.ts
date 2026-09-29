import { request as playwrightRequest } from "@playwright/test";

import {
  expectCleanBrowserAudit,
  expectNoEngineeringMetadata,
  expectSecurityHeaders,
} from "../support/assertions";
import { expect, test } from "../support/fixture";

const ownerTitle = "E2E Character History Owner 016";
const characterName = "E2E Character History 016";
const profilePrefix = "E2E-CHARACTER-HISTORY-PROFILE-CANARY-016";

test("E2E-INT-016 views immutable Character history with lazy profile reads", async ({
  baseURL,
  browserAudit,
  page,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  const external = await playwrightRequest.newContext({ baseURL: origin });
  let projectId = "";
  let characterId = "";
  try {
    const session = await external.get("/api/v1/security/session", {
      headers: { Origin: origin },
    });
    expect(session.status()).toBe(200);
    const csrf = ((await session.json()) as { readonly csrf_token: string })
      .csrf_token;
    const writeHeaders = { Origin: origin, "X-CSRF-Token": csrf };
    const project = await external.post("/api/v1/projects", {
      data: { title: ownerTitle, description: "History owner" },
      headers: writeHeaders,
    });
    expect(project.status()).toBe(201);
    projectId = ((await project.json()) as { readonly project_id: string })
      .project_id;
    const created = await external.post(
      `/api/v1/projects/${projectId}/characters`,
      {
        data: {
          name: `${characterName} 01`,
          role: "Lead 01",
          profile: `${profilePrefix}-01\nline two`,
        },
        headers: writeHeaders,
      },
    );
    expect(created.status()).toBe(201);
    characterId = ((await created.json()) as { readonly character_id: string })
      .character_id;
    let etag = created.headers().etag ?? "missing-etag";
    for (let number = 2; number <= 21; number += 1) {
      const suffix = String(number).padStart(2, "0");
      const revised = await external.put(`/api/v1/characters/${characterId}`, {
        data: {
          name: `${characterName} ${suffix}`,
          role: `Lead ${suffix}`,
          profile: `${profilePrefix}-${suffix}`,
        },
        headers: { ...writeHeaders, "If-Match": etag },
      });
      expect(revised.status()).toBe(200);
      etag = revised.headers().etag ?? "missing-etag";
      expect(etag).toBe(`"${number}"`);
    }
  } finally {
    await external.dispose();
  }

  const historyRequests: Array<{
    readonly method: string;
    readonly url: string;
  }> = [];
  const sessionRequests: string[] = [];
  page.on("request", (request) => {
    const target = new URL(request.url());
    if (target.pathname === "/api/v1/security/session") {
      sessionRequests.push(target.pathname);
    }
    if (target.pathname.includes(`/characters/${characterId}/revisions`)) {
      historyRequests.push({
        method: request.method(),
        url: target.toString(),
      });
    }
  });

  const editorPath = `/projects/${projectId}/characters/${characterId}`;
  const historyPath = `${editorPath}/history`;
  await page.goto(editorPath);
  const historyLink = page.getByRole("link", { name: "查看修订历史" });
  await expect(historyLink).toHaveAttribute("href", historyPath);
  await expectNoEngineeringMetadata(page);
  await historyLink.click();
  await expect(page).toHaveURL(new RegExp(`${historyPath}$`, "u"));
  await expect(page.locator(".project-revision-card")).toHaveCount(20);
  await expectNoEngineeringMetadata(page);
  await expect(page.locator(".project-revision-card time")).toHaveCount(20);
  historyRequests.length = 0;
  sessionRequests.length = 0;
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "角色修订历史" }),
  ).toBeVisible();
  await expect(page.locator(".project-revision-card")).toHaveCount(20);
  await expect(page.locator(".project-revision-card h3")).toHaveText(
    Array.from({ length: 20 }, (_, index) => `修订 ${21 - index}`),
  );
  await expect(page.getByText("当前版本", { exact: true })).toHaveCount(1);
  await expect(page.getByText(`${profilePrefix}-01`)).toHaveCount(0);
  expect(
    historyRequests.filter(({ url }) => !url.match(/\/revisions\/\d+$/u)),
  ).toHaveLength(1);
  expect(
    historyRequests.filter(({ url }) => url.match(/\/revisions\/\d+$/u)),
  ).toHaveLength(0);
  expect(sessionRequests).toHaveLength(0);

  const urlBeforePaging = page.url();
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(page.locator(".project-revision-card")).toHaveCount(21);
  expect(page.url()).toBe(urlBeforePaging);
  const revisionOne = page.locator(".project-revision-card").filter({
    has: page.getByRole("heading", { name: "修订 1", exact: true }),
  });
  await revisionOne.getByRole("button", { name: "查看此修订" }).click();
  await expect(page.getByText(`${profilePrefix}-01`)).toBeVisible();
  await expect(page.getByText("line two")).toBeVisible();
  await expectNoEngineeringMetadata(page);

  let releaseRevisionTwo!: () => void;
  const revisionTwoRelease = new Promise<void>((resolve) => {
    releaseRevisionTwo = resolve;
  });
  await page.route(
    `**/api/v1/characters/${characterId}/revisions/2`,
    async (route) => {
      await revisionTwoRelease;
      await route.continue();
    },
  );
  const revisionTwo = page.locator(".project-revision-card").filter({
    has: page.getByRole("heading", { name: "修订 2", exact: true }),
  });
  browserAudit.allowOneExpectedLocalCancellation(
    `/api/v1/characters/${characterId}/revisions/2`,
  );
  await revisionTwo.getByRole("button", { name: "查看此修订" }).click();
  const revisionTwentyOne = page.locator(".project-revision-card").filter({
    has: page.getByRole("heading", { name: "修订 21", exact: true }),
  });
  await revisionTwentyOne.getByRole("button", { name: "查看此修订" }).click();
  await expect(page.getByText(`${profilePrefix}-21`)).toBeVisible();
  releaseRevisionTwo();
  await expect(page.getByText(`${profilePrefix}-02`)).toHaveCount(0);

  await expect(
    page.getByRole("button", { name: /回滚|恢复|采用|删除|Diff|编辑历史/u }),
  ).toHaveCount(0);
  expect(historyRequests.every(({ method }) => method === "GET")).toBe(true);
  expect(
    historyRequests.some(({ url }) => new URL(url).searchParams.has("total")),
  ).toBe(false);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(page.url()).not.toMatch(/cursor|profile|revision_id/iu);
  expectCleanBrowserAudit(browserAudit);

  // Keep the captured history page open while the author deletes its novel.
  const ownerPage = await page.context().newPage();
  const deleteApiPath = `/api/v1/projects/${projectId}/delete`;
  const deleteRequests: Array<{
    readonly method: string;
    readonly ifMatch: string | undefined;
  }> = [];
  ownerPage.on("request", (request) => {
    if (new URL(request.url()).pathname === deleteApiPath) {
      deleteRequests.push({
        method: request.method(),
        ifMatch: request.headers()["if-match"],
      });
    }
  });
  browserAudit.allowOneExpectedSessionCookie();
  await ownerPage.goto(`/projects/${projectId}`);
  const deletion = ownerPage.getByRole("region", { name: "删除小说" });
  const deleteButton = deletion.getByRole("button", {
    name: "删除小说",
    exact: true,
  });
  await expect(deleteButton).toBeDisabled();
  await deletion.getByRole("textbox", { name: "确认书名" }).fill(ownerTitle);
  const deletedResponsePromise = ownerPage.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === deleteApiPath,
  );
  await deleteButton.click();
  const deletedResponse = await deletedResponsePromise;
  expect(deletedResponse.status()).toBe(200);
  expect(await deletedResponse.json()).toEqual({ deleted: true });
  expect(deleteRequests).toEqual([{ method: "POST", ifMatch: '"1"' }]);
  await expect(ownerPage).toHaveURL(`${origin}/projects`);
  await expect(ownerPage.getByText("还没有项目")).toBeVisible();

  const deletedRevisionApi = `/api/v1/characters/${characterId}/revisions/3`;
  browserAudit.allowExpectedConsoleHttpFailure(deletedRevisionApi, 404);
  const deniedRevisionPromise = page.waitForResponse(
    (response) => new URL(response.url()).pathname === deletedRevisionApi,
  );
  const revisionThree = page.locator(".project-revision-card").filter({
    has: page.getByRole("heading", { name: "修订 3", exact: true }),
  });
  await revisionThree.getByRole("button", { name: "查看此修订" }).click();
  const deniedRevision = await deniedRevisionPromise;
  expect(deniedRevision.status()).toBe(404);
  expectSecurityHeaders(deniedRevision.headers(), "api");
  expect(await deniedRevision.text()).not.toContain(profilePrefix);
  await expect(
    page.locator(".project-revision-viewer").getByRole("alert"),
  ).toContainText("指定角色不存在。");
  await expect(page.getByText(new RegExp(profilePrefix, "u"))).toHaveCount(0);

  const deletedHistoryApi = `/api/v1/characters/${characterId}/revisions`;
  browserAudit.allowExpectedConsoleHttpFailure(deletedHistoryApi, 404);
  const deniedHistoryPromise = page.waitForResponse(
    (response) => new URL(response.url()).pathname === deletedHistoryApi,
  );
  await page.goto(historyPath);
  const deniedHistory = await deniedHistoryPromise;
  expect(deniedHistory.status()).toBe(404);
  expectSecurityHeaders(deniedHistory.headers(), "api");
  expect(await deniedHistory.text()).not.toContain(profilePrefix);
  await expect(page.getByRole("heading", { name: "角色不存在" })).toBeVisible();
  await expect(page.locator(".project-revision-card")).toHaveCount(0);
  await expect(page.getByText(new RegExp(profilePrefix, "u"))).toHaveCount(0);
  expect(historyRequests.every(({ method }) => method === "GET")).toBe(true);
  expect(sessionRequests).toHaveLength(0);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expectCleanBrowserAudit(browserAudit);
});
