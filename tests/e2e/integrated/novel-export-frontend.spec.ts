import { readFile } from "node:fs/promises";

import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test.use({ acceptDownloads: true });

test("E2E-INT-020 Novel text export flow", async ({ page, browserAudit }) => {
  browserAudit.allowOneExpectedSessionCookie();
  await page.goto("/projects");
  const title = "归途：雨夜";
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
  await expect(page.getByText("当前尚未创建大纲。")).toBeVisible();
  const outline = page
    .getByRole("heading", { name: "大纲", exact: true })
    .locator("xpath=ancestor::section[1]");
  await outline.getByLabel("标题").fill("归途总纲");
  await outline.getByRole("button", { name: "创建大纲" }).click();
  await expect(page.getByText("大纲已创建。")).toBeVisible();
  const volume = page
    .getByRole("heading", { name: "创建卷" })
    .locator("xpath=ancestor::form[1]");
  await volume.getByLabel("标题").fill("故乡");
  await volume.getByRole("button", { name: "创建卷" }).click();
  await expect(page.getByText("卷已创建。已选中新卷。")).toBeVisible();
  for (const chapterTitle of ["雨夜", "灯火"]) {
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
  const manuscripts = [
    "雨停后，他推开旧院的木门。\n\n廊下留着一盏灯。",
    "她将温粥放在桌边。\n\n两人终于坐下来。",
  ];
  for (const [index, chapterTitle] of ["雨夜", "灯火"].entries()) {
    const item = page
      .getByRole("button", {
        name: `${index + 1}. ${chapterTitle}`,
        exact: true,
      })
      .locator("xpath=ancestor::li[1]");
    const writingLink = item.getByRole("link", { name: "写正文" });
    const path = await writingLink.getAttribute("href");
    expect(path).toMatch(/\/chapters\/chp_[0-9A-HJKMNP-TV-Z]{26}\/write$/u);
    const chapterId = path!.split("/")[4];
    await writingLink.click();
    const editor = page.getByLabel("章节正文");
    await expect(editor).toHaveValue("");
    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === "PUT" &&
        new URL(response.url()).pathname ===
          `/api/v1/chapters/${chapterId}/content`,
    );
    await editor.fill(manuscripts[index]);
    expect((await saved).status()).toBe(200);
    await expect(page.getByRole("status", { name: "保存状态" })).toHaveText(
      "已保存",
    );
    await page.getByRole("link", { name: "返回小说结构" }).click();
    await expect(
      page.getByRole("button", { name: `2. 灯火`, exact: true }),
    ).toBeVisible();
  }
  await page.getByRole("link", { name: "返回Project详情" }).click();
  const downloadEvent = page.waitForEvent("download");
  browserAudit.allowOneExpectedManuscriptDownload(`${title}.txt`);
  await page.getByRole("button", { name: "导出小说" }).click();
  const download = await downloadEvent;
  try {
    expect(download.suggestedFilename()).toBe(`${title}.txt`);
    expect(download.suggestedFilename()).not.toMatch(/[<>:"/\\|?*]/u);
    const path = await download.path();
    expect(path).not.toBeNull();
    const text = await readFile(path, "utf8");
    expect(text).toBe(
      `《${title}》\n\n第1卷 故乡\n\n第1章 雨夜\n\n${manuscripts[0]}\n\n第2章 灯火\n\n${manuscripts[1]}\n`,
    );
    expect(text.indexOf("第1章")).toBeLessThan(text.indexOf("第2章"));
    expect(text).not.toContain("\r");
  } finally {
    await download.delete();
  }
  expectCleanBrowserAudit(browserAudit);
});
