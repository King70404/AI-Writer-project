import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

const MODEL_CALL_PATH =
  /\/(?:generate|analyze|analysis|review|reviews|chat\/completions)(?:\/|$)/u;

function nonWhitespace(text: string): number {
  return Array.from(text).filter((value) => !/\s/u.test(value)).length;
}

test("E2E-INT-024 Workbench summary: server-side totals, editorial state and derived to-dos", async ({
  page,
  browserAudit,
}) => {
  browserAudit.allowOneExpectedSessionCookie();
  const summaryBodies: Promise<string>[] = [];
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (/\/workspace(?:\/|$)|\/editorial-state$/u.test(path))
      summaryBodies.push(response.text());
  });

  // 新建小说、卷与两章；汇总随卷章变化重新读取，空章计 0 字。
  await page.goto("/projects");
  const title = "汇总长篇";
  await page.getByRole("textbox", { name: "书名" }).fill(title);
  await page.getByRole("button", { name: "创建小说" }).click();
  const projectLink = page.getByRole("link", { name: "打开这本小说" });
  const projectPath = await projectLink.getAttribute("href");
  expect(projectPath).toMatch(/^\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}$/u);
  const projectId = projectPath!.split("/")[2];
  await projectLink.click();
  browserAudit.allowExpectedConsoleHttpFailure(
    `/api/v1/projects/${projectId}/outline`,
    404,
  );
  await page.getByRole("link", { name: "大纲与章节" }).click();
  const summary = page.getByRole("region", { name: "写作进度与待处理" });
  await expect(summary.getByTestId("workspace-characters")).toHaveText("0 字");
  await expect(summary.getByText("0 章 / 0 卷")).toBeVisible();
  await expect(summary.getByText("目前没有需要处理的事项。")).toBeVisible();
  const volumeForm = page
    .getByRole("heading", { name: "创建卷" })
    .locator("xpath=ancestor::form[1]");
  await volumeForm.getByLabel("标题").fill("初卷");
  await volumeForm.getByRole("button", { name: "创建卷" }).click();
  await expect(page.getByText("卷已创建。已选中新卷。")).toBeVisible();
  for (const chapterTitle of ["晨雾", "夜航"]) {
    const form = page
      .getByRole("heading", { name: "创建章" })
      .locator("xpath=ancestor::form[1]");
    await form.getByLabel("标题").fill(chapterTitle);
    await form.getByRole("button", { name: "创建章" }).click();
    await expect(
      page.getByRole("button", {
        name: new RegExp(`\\d\\. ${chapterTitle}`, "u"),
      }),
    ).toBeVisible();
  }
  await expect(summary.getByText("2 章 / 1 卷")).toBeVisible();
  await expect(summary.getByText("定稿 0 · 待检查 0 · 草稿 2")).toBeVisible();

  // 写正文并由作者选择“待检查”；状态绑定已保存版本。
  const firstItem = page
    .getByRole("button", { name: "1. 晨雾", exact: true })
    .locator("xpath=ancestor::li[1]");
  const firstPath = await firstItem
    .getByRole("link", { name: "写正文" })
    .getAttribute("href");
  const chapterId = firstPath!.split("/")[4];
  await firstItem.getByRole("link", { name: "写正文" }).click();
  const desk = page.getByRole("region", { name: "第1章 / 晨雾" });
  const status = desk.getByRole("region", { name: "写作状态" });
  const editor = desk.getByLabel("章节正文");
  const text = "晨雾  散开，\n\t渡船靠岸。　旅人上岸！";
  const contentPath = `/api/v1/chapters/${chapterId}/content`;
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === contentPath,
  );
  await editor.fill(text);
  await status.getByRole("button", { name: "立即保存" }).click();
  expect((await saved).status()).toBe(200);
  await expect(status.getByRole("status", { name: "保存状态" })).toHaveText(
    "已保存",
  );
  const editorial = status.getByLabel("章节状态");
  await expect(editorial).toHaveValue("draft");
  await editorial.selectOption("review");
  await expect(status.getByText("已标记为“待检查”。")).toBeVisible();

  // 汇总页：字数由服务端按非空白字符统计；分页读取各章字数。
  // 重新进入结构页会再读一次尚未创建的大纲（预期 404，仅此一次）。
  browserAudit.allowExpectedConsoleHttpFailure(
    `/api/v1/projects/${projectId}/outline`,
    404,
  );
  await page.goto(`/projects/${projectId}/structure`);
  const expected = nonWhitespace(text);
  await expect(summary.getByTestId("workspace-characters")).toHaveText(
    `${expected} 字`,
  );
  await expect(summary.getByText("定稿 0 · 待检查 1 · 草稿 1")).toBeVisible();
  await summary.getByRole("button", { name: "查看各章字数与状态" }).click();
  const table = summary.getByRole("table");
  const firstRow = table.getByRole("row").filter({ hasText: "第1章 · 晨雾" });
  await expect(firstRow.getByRole("cell").nth(1)).toHaveText(String(expected));
  await expect(firstRow.getByRole("cell").nth(2)).toHaveText("待检查");
  const secondRow = table.getByRole("row").filter({ hasText: "第2章 · 夜航" });
  await expect(secondRow.getByRole("cell").nth(1)).toHaveText("0");

  // 定稿后再修改正文：派生“定稿后正文已修改”，首页显示同一项待处理。
  await firstRow.getByRole("link", { name: "第1章 · 晨雾" }).click();
  await expect(editorial).toHaveValue("review");
  await editorial.selectOption("final");
  await expect(status.getByText("已标记为“定稿”。")).toBeVisible();
  const resaved = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === contentPath,
  );
  await editor.fill(`${text}风停。`);
  await status.getByRole("button", { name: "立即保存" }).click();
  expect((await resaved).status()).toBe(200);
  await expect(status.getByText("标记后正文已修改")).toBeVisible();
  await page
    .getByRole("navigation", { name: "主要导航" })
    .getByRole("link", { name: "首页" })
    .click();
  const home = page.getByRole("region", { name: "本书进度" });
  await expect(home.getByTestId("workspace-action-total")).toHaveText("1 项");
  await expect(home.getByTestId("workspace-characters")).toHaveText(
    `${expected + 3} 字`,
  );
  await expect(home.getByText("定稿后正文已修改")).toBeVisible();
  await home.getByRole("link", { name: "第1章 · 晨雾" }).click();
  await expect(page).toHaveURL(
    `${browserAudit.allowedOrigin}/projects/${projectId}/chapters/${chapterId}/write`,
  );
  await status.getByRole("button", { name: "按当前正文重新标记" }).click();
  await expect(status.getByText("已标记为“定稿”。")).toBeVisible();
  await expect(status.getByText("标记后正文已修改")).toHaveCount(0);
  await page
    .getByRole("navigation", { name: "主要导航" })
    .getByRole("link", { name: "首页" })
    .click();
  await expect(home.getByText("目前没有需要处理的事项。")).toBeVisible();
  await expect(home.getByText("定稿 1 · 待检查 0 · 草稿 1")).toBeVisible();

  // 刷新不会改变作者状态；汇总与状态读取不触发任何模型调用。
  await page.reload();
  await expect(home.getByText("定稿 1 · 待检查 0 · 草稿 1")).toBeVisible();
  // 汇总接口只返回统计与标识，不把正文下载到浏览器。
  const bodies = await Promise.all(summaryBodies);
  expect(bodies.length).toBeGreaterThan(0);
  expect(bodies.some((body) => /渡船靠岸|旅人上岸/u.test(body))).toBe(false);
  expect(
    browserAudit.events.filter(
      (event) => event.type === "request" && MODEL_CALL_PATH.test(event.path),
    ),
  ).toEqual([]);
  expectCleanBrowserAudit(browserAudit);
});
