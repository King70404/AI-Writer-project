import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-INT-028 Import a manuscript into a new book without calling a model", async ({
  page,
  browserAudit,
}) => {
  browserAudit.allowOneExpectedSessionCookie();
  const modelRequests: string[] = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (/\/(?:generate|analyze|review|chat\/completions)(?:\/|$)/u.test(path)) {
      modelRequests.push(path);
    }
  });

  await page.goto("/projects");
  const importer = page.getByRole("region", { name: "导入旧稿" });
  await importer.getByRole("button", { name: "导入旧稿", exact: true }).click();
  await importer
    .getByLabel("或粘贴旧稿")
    .fill("第一章 晨光\n城门打开。\n第二章 夜行\n旅人抵达渡口。");
  await importer.getByLabel("章节标题格式").selectOption("chinese");
  await importer.getByRole("button", { name: "预览分章" }).click();
  await expect(importer.getByText(/共 2 章/)).toBeVisible();
  await expect(importer.getByLabel("第 1 章正文（选择拆分位置）")).toHaveValue(
    "城门打开。\n",
  );
  await expect(importer.getByLabel("第 2 章正文（选择拆分位置）")).toHaveValue(
    "旅人抵达渡口。",
  );
  await importer.getByLabel("新小说书名").fill("旧稿测试作品");
  await importer.getByRole("button", { name: "确认导入为新小说" }).click();
  await expect(importer.getByText("小说已创建，旧稿导入完成。")).toBeVisible();
  await importer.getByRole("link", { name: "打开第一章" }).click();
  await expect(page.getByLabel("章节正文")).toHaveValue("城门打开。\n");
  expect(modelRequests).toEqual([]);
  expectCleanBrowserAudit(browserAudit);
});
