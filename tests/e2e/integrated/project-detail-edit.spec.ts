import { request as playwrightRequest } from "@playwright/test";

import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

const directInitialTitle = "E2E Project Detail Direct Initial 009";
const directRevisedTitle = "E2E Project Detail Direct Revised 009";
const directInitialDescription =
  "E2E-PROJECT-DETAIL-DIRECT-INITIAL-DESCRIPTION-CANARY-009";
const directRevisedDescription =
  "E2E-PROJECT-DETAIL-DIRECT-REVISED-DESCRIPTION-CANARY-009";
const conflictInitialTitle = "E2E Project Conflict Initial 009";
const externalRevisedTitle = "E2E Project Conflict External 009";
const localConflictTitle = "E2E Project Conflict Local Draft 009";
const conflictInitialDescription =
  "E2E-PROJECT-CONFLICT-INITIAL-DESCRIPTION-CANARY-009";
const externalRevisedDescription =
  "E2E-PROJECT-CONFLICT-EXTERNAL-DESCRIPTION-CANARY-009";
const localConflictDescription =
  "E2E-PROJECT-CONFLICT-LOCAL-DESCRIPTION-CANARY-009\n保留换行";

function projectPathFromHref(href: string | null): string {
  expect(href).toMatch(/^\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}$/u);
  return href ?? "/invalid-project-link";
}

test("E2E-INT-009 exercises Project detail editing and explicit conflict handling", async ({
  baseURL,
  browserAudit,
  page,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  browserAudit.allowOneExpectedSessionCookie();

  const projectRequests: Array<{
    readonly method: string;
    readonly path: string;
    readonly ifMatch: string | undefined;
    readonly body: string | null;
  }> = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (/^\/api\/v1\/projects\/prj_/u.test(path)) {
      projectRequests.push({
        method: request.method(),
        path,
        ifMatch: request.headers()["if-match"],
        body: request.postData(),
      });
    }
  });

  await page.goto("/projects");
  await expect(page.getByText("还没有项目")).toBeVisible();

  await page.getByRole("textbox", { name: "书名" }).fill(directInitialTitle);
  await page
    .getByRole("textbox", { name: "一句话简介（可选）" })
    .fill(directInitialDescription);
  await page.getByRole("button", { name: "创建小说" }).click();
  const directLink = page.getByRole("link", { name: "打开这本小说" });
  const directPath = projectPathFromHref(await directLink.getAttribute("href"));
  const directApiPath = `/api/v1${directPath}`;
  const directGetOne = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === directApiPath,
  );
  await directLink.click();
  const directInitialGet = await directGetOne;
  expect(directInitialGet.status()).toBe(200);
  expect(directInitialGet.headers().etag).toBe('"1"');
  await expect(
    page.getByRole("heading", { level: 2, name: directInitialTitle }),
  ).toBeVisible();
  await expect(page.getByText("并发版本")).toHaveCount(0);
  await expect(page.getByText("当前修订号")).toHaveCount(0);
  expect(await directInitialGet.json()).toMatchObject({
    revision_number: 1,
    concurrency_version: 1,
  });

  await page
    .getByRole("textbox", { name: "书名", exact: true })
    .fill(directRevisedTitle);
  await page
    .getByRole("textbox", { name: "简介", exact: true })
    .fill(directRevisedDescription);
  const directPutResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === directApiPath,
  );
  await page.getByRole("button", { name: "保存小说信息" }).click();
  const directSaved = await directPutResponse;
  expect(directSaved.status()).toBe(200);
  expect(directSaved.headers().etag).toBe('"2"');
  await expect(page.getByText("小说信息已保存。")).toBeVisible();
  await expect(page.getByText("并发版本")).toHaveCount(0);
  await expect(page.getByText("当前修订号")).toHaveCount(0);
  expect(await directSaved.json()).toMatchObject({
    revision_number: 2,
    concurrency_version: 2,
  });
  const directPut = projectRequests.find(
    (request) => request.method === "PUT" && request.path === directApiPath,
  );
  expect(directPut?.ifMatch).toBe('"1"');
  expect(JSON.parse(directPut?.body ?? "null")).toEqual({
    title: directRevisedTitle,
    description: directRevisedDescription,
  });

  const directReloadGet = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === directApiPath,
  );
  await page.reload();
  const reloadedDirect = await directReloadGet;
  expect(reloadedDirect.headers().etag).toBe('"2"');
  await expect(
    page.getByRole("heading", { level: 2, name: directRevisedTitle }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "简介", exact: true }),
  ).toHaveValue(directRevisedDescription);

  await page.getByRole("link", { name: "返回我的小说" }).click();
  await expect(
    page
      .getByRole("list", { name: "项目列表", exact: true })
      .getByRole("heading", { name: directRevisedTitle, exact: true }),
  ).toBeVisible();
  const createProjectRegion = page.getByRole("region", { name: "新建小说" });
  const conflictTitleInput = createProjectRegion.getByRole("textbox", {
    name: "书名",
  });
  const conflictDescriptionInput = createProjectRegion.getByRole("textbox", {
    name: "一句话简介（可选）",
  });
  await expect(
    createProjectRegion.getByRole("button", { name: "创建小说" }),
  ).toBeEnabled();
  await conflictTitleInput.fill(conflictInitialTitle);
  await conflictDescriptionInput.fill(conflictInitialDescription);
  await expect(conflictTitleInput).toHaveValue(conflictInitialTitle);
  await expect(conflictDescriptionInput).toHaveValue(
    conflictInitialDescription,
  );
  await createProjectRegion.getByRole("button", { name: "创建小说" }).click();
  const conflictLink = page.getByRole("link", { name: "打开这本小说" });
  const conflictPath = projectPathFromHref(
    await conflictLink.getAttribute("href"),
  );
  const conflictApiPath = `/api/v1${conflictPath}`;
  const conflictInitialGetPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === conflictApiPath,
  );
  await conflictLink.click();
  const conflictInitialGet = await conflictInitialGetPromise;
  expect(conflictInitialGet.headers().etag).toBe('"1"');

  const external = await playwrightRequest.newContext({ baseURL: origin });
  try {
    const externalSession = await external.get("/api/v1/security/session", {
      headers: { Origin: origin },
    });
    expect(externalSession.status()).toBe(200);
    const externalSessionBody = (await externalSession.json()) as {
      readonly csrf_token: string;
    };
    const externalPut = await external.put(conflictApiPath, {
      data: {
        title: externalRevisedTitle,
        description: externalRevisedDescription,
      },
      headers: {
        Origin: origin,
        "X-CSRF-Token": externalSessionBody.csrf_token,
        "If-Match": '"1"',
      },
    });
    expect(externalPut.status()).toBe(200);
    expect(externalPut.headers().etag).toBe('"2"');
  } finally {
    await external.dispose();
  }

  await page
    .getByRole("textbox", { name: "书名", exact: true })
    .fill(localConflictTitle);
  await page
    .getByRole("textbox", { name: "简介", exact: true })
    .fill(localConflictDescription);
  const getsBeforeConflict = projectRequests.filter(
    (request) => request.method === "GET" && request.path === conflictApiPath,
  ).length;
  const putsBeforeConflict = projectRequests.filter(
    (request) => request.method === "PUT" && request.path === conflictApiPath,
  ).length;
  browserAudit.allowExpectedConsoleHttpFailure(conflictApiPath, 412);
  await page.getByRole("button", { name: "保存小说信息" }).click();
  await expect(
    page.getByRole("heading", { name: "检测到版本冲突" }),
  ).toBeFocused();
  await expect(page.getByText(/当前草稿基于版本 1/u)).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "书名", exact: true }),
  ).toHaveValue(localConflictTitle);
  expect(
    projectRequests.filter(
      (request) => request.method === "GET" && request.path === conflictApiPath,
    ),
  ).toHaveLength(getsBeforeConflict);
  expect(
    projectRequests.filter(
      (request) => request.method === "PUT" && request.path === conflictApiPath,
    ),
  ).toHaveLength(putsBeforeConflict + 1);

  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
  expect(
    projectRequests.filter(
      (request) => request.method === "GET" && request.path === conflictApiPath,
    ),
  ).toHaveLength(getsBeforeConflict);
  expect(
    projectRequests.filter(
      (request) => request.method === "PUT" && request.path === conflictApiPath,
    ),
  ).toHaveLength(putsBeforeConflict + 1);

  await page.getByRole("button", { name: "读取最新版本" }).click();
  await expect(page.getByText(externalRevisedTitle)).toBeVisible();
  await expect(page.getByText(localConflictTitle)).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "书名", exact: true }),
  ).toHaveValue(localConflictTitle);
  expect(
    projectRequests.filter(
      (request) => request.method === "GET" && request.path === conflictApiPath,
    ),
  ).toHaveLength(getsBeforeConflict + 1);

  await page
    .getByRole("button", {
      name: "保留草稿并以最新版本建立基线",
    })
    .click();
  await expect(
    page.getByText("当前编辑内容将在下次保存时应用到最新版本。"),
  ).toBeVisible();
  expect(
    projectRequests.filter(
      (request) => request.method === "PUT" && request.path === conflictApiPath,
    ),
  ).toHaveLength(putsBeforeConflict + 1);

  const finalPutPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === conflictApiPath &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "保存小说信息" }).click();
  const finalPut = await finalPutPromise;
  expect(finalPut.headers().etag).toBe('"3"');
  await expect(page.getByText("小说信息已保存。")).toBeVisible();
  await expect(page.getByText("并发版本")).toHaveCount(0);
  await expect(page.getByText("当前修订号")).toHaveCount(0);
  expect(await finalPut.json()).toMatchObject({
    revision_number: 3,
    concurrency_version: 3,
  });
  const conflictPuts = projectRequests.filter(
    (request) => request.method === "PUT" && request.path === conflictApiPath,
  );
  expect(conflictPuts).toHaveLength(2);
  expect(conflictPuts[0]?.ifMatch).toBe('"1"');
  expect(conflictPuts[1]?.ifMatch).toBe('"2"');

  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  const stored = await page.evaluate(
    () => `${JSON.stringify(localStorage)}${JSON.stringify(sessionStorage)}`,
  );
  expect(stored).not.toMatch(/csrf|token|etag|draft/iu);
  await expect(page.getByRole("link", { name: "返回我的小说" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: /删除|归档|Character|Chapter/u }),
  ).toHaveCount(0);
  expectCleanBrowserAudit(browserAudit);
});
