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
  const continued = "续写候选文本：门外传来轻轻的脚步声。".repeat(12);
  const rewritten = "改写候选文本：夜雨终于停歇。".repeat(16);
  let rejectRequest = false;
  let analysisReply: string | null = null;
  const server = createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk: string) => {
      body += chunk;
    });
    request.on("end", () => {
      requests.push({ method: request.method, path: request.url, body });
      if (rejectRequest) {
        response.writeHead(429, { "Content-Type": "application/json" });
        response.end(JSON.stringify({ error: { message: "test rate limit" } }));
        return;
      }
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          choices: [
            {
              message: {
                content:
                  analysisReply ??
                  (requests.length === 1 ? continued : rewritten),
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
    const projectApiPath = `/api/v1${projectPath}`;
    // 升级 AI 工作流前，工作台汇总与待办按设计返回 503；结构变更会重新读取，先登记本轮预期错误。
    browserAudit.allowExpectedConsoleHttpFailure(
      `${projectApiPath}/workspace`,
      503,
      8,
    );
    browserAudit.allowExpectedConsoleHttpFailure(
      `${projectApiPath}/workspace/actions`,
      503,
      8,
    );
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
    const writingPath = await page
      .getByRole("link", { name: "写正文" })
      .getAttribute("href");
    const oldChapterId = writingPath?.match(
      /\/chapters\/(chp_[0-9A-HJKMNP-TV-Z]{26})\/write$/u,
    )?.[1];
    expect(oldChapterId).toBeTruthy();
    browserAudit.allowExpectedConsoleHttpFailure("/api/v1/ai/models", 503);
    browserAudit.allowExpectedConsoleHttpFailure(
      `/api/v1/chapters/${oldChapterId}/ai/runs`,
      503,
    );
    browserAudit.allowExpectedConsoleHttpFailure(
      `/api/v1/chapters/${oldChapterId}/editorial-state`,
      503,
      4,
    );
    await page.getByRole("link", { name: "写正文" }).click();
    const editor = page.getByLabel("章节正文");
    const status = page.getByRole("status", { name: "保存状态" });
    const initial = "雨停后，旅人推开了旧院的木门。";
    await editor.fill(initial);
    await expect(status).toHaveText("已保存");
    const enableAI = page.getByRole("button", {
      name: "备份并启用 AI 协作",
      exact: true,
    });
    await expect(enableAI).toBeVisible();
    await enableAI.click();
    await expect(enableAI).toHaveCount(0);
    await expect(editor).toHaveValue(initial);
    await page.getByText("模型配置", { exact: true }).click();
    await page.getByLabel("配置名称", { exact: true }).fill("云端配置保存测试");
    await page.getByLabel("服务位置", { exact: true }).selectOption("cloud");
    await page
      .getByLabel("服务地址", { exact: true })
      .fill("https://api.example.com");
    await page.getByLabel("模型名称", { exact: true }).fill("cloud-test-model");
    await page
      .getByLabel("API Key（留空保留已有密钥）")
      .fill("e2e-placeholder-not-a-real-key");
    await page
      .getByRole("button", { name: "保存模型配置", exact: true })
      .click();
    await expect(
      page.getByText(
        "配置已保存，已选中“云端配置保存测试”。密钥不会回显；尚未检查服务连接。",
      ),
    ).toBeVisible();
    await expect(page.getByLabel("API Key（留空保留已有密钥）")).toHaveValue(
      "",
    );
    await expect(
      page.getByLabel("使用模型").locator("option:checked"),
    ).toHaveText("云端配置保存测试 · 云端");
    await page.reload();
    await expect(
      page
        .getByLabel("使用模型")
        .getByRole("option", { name: "云端配置保存测试 · 云端", exact: true }),
    ).toHaveCount(1);
    await page.getByText("模型配置", { exact: true }).click();
    await page.getByRole("button", { name: "添加新模型", exact: true }).click();
    await page.getByLabel("配置名称", { exact: true }).fill("新保存的写作模型");
    await page
      .getByLabel("服务地址", { exact: true })
      .fill("http://127.0.0.1:18123");
    await page.getByLabel("模型名称", { exact: true }).fill("e2e-ai-model");
    await page
      .getByRole("button", { name: "保存模型配置", exact: true })
      .click();
    await expect(
      page.getByText(
        "配置已保存，已选中“新保存的写作模型”。密钥不会回显；尚未检查服务连接。",
      ),
    ).toBeVisible();
    await expect(
      page.getByLabel("使用模型").locator("option:checked"),
    ).toHaveText("新保存的写作模型 · 本地");
    await page.reload();
    await expect(
      page
        .getByLabel("使用模型")
        .getByRole("option", { name: "新保存的写作模型 · 本地", exact: true }),
    ).toHaveCount(1);
    await page
      .getByLabel("使用模型")
      .selectOption({ label: "新保存的写作模型 · 本地" });
    await page.getByLabel("额外要求（可选）").fill("增加紧张感");
    await page.getByRole("button", { name: "准备续写", exact: true }).click();
    await expect(page.getByLabel("本次发送的小说上下文")).toHaveValue(
      new RegExp(initial),
    );
    expect(requests).toHaveLength(0);
    await page
      .getByRole("button", { name: "确认发送并生成", exact: true })
      .click();
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
    await page.reload();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(continued);
    await page.getByRole("button", { name: "暂停任务", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "恢复任务", exact: true }),
    ).toBeVisible();
    expect(requests).toHaveLength(1);
    await page.getByRole("button", { name: "恢复任务", exact: true }).click();
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
    const rewrite = page.getByRole("button", { name: "准备改写选中文本" });
    await expect(rewrite).toBeEnabled();
    await rewrite.click();
    await page
      .getByRole("button", { name: "确认发送并生成", exact: true })
      .click();
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
    const preparing = page.waitForResponse(
      (response) =>
        response.url().endsWith("/ai/runs") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "准备续写", exact: true }).click();
    const prepared = await preparing;
    const run = (await prepared.json()) as { run_id: string };
    const generatePath = `/api/v1/chapters/${oldChapterId}/ai/runs/${run.run_id}/generate`;
    browserAudit.allowExpectedConsoleHttpFailure(generatePath, 502);
    rejectRequest = true;
    const currentTask = page.getByRole("region", { name: "当前AI任务" });
    const taskStatus = currentTask
      .getByRole("status")
      .filter({ hasText: "已生成" });
    await currentTask
      .getByRole("button", { name: "确认发送并生成", exact: true })
      .click();
    await expect(currentTask.getByRole("alert")).toContainText("频繁");
    await expect(currentTask.getByRole("alert")).toBeInViewport();
    await expect(taskStatus).toContainText("已暂停");
    await expect(taskStatus).toContainText("1/5");
    await expect(editor).toHaveValue(final);
    expect(requests).toHaveLength(3);
    await currentTask.getByRole("button", { name: "恢复任务" }).click();
    await expect(taskStatus).toContainText("可以生成下一段");
    expect(requests).toHaveLength(3);
    rejectRequest = false;
    await currentTask
      .getByRole("button", { name: "确认发送并生成", exact: true })
      .click();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(rewritten);
    await expect(editor).toHaveValue(final);
    expect(requests).toHaveLength(4);

    await page.getByRole("button", { name: "丢弃", exact: true }).click();
    await page
      .getByLabel("使用模型")
      .selectOption({ label: "新保存的写作模型 · 本地" });
    await page.getByRole("tab", { name: "准备", exact: true }).click();
    const workbench = page.getByRole("region", {
      name: "范文分析与章节规划",
      exact: true,
    });
    const sourceText = "旅人敲了两下门。屋内的人没有答话，只把烛火移到窗后。";
    await workbench
      .getByLabel("范文名称", { exact: true })
      .fill("迟疑与动作的范文");
    await workbench
      .getByRole("textbox", { name: "范文原文", exact: true })
      .fill(sourceText);
    await workbench.getByRole("button", { name: "保存范文并准备分析" }).click();
    await expect(
      workbench.getByRole("button", { name: "确认发送并分析范文" }),
    ).toBeEnabled();
    expect(requests).toHaveLength(4);
    analysisReply = JSON.stringify({
      units: ["旅人敲了两下门。", "屋内的人没有答话，只把烛火移到窗后。"].map(
        (text, index) => ({
          unit_id: `u${index + 1}`,
          quote: text.slice(0, 3),
          function: "用动作延迟信息揭示",
          effect: "读者察觉人物有所保留",
          rationale: "可能让迟疑以可见行动表现出来",
          transfer: "新场景用物件动作承接人物的试探",
        }),
      ),
      long_form_notes: "围绕本章重点持续表现人物意图，跨章保留后果。",
      rules: [
        {
          name: "动作承接",
          instruction: "先写试探动作，再给有限回答。",
          applies_to: "盘问与对峙",
        },
      ],
    });
    await workbench.getByRole("button", { name: "确认发送并分析范文" }).click();
    await expect(
      workbench.getByText("写作原因（推测）", { exact: true }),
    ).toHaveCount(2);
    expect(requests).toHaveLength(5);
    expect(JSON.stringify(JSON.parse(requests[4].body))).toContain(
      "旅人敲了两下门",
    );
    await expect(editor).toHaveValue(final);
    await workbench
      .getByRole("button", { name: "编辑并提炼这份范文的写作规则" })
      .click();
    await workbench
      .getByLabel("规则集名称", { exact: true })
      .fill("迟疑与行动方法");
    await workbench
      .getByRole("textbox", { name: "规则 1 操作方法", exact: true })
      .fill("用试探动作承接对话，重要回答保留余地。");
    await workbench
      .getByRole("button", { name: "确认保存写作规则", exact: true })
      .click();
    await workbench
      .getByRole("checkbox", { name: "迟疑与行动方法 · 版本 1", exact: true })
      .check();
    await workbench
      .getByLabel("章节重点 1", { exact: true })
      .fill("旅人决定查清渡口失踪事件");
    await workbench.getByLabel("本章目标字数", { exact: true }).fill("3200");
    await workbench
      .getByRole("textbox", { name: "核心冲突", exact: true })
      .fill("得到消息与保护证人的冲突");
    await workbench
      .getByRole("textbox", { name: "承接前文与后续伏笔", exact: true })
      .fill("保留上一章手腕受伤的影响");
    await workbench
      .getByRole("button", { name: "增加场景", exact: true })
      .click();
    await workbench.getByLabel("场景 1 名称", { exact: true }).fill("渡口试探");
    await workbench
      .getByRole("button", { name: "为场景 1 增加推进点", exact: true })
      .click();
    await workbench
      .getByRole("textbox", { name: "场景 1 推进点 1 行动", exact: true })
      .fill("借搬货接近证人");
    await workbench
      .getByRole("textbox", { name: "场景 1 推进点 1 变化", exact: true })
      .fill("证人愿意透露船名");
    await expect(
      page.getByText(
        "章节规划有未保存修改；可保存并进入生成准备。此操作不会发送模型请求。",
      ),
    ).toBeVisible();
    await page.getByRole("tab", { name: "生成", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "准备续写", exact: true }),
    ).toBeDisabled();
    await page.getByRole("tab", { name: "准备", exact: true }).click();
    await workbench
      .getByRole("button", { name: "保存规划并进入生成准备", exact: true })
      .click();
    await expect(
      page.getByRole("tab", { name: "生成", exact: true }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(
      page.getByRole("button", { name: "准备续写", exact: true }),
    ).toBeFocused();
    expect(requests).toHaveLength(5);
    await page.reload();
    await page.getByRole("tab", { name: "准备", exact: true }).click();
    await expect(
      workbench.getByLabel("场景 1 名称", { exact: true }),
    ).toHaveValue("渡口试探");
    await expect(
      workbench.getByRole("checkbox", {
        name: "迟疑与行动方法 · 版本 1",
        exact: true,
      }),
    ).toBeChecked();
    expect(requests).toHaveLength(5);
    await page.getByRole("tab", { name: "生成", exact: true }).click();
    await page
      .getByLabel("使用模型")
      .selectOption({ label: "新保存的写作模型 · 本地" });
    await page.getByRole("button", { name: "准备续写", exact: true }).click();
    await expect(page.getByLabel("本次发送的小说上下文")).toHaveValue(
      /用试探动作承接对话/u,
    );
    const frozen = await page.getByLabel("本次发送的小说上下文").inputValue();
    expect(frozen).toContain("渡口试探");
    expect(frozen).not.toContain(sourceText);
    await page.getByRole("tab", { name: "准备", exact: true }).click();
    await workbench
      .getByRole("textbox", { name: "核心冲突", exact: true })
      .fill("准备之后修改的冲突");
    await workbench
      .getByRole("button", { name: "保存章节规划", exact: true })
      .click();
    await expect(workbench.getByText(/规划已保存 · 版本 2/u)).toBeVisible();
    await expect(page.getByLabel("本次发送的小说上下文")).toHaveValue(frozen);
    analysisReply = null;
    await page.getByRole("tab", { name: "生成", exact: true }).click();
    await currentTask
      .getByRole("button", { name: "确认发送并生成", exact: true })
      .click();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(rewritten);
    expect(requests).toHaveLength(6);
    const generationPayload = JSON.stringify(JSON.parse(requests[5].body));
    expect(generationPayload).toContain("用试探动作承接对话");
    expect(generationPayload).not.toContain("准备之后修改的冲突");
    expect(generationPayload).not.toContain("旅人敲了两下门");
    await expect(editor).toHaveValue(final);
    await page.getByRole("button", { name: "追加到正文", exact: true }).click();
    await expect(editor).toHaveValue(`${final}\n\n${rewritten}`);
    await expect(status).toHaveText("已保存");
    expectCleanBrowserAudit(browserAudit);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
