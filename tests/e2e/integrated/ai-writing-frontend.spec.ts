import { createServer } from "node:http";
import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-INT-019 AI writing assistance flow", async ({
  page,
  browserAudit,
}) => {
  const requests: {
    method: string | undefined;
    path: string | undefined;
    body: string;
  }[] = [];
  const continued = "续写候选文本：门外传来轻轻的脚步声。";
  const rewritten = "改写候选文本：夜雨终于停歇";
  const server = createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk: string) => {
      body += chunk;
    });
    request.on("end", () => {
      requests.push({ method: request.method, path: request.url, body });
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          choices: [
            {
              message: {
                content: requests.length === 1 ? continued : rewritten,
              },
            },
          ],
        }),
      );
    });
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(18123, "127.0.0.1", resolve);
  });
  try {
    browserAudit.allowOneExpectedSessionCookie();
    await page.goto("/projects");
    await page
      .getByRole("textbox", { name: "书名" })
      .fill("E2E AI Writing 019");
    await page.getByRole("button", { name: "创建小说" }).click();
    const projectLink = page.getByRole("link", { name: "打开这本小说" });
    const projectPath = await projectLink.getAttribute("href");
    expect(projectPath).toMatch(/^\/projects\/prj_[0-9A-HJKMNP-TV-Z]{26}$/u);
    await projectLink.click();
    browserAudit.allowExpectedConsoleHttpFailure(
      `/api/v1${projectPath}/outline`,
      404,
    );
    await page.getByRole("link", { name: "大纲与章节" }).click();
    await expect(page.getByText("当前尚未创建大纲。")).toBeVisible();
    const outline = page
      .getByRole("heading", { name: "大纲" })
      .locator("xpath=ancestor::section[1]");
    await outline.getByLabel("标题").fill("归途总纲");
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
    await page.getByRole("link", { name: "写正文" }).click();
    const editor = page.getByLabel("章节正文");
    const status = page.getByRole("status", { name: "保存状态" });
    const initial = "雨停后，旅人推开了旧院的木门。";
    await editor.fill(initial);
    await expect(status).toHaveText("已保存");
    await page.getByLabel("额外要求（可选）").fill("增加紧张感");
    await page.getByRole("button", { name: "续写", exact: true }).click();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(continued);
    await expect(editor).toHaveValue(initial);
    expect(requests).toHaveLength(1);
    expect(requests[0].method).toBe("POST");
    expect(requests[0].path).toBe("/chat/completions");
    expect(JSON.parse(requests[0].body)).toMatchObject({
      model: "e2e-ai-model",
      stream: false,
    });
    expect(requests[0].body).toContain("messages");
    expect(JSON.stringify(JSON.parse(requests[0].body))).toContain(initial);
    await page.getByRole("button", { name: "追加到正文" }).click();
    const appended = `${initial}\n\n${continued}`;
    await expect(editor).toHaveValue(appended);
    await expect(status).toHaveText("已保存");
    await page.reload();
    await expect(editor).toHaveValue(appended);
    await expect(page.getByLabel("AI候选文本")).toHaveCount(0);
    await editor.evaluate((element: HTMLTextAreaElement) => {
      element.focus();
      element.setSelectionRange(0, 3);
      document.dispatchEvent(new Event("selectionchange"));
      element.dispatchEvent(
        new KeyboardEvent("keyup", { bubbles: true, key: "Shift" }),
      );
    });
    const rewrite = page.getByRole("button", { name: "改写选中文本" });
    await expect(rewrite).toBeEnabled();
    await rewrite.click();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(rewritten);
    await expect(editor).toHaveValue(appended);
    expect(requests).toHaveLength(2);
    expect(requests[1].method).toBe("POST");
    expect(requests[1].path).toBe("/chat/completions");
    expect(JSON.parse(requests[1].body)).toMatchObject({
      model: "e2e-ai-model",
      stream: false,
    });
    expect(JSON.stringify(JSON.parse(requests[1].body))).toContain("雨停后");
    await page.getByRole("button", { name: "替换选中文本" }).click();
    const final = rewritten + appended.slice(3);
    await expect(editor).toHaveValue(final);
    await expect(status).toHaveText("已保存");
    await page.reload();
    await expect(editor).toHaveValue(final);
    await expect(status).toHaveText("已保存");
    expectCleanBrowserAudit(browserAudit);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
