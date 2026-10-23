import { readFile } from "node:fs/promises";

import { expect, test } from "../support/fixture";

test.use({ acceptDownloads: true });

test("E2E-INT-022 Author backup, verify, download and fresh-copy restore", async ({
  page,
  browserAudit,
}) => {
  browserAudit.allowOneExpectedSessionCookie();
  await page.goto("/projects");
  const title = "备份验证：渡口";
  await page.getByRole("textbox", { name: "书名" }).fill(title);
  await page.getByRole("button", { name: "创建小说" }).click();
  await expect(page.getByRole("link", { name: "打开这本小说" })).toBeVisible();

  const navigation = page.getByRole("navigation", { name: "主要导航" });
  await navigation.getByRole("link", { name: "数据备份" }).click();
  await expect(page.getByRole("heading", { name: "备份与恢复" })).toBeVisible();
  await expect(page.getByText("还没有备份。")).toBeVisible();

  const created = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/v1/backups",
  );
  await page.getByRole("button", { name: "立即备份" }).click();
  const createdResponse = await created;
  expect(createdResponse.status()).toBe(201);
  const { backup_id: backupId } = (await createdResponse.json()) as {
    backup_id: string;
  };
  expect(backupId).toMatch(/^\d{8}T\d{6}Z-[0-9a-f]{12}$/u);
  await expect(page.getByText(/已创建并校验备份/u)).toBeVisible();
  const card = page.getByRole("listitem");
  await expect(card).toHaveCount(1);
  await expect(card.getByText(/1 部小说/u)).toBeVisible();

  await card.getByRole("button", { name: "校验完整性" }).click();
  await expect(card.getByRole("status")).toHaveText(/校验通过/u);

  browserAudit.allowOneExpectedBackupDownload();
  const downloadEvent = page.waitForEvent("download");
  await card.getByRole("link", { name: "下载备份" }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe(
    `aiwebnovel-backup-${backupId}.zip`,
  );
  const archivePath = await download.path();
  const archive = await readFile(archivePath);
  // ZIP local file header.
  expect(archive.subarray(0, 4).toString("hex")).toBe("504b0304");

  await card.getByRole("button", { name: "恢复到新文件夹" }).click();
  const restore = card.getByRole("button", { name: "恢复为新副本" });
  await card.getByLabel("新副本文件夹名称").fill("e2e-restored-copy");
  await expect(restore).toBeDisabled();
  await card.getByRole("checkbox").check();
  const restored = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname.endsWith("/restore"),
  );
  await restore.click();
  expect((await restored).status()).toBe(200);
  const result = page
    .getByRole("heading", { name: "已恢复为独立副本" })
    .locator("xpath=ancestor::section[1]");
  await expect(result).toContainText("“e2e-restored-copy”文件夹");
  await expect(result).toContainText("1 部小说");

  browserAudit.allowExpectedConsoleHttpFailure(
    `/api/v1/backups/${backupId}/restore`,
    409,
  );
  const refused = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname.endsWith("/restore"),
  );
  await restore.click();
  expect((await refused).status()).toBe(409);
  await expect(card.getByRole("alert")).toHaveText(/不是空文件夹/u);

  await navigation.getByRole("link", { name: "书架" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
});
