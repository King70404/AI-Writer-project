import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-INT-018 writes and autosaves Chapter prose through the writing workspace", async ({
  page,
  browserAudit,
}) => {
  browserAudit.allowOneExpectedSessionCookie();
  await page.goto("/projects");
  await page
    .getByRole("textbox", { name: "书名" })
    .fill("E2E Chapter Writing 018");
  await page
    .getByRole("textbox", { name: "一句话简介（可选）" })
    .fill("独立写作验收项目");
  await page.getByRole("button", { name: "创建小说" }).click();
  const projectLink = page.getByRole("link", { name: "打开这本小说" });
  const projectPath = await projectLink.getAttribute("href");
  expect(projectPath).toMatch(/^\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}$/u);
  await projectLink.click();
  const projectId = projectPath!.split("/")[2];
  browserAudit.allowExpectedConsoleHttpFailure(
    `/api/v1/projects/${projectId}/outline`,
    404,
  );
  await page.getByRole("link", { name: "大纲与章节" }).click();
  await expect(page).toHaveURL(
    `${browserAudit.allowedOrigin}${projectPath}/structure`,
  );
  await expect(page.getByText("当前尚未创建大纲。")).toBeVisible();

  const outline = page
    .getByRole("heading", { name: "大纲" })
    .locator("xpath=ancestor::section[1]");
  await outline.getByLabel("标题").fill("归途总纲");
  await outline.getByLabel("梗概").fill("旅人归来");
  await outline.getByRole("button", { name: "创建大纲" }).click();
  await expect(page.getByText("大纲已创建。")).toBeVisible();
  const volume = page
    .getByRole("heading", { name: "创建卷" })
    .locator("xpath=ancestor::form[1]");
  await volume.getByLabel("标题").fill("第一卷");
  await volume.getByRole("button", { name: "创建卷" }).click();
  await expect(page.getByText("卷已创建。已选中新卷。")).toBeVisible();
  const chapter = page
    .getByRole("heading", { name: "创建章" })
    .locator("xpath=ancestor::form[1]");
  await chapter.getByLabel("标题").fill("归途");
  await chapter.getByRole("button", { name: "创建章" }).click();
  await expect(page.getByText("章已创建。已选中新章。")).toBeVisible();
  const writeLink = page.getByRole("link", { name: "写正文" });
  const writingPath = await writeLink.getAttribute("href");
  expect(writingPath).toMatch(
    new RegExp(
      `^/projects/${projectId}/chapters/chp_[0-9A-HJKMNP-TV-Z]{26}/write$`,
      "u",
    ),
  );
  const chapterId = writingPath!.split("/")[4];
  const contentPath = `/api/v1/chapters/${chapterId}/content`;
  await writeLink.click();
  await expect(page).toHaveURL(`${browserAudit.allowedOrigin}${writingPath}`);
  const workspace = page.getByRole("region", { name: "第1章 / 归途" });
  await expect(workspace).toBeVisible();
  const editor = workspace.getByLabel("章节正文");
  const status = workspace.getByRole("status", { name: "保存状态" });
  await expect(editor).toHaveValue("");
  const firstText =
    "雨停后，旅人推开了旧院的木门。\n\n廊下的灯还亮着，桌上放着一碗温热的粥。";
  const firstSave = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === contentPath,
  );
  await editor.fill(firstText);
  const saved = await firstSave;
  expect(saved.status()).toBe(200);
  expect(saved.request().headers()["if-match"]).toBe('"1"');
  expect(saved.headers().etag).toBe('"2"');
  await expect(status).toHaveText("已保存");
  await expect(workspace.getByLabel("字符数")).toHaveText(
    `字符数：${firstText.length}`,
  );
  await workspace.getByRole("link", { name: "返回小说结构" }).click();
  await expect(page).toHaveURL(
    `${browserAudit.allowedOrigin}${projectPath}/structure`,
  );
  await expect(
    page.getByRole("heading", { name: "小说结构", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "写正文" }).click();
  await expect(page).toHaveURL(`${browserAudit.allowedOrigin}${writingPath}`);
  await expect(editor).toHaveValue(firstText);
  const finalText = `${firstText}\n\n他放下行囊，终于坐了下来。`;
  const secondSave = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      new URL(response.url()).pathname === contentPath,
  );
  await editor.fill(finalText);
  await workspace.getByRole("button", { name: "立即保存" }).click();
  expect((await secondSave).status()).toBe(200);
  await expect(status).toHaveText("已保存");
  await page.reload();
  await expect(page).toHaveURL(`${browserAudit.allowedOrigin}${writingPath}`);
  await expect(workspace).toBeVisible();
  await expect(editor).toHaveValue(finalText);
  await expect(status).toHaveText("已保存");
  expectCleanBrowserAudit(browserAudit);
});
