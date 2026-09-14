import { request as playwrightRequest } from "@playwright/test";

import {
  expectCleanBrowserAudit,
  expectNoEngineeringMetadata,
} from "../support/assertions";
import { expect, test } from "../support/fixture";

const projectTitle = "E2E Story Bible Frontend Owner 012";
const projectDescription = "E2E-STORY-BIBLE-PROJECT-DESCRIPTION-CANARY-012";
const initialTitle = "E2E Story Bible UI Initial 012";
const initialContent = "E2E-STORY-BIBLE-UI-CONTENT-CANARY-012-V1\nsecond line";
const revisedTitle = "E2E Story Bible UI Revised 012";
const revisedContent = "E2E-STORY-BIBLE-UI-CONTENT-CANARY-012-V2\nreplacement";
const externalTitle = "E2E Story Bible External 012";
const externalContent = "E2E-STORY-BIBLE-UI-CONTENT-CANARY-012-V3";
const localTitle = "E2E Story Bible Local Rebased 012";
const localContent =
  "E2E-STORY-BIBLE-UI-CONTENT-CANARY-012-V4\npreserved draft";

function projectPathFromHref(href: string | null): string {
  expect(href).toMatch(/^\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}$/u);
  return href ?? "/invalid-project-link";
}

test("E2E-INT-012 exercises Story Bible creation, editing, and explicit conflict resolution", async ({
  baseURL,
  browserAudit,
  page,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  browserAudit.allowOneExpectedSessionCookie();

  const storyRequests: Array<{
    readonly method: string;
    readonly path: string;
    readonly ifMatch: string | undefined;
    readonly body: string | null;
  }> = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.includes("/story-bible")) {
      storyRequests.push({
        method: request.method(),
        path,
        ifMatch: request.headers()["if-match"],
        body: request.postData(),
      });
    }
  });

  await page.goto("/projects");
  await expect(page.getByText("还没有项目")).toBeVisible();
  await page.getByRole("textbox", { name: "书名" }).fill(projectTitle);
  await page
    .getByRole("textbox", { name: "一句话简介（可选）" })
    .fill(projectDescription);
  await page.getByRole("button", { name: "创建小说" }).click();

  const projectLink = page.getByRole("link", { name: "打开这本小说" });
  const projectPath = projectPathFromHref(
    await projectLink.getAttribute("href"),
  );
  const nestedApiPath = `/api/v1${projectPath}/story-bible`;
  await projectLink.click();
  await expect(
    page.getByRole("heading", { level: 2, name: projectTitle }),
  ).toBeVisible();
  const storyLink = page.getByRole("link", { name: "小说设定" });
  expect(await storyLink.getAttribute("href")).toBe(
    `${projectPath}/story-bible`,
  );
  browserAudit.allowExpectedConsoleHttpFailure(nestedApiPath, 404);
  await storyLink.click();

  await expect(
    page.getByRole("heading", {
      level: 3,
      name: "创建小说设定",
      exact: true,
    }),
  ).toBeVisible();
  const initialGets = storyRequests.filter(
    (request) => request.method === "GET" && request.path === nestedApiPath,
  ).length;
  expect(initialGets).toBe(1);

  await page.getByRole("textbox", { name: "设定标题" }).fill(initialTitle);
  await page.getByRole("textbox", { name: "设定正文" }).fill(initialContent);
  const createResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === nestedApiPath,
  );
  await page.getByRole("button", { name: "创建小说设定" }).click();
  const created = await createResponsePromise;
  expect(created.status()).toBe(201);
  expect(created.headers().etag).toBe('"1"');
  expect(created.headers().location).toMatch(
    /^\/api\/v1\/story-bibles\/sbl_[0-9A-HJKMNP-TV-Z]{26}$/u,
  );
  const directApiPath = created.headers().location ?? "/invalid-story-bible";
  expect(await created.json()).toMatchObject({
    revision_number: 1,
    concurrency_version: 1,
  });
  await expect(
    page.getByRole("heading", { level: 2, name: initialTitle }),
  ).toBeVisible();
  await expectNoEngineeringMetadata(page);
  await expect(
    page.getByRole("heading", { name: "设定保存信息" }),
  ).toBeVisible();
  await expect(page.locator(".story-bible-metadata time")).toHaveCount(2);
  expect(
    storyRequests.filter(
      (request) => request.method === "GET" && request.path === nestedApiPath,
    ),
  ).toHaveLength(initialGets);

  await page.reload();
  await expect(
    page.getByRole("heading", { level: 2, name: initialTitle }),
  ).toBeVisible();
  await expect(page.getByRole("textbox", { name: "小说设定正文" })).toHaveValue(
    initialContent,
  );

  await page.getByRole("textbox", { name: "小说设定标题" }).fill(revisedTitle);
  await page
    .getByRole("textbox", { name: "小说设定正文" })
    .fill(revisedContent);
  const revisionTwoPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === directApiPath,
  );
  await page.getByRole("button", { name: "保存完整修订", exact: true }).click();
  const revisionTwo = await revisionTwoPromise;
  expect(revisionTwo.status()).toBe(200);
  expect(revisionTwo.headers().etag).toBe('"2"');
  await expect(page.getByText("小说设定修订已保存。")).toBeVisible();

  await page.reload();
  await expect(
    page.getByRole("heading", { level: 2, name: revisedTitle }),
  ).toBeVisible();
  await expect(page.getByRole("textbox", { name: "小说设定正文" })).toHaveValue(
    revisedContent,
  );

  const external = await playwrightRequest.newContext({ baseURL: origin });
  try {
    const externalSession = await external.get("/api/v1/security/session", {
      headers: { Origin: origin },
    });
    expect(externalSession.status()).toBe(200);
    const sessionBody = (await externalSession.json()) as {
      readonly csrf_token: string;
    };
    const externalRevision = await external.put(directApiPath, {
      data: { title: externalTitle, content: externalContent },
      headers: {
        Origin: origin,
        "X-CSRF-Token": sessionBody.csrf_token,
        "If-Match": '"2"',
      },
    });
    expect(externalRevision.status()).toBe(200);
    expect(externalRevision.headers().etag).toBe('"3"');
  } finally {
    await external.dispose();
  }

  await page.getByRole("textbox", { name: "小说设定标题" }).fill(localTitle);
  await page.getByRole("textbox", { name: "小说设定正文" }).fill(localContent);
  const getsBeforeConflict = storyRequests.filter(
    (request) => request.method === "GET" && request.path === directApiPath,
  ).length;
  const putsBeforeConflict = storyRequests.filter(
    (request) => request.method === "PUT" && request.path === directApiPath,
  ).length;
  browserAudit.allowExpectedConsoleHttpFailure(directApiPath, 412);
  await page.getByRole("button", { name: "保存完整修订", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "检测到小说设定版本冲突",
      exact: true,
    }),
  ).toBeFocused();
  await expect(page.getByText(/当前草稿基于版本 2/u)).toBeVisible();
  await expect(page.getByRole("textbox", { name: "小说设定标题" })).toHaveValue(
    localTitle,
  );
  expect(
    storyRequests.filter(
      (request) => request.method === "GET" && request.path === directApiPath,
    ),
  ).toHaveLength(getsBeforeConflict);
  expect(
    storyRequests.filter(
      (request) => request.method === "PUT" && request.path === directApiPath,
    ),
  ).toHaveLength(putsBeforeConflict + 1);

  await page.getByRole("button", { name: "读取最新版本" }).click();
  const latestVersion = page.getByRole("region", {
    name: "服务器最新版本",
    exact: true,
  });
  const localDraft = page.getByRole("region", {
    name: "当前本地草稿",
    exact: true,
  });
  await expect(
    latestVersion.getByText(externalTitle, { exact: true }),
  ).toBeVisible();
  await expect(localDraft.getByText(localTitle, { exact: true })).toBeVisible();
  expect(
    storyRequests.filter(
      (request) => request.method === "GET" && request.path === directApiPath,
    ),
  ).toHaveLength(getsBeforeConflict + 1);
  await page
    .getByRole("button", {
      name: "保留草稿并以服务器版本建立基线",
    })
    .click();
  await expect(
    page.getByText("当前草稿将在下次手动保存时完整替换服务器上的标题和正文。"),
  ).toBeVisible();

  const finalSavePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === directApiPath &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "保存完整修订", exact: true }).click();
  const finalSave = await finalSavePromise;
  expect(finalSave.headers().etag).toBe('"4"');
  await expect(page.getByText("小说设定修订已保存。")).toBeVisible();
  expect(await finalSave.json()).toMatchObject({
    revision_number: 4,
    concurrency_version: 4,
  });
  await expectNoEngineeringMetadata(page);

  const storyPuts = storyRequests.filter(
    (request) => request.method === "PUT" && request.path === directApiPath,
  );
  expect(storyPuts).toHaveLength(3);
  expect(storyPuts.map((request) => request.ifMatch)).toEqual([
    '"1"',
    '"2"',
    '"3"',
  ]);
  expect(
    storyPuts.map((request) => JSON.parse(request.body ?? "null") as unknown),
  ).toEqual([
    { title: revisedTitle, content: revisedContent },
    { title: localTitle, content: localContent },
    { title: localTitle, content: localContent },
  ]);

  await page.reload();
  await expect(
    page.getByRole("heading", { level: 2, name: localTitle }),
  ).toBeVisible();
  await expect(page.getByRole("textbox", { name: "小说设定正文" })).toHaveValue(
    localContent,
  );
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(page.url()).not.toMatch(/etag|csrf|token|content|draft/iu);
  await expect(
    page.getByRole("link", {
      name: /Character|World|Power|删除|归档|恢复|回滚|Diff/iu,
    }),
  ).toHaveCount(0);
  expectCleanBrowserAudit(browserAudit);
});
