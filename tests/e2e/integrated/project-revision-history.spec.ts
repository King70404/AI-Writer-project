import { request as playwrightRequest } from "@playwright/test";

import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

const titles = {
  1: "E2E Project History Revision 01 010",
  2: "E2E Project History Revision 02 010",
  3: "E2E Project History Revision 03 010",
} as const;
const descriptions = {
  1: "E2E-PROJECT-HISTORY-DESCRIPTION-CANARY-010-REVISION-01",
  2: "E2E-PROJECT-HISTORY-DESCRIPTION-CANARY-010-REVISION-02\n第二行",
  3: "E2E-PROJECT-HISTORY-DESCRIPTION-CANARY-010-REVISION-03",
} as const;

function projectPathFromHref(href: string | null): string {
  expect(href).toMatch(/^\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}$/u);
  return href ?? "/invalid-project-link";
}

test("E2E-INT-010 views immutable Project revision history and keyset pages", async ({
  baseURL,
  browserAudit,
  page,
}) => {
  expect(baseURL).toBeDefined();
  const origin = new URL(baseURL ?? "http://invalid").origin;
  browserAudit.allowOneExpectedSessionCookie();

  const pageSecurityRequests: string[] = [];
  const historyRequests: string[] = [];
  page.on("request", (request) => {
    const target = new URL(request.url());
    if (target.pathname === "/api/v1/security/session") {
      pageSecurityRequests.push(target.pathname);
    }
    if (
      /^\/api\/v1\/projects\/prj_.+\/revisions(?:\/\d+)?$/u.test(
        target.pathname,
      )
    ) {
      historyRequests.push(target.toString());
    }
  });

  await page.goto("/projects");
  await expect(page.getByText("还没有项目")).toBeVisible();
  await page.getByRole("textbox", { name: "书名" }).fill(titles[1]);
  await page
    .getByRole("textbox", { name: "一句话简介（可选）" })
    .fill(descriptions[1]);
  await page.getByRole("button", { name: "创建小说" }).click();
  const projectPath = projectPathFromHref(
    await page.getByRole("link", { name: "打开这本小说" }).getAttribute("href"),
  );
  const projectApiPath = `/api/v1${projectPath}`;
  await page.getByRole("link", { name: "打开这本小说" }).click();
  await expect(page).toHaveURL(`${origin}${projectPath}`);
  const projectEditor = page.locator(".project-edit");
  const titleInput = projectEditor.getByRole("textbox", {
    name: "书名",
  });
  const descriptionInput = projectEditor.getByRole("textbox", {
    name: "简介",
  });
  await expect(projectEditor).toBeVisible();
  await expect(titleInput).toHaveValue(titles[1]);
  await expect(descriptionInput).toHaveValue(descriptions[1]);

  for (const revisionNumber of [2, 3] as const) {
    await titleInput.fill(titles[revisionNumber]);
    await expect(titleInput).toHaveValue(titles[revisionNumber]);
    await descriptionInput.fill(descriptions[revisionNumber]);
    await expect(descriptionInput).toHaveValue(descriptions[revisionNumber]);
    await expect(page.getByText("小说信息已保存。")).toHaveCount(0);
    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        new URL(response.url()).pathname === projectApiPath,
    );
    await page.getByRole("button", { name: "保存小说信息" }).click();
    await expect(page.getByText("小说信息已保存。")).toBeVisible();
    await expect(page.getByText("当前修订号")).toHaveCount(0);
    expect(await (await saved).json()).toMatchObject({
      revision_number: revisionNumber,
      concurrency_version: revisionNumber,
    });
  }

  const securityRequestsBeforeHistory = pageSecurityRequests.length;
  await page.getByRole("link", { name: "历史版本" }).click();
  await expect(page.locator(".project-revision-card")).toHaveCount(3);
  await expect(page.locator(".project-revision-card h3")).toHaveText([
    "修订 3",
    "修订 2",
    "修订 1",
  ]);
  await expect(
    page
      .locator(".project-revision-card")
      .filter({ hasText: "修订 3" })
      .getByText("当前修订"),
  ).toBeVisible();
  for (const description of Object.values(descriptions)) {
    await expect(page.getByText(description, { exact: false })).toHaveCount(0);
  }

  for (const revisionNumber of [1, 2, 3] as const) {
    const row = page.locator(".project-revision-card").filter({
      has: page.getByRole("heading", { name: `修订 ${revisionNumber}` }),
    });
    await row.getByRole("button", { name: "查看内容" }).click();
    await expect(
      page.getByRole("heading", {
        level: 3,
        name: `修订 ${revisionNumber}：${titles[revisionNumber]}`,
      }),
    ).toBeFocused();
    await expect(
      page.locator(".project-revision-viewer__description"),
    ).toHaveText(descriptions[revisionNumber]);
  }
  expect(pageSecurityRequests).toHaveLength(securityRequestsBeforeHistory);
  await expect(
    page.getByRole("button", { name: /回滚|恢复|编辑历史|删除|Diff/u }),
  ).toHaveCount(0);

  const external = await playwrightRequest.newContext({ baseURL: origin });
  try {
    const session = await external.get("/api/v1/security/session", {
      headers: { Origin: origin },
    });
    expect(session.status()).toBe(200);
    const sessionBody = (await session.json()) as {
      readonly csrf_token: string;
    };
    let etag = '"3"';
    for (let revisionNumber = 4; revisionNumber <= 21; revisionNumber += 1) {
      const response = await external.put(projectApiPath, {
        data: {
          title: `E2E Project History Revision ${String(revisionNumber).padStart(2, "0")} 010`,
          description: `E2E-PROJECT-HISTORY-DESCRIPTION-CANARY-010-REVISION-${String(revisionNumber).padStart(2, "0")}`,
        },
        headers: {
          Origin: origin,
          "X-CSRF-Token": sessionBody.csrf_token,
          "If-Match": etag,
        },
      });
      expect(response.status()).toBe(200);
      etag = response.headers().etag ?? "missing-etag";
      expect(etag).toBe(`"${revisionNumber}"`);
    }
  } finally {
    await external.dispose();
  }

  const historyPath = `${projectPath}/history`;
  await page.goto(historyPath);
  await expect(page.locator(".project-revision-card")).toHaveCount(20);
  await expect(page.locator(".project-revision-card h3")).toHaveText(
    Array.from({ length: 20 }, (_, index) => `修订 ${21 - index}`),
  );
  const pageUrlBeforeLoadMore = page.url();
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(page.locator(".project-revision-card")).toHaveCount(21);
  await expect(page.locator(".project-revision-card h3")).toHaveText(
    Array.from({ length: 21 }, (_, index) => `修订 ${21 - index}`),
  );
  await expect(page.getByRole("button", { name: "加载更多" })).toHaveCount(0);
  expect(page.url()).toBe(pageUrlBeforeLoadMore);
  expect(
    new Set(await page.locator(".project-revision-card h3").allTextContents())
      .size,
  ).toBe(21);
  expect(
    historyRequests.some((url) => new URL(url).searchParams.has("total")),
  ).toBe(false);
  expect(pageSecurityRequests).toHaveLength(securityRequestsBeforeHistory);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0);
  expect(
    await page.evaluate(
      () => `${JSON.stringify(localStorage)}${JSON.stringify(sessionStorage)}`,
    ),
  ).not.toMatch(/cursor|description|revision/iu);

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "项目修订历史" }),
  ).toBeVisible();
  await expect(page.locator(".project-revision-card")).toHaveCount(20);
  const unknown = await page.goto("/not-a-real-route");
  expect(unknown?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible();
  expectCleanBrowserAudit(browserAudit);
});
