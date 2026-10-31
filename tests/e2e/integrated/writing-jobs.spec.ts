import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-INT-030 Author creates and resumes a manual chapter writing list", async ({
  page,
  browserAudit,
}) => {
  browserAudit.allowOneExpectedSessionCookie();
  const modelRequests: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (/\/(?:generate|analyze|review|chat\/completions)(?:\/|$)/u.test(path))
      modelRequests.push(path);
  });
  await page.goto("/projects");
  await page.getByRole("textbox", { name: "书名" }).fill("跨章写作测试");
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
  const volumeForm = page
    .getByRole("heading", { name: "创建卷" })
    .locator("xpath=ancestor::form[1]");
  await volumeForm.getByLabel("标题").fill("初卷");
  await volumeForm.getByRole("button", { name: "创建卷" }).click();
  await expect(page.getByText("卷已创建。已选中新卷。")).toBeVisible();
  for (const title of ["晨光", "夜行"]) {
    const chapterForm = page
      .getByRole("heading", { name: "创建章" })
      .locator("xpath=ancestor::form[1]");
    await chapterForm.getByLabel("标题").fill(title);
    await chapterForm.getByRole("button", { name: "创建章" }).click();
    await expect(
      page.getByRole("button", { name: new RegExp(`\\d\\. ${title}`, "u") }),
    ).toBeVisible();
  }
  const jobs = page.getByRole("region", { name: "跨章写作任务" });
  await jobs.getByRole("button", { name: "安排写作任务" }).click();
  await jobs.getByRole("checkbox", { name: /晨光/u }).check();
  await jobs.getByRole("checkbox", { name: /夜行/u }).check();
  await jobs.getByLabel("任务名称").fill("首卷任务");
  await jobs.getByRole("button", { name: "创建任务清单" }).click();
  await expect(
    jobs.getByText("任务已创建；请选择当前章节进入写作台。"),
  ).toBeVisible();
  await expect(jobs.getByText("进行中 · 已完成 0/2 章")).toBeVisible();
  const firstPath = await jobs
    .getByRole("link", { name: "进入当前章节写作" })
    .getAttribute("href");
  await jobs.getByRole("button", { name: "结束本章任务" }).click();
  await expect(
    jobs.getByText("已结束本章任务；章节定稿状态没有改变。"),
  ).toBeVisible();
  await expect(jobs.getByText("进行中 · 已完成 1/2 章")).toBeVisible();
  const secondPath = await jobs
    .getByRole("link", { name: "进入当前章节写作" })
    .getAttribute("href");
  expect(secondPath).not.toBe(firstPath);
  await jobs.getByRole("button", { name: "暂停任务" }).click();
  await expect(jobs.getByText("已暂停 · 已完成 1/2 章")).toBeVisible();
  await jobs.getByRole("button", { name: "收起写作任务" }).click();
  await jobs.getByRole("button", { name: "安排写作任务" }).click();
  await expect(jobs.getByText("已暂停 · 已完成 1/2 章")).toBeVisible();
  await jobs.getByRole("button", { name: "恢复任务" }).click();
  await expect(jobs.getByText("进行中 · 已完成 1/2 章")).toBeVisible();
  await jobs.getByRole("link", { name: "进入当前章节写作" }).click();
  await expect(page).toHaveURL(`${browserAudit.allowedOrigin}${secondPath}`);
  await expect(page.getByLabel("章节正文")).toBeVisible();
  expect(modelRequests).toEqual([]);
  expectCleanBrowserAudit(browserAudit);
});
