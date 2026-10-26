import { createServer } from "node:http";
import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-INT-025 Candidate comparison and chapter model usage: reported tokens vs unknown, nothing auto-adopted", async ({
  page,
  browserAudit,
}) => {
  const requests: { path: string | undefined; body: string }[] = [];
  const continued = "门外的风声停了，旅人侧耳听见远处的马蹄。".repeat(10);
  const rewritten = "灯火忽明忽暗，旅人抖落斗篷上的雨水。".repeat(12);
  // 第一次请求返回 OpenAI 兼容的 usage；第二次完全省略 usage（应记为未知，不按 0 计）。
  const server = createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk: string) => {
      body += chunk;
    });
    request.on("end", () => {
      requests.push({ path: request.url, body });
      const first = requests.length === 1;
      const payload: Record<string, unknown> = {
        choices: [{ message: { content: first ? continued : rewritten } }],
      };
      if (first) {
        payload.usage = {
          prompt_tokens: 321,
          completion_tokens: 123,
          total_tokens: 444,
        };
      }
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(payload));
    });
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(18123, "127.0.0.1", resolve);
  });
  try {
    browserAudit.allowOneExpectedSessionCookie();
    await page.goto("/projects");
    const origin = new URL(page.url()).origin;
    const session = (await (
      await page.request.get("/api/v1/security/session")
    ).json()) as { csrf_token: string };
    const headers = { "X-CSRF-Token": session.csrf_token, Origin: origin };
    const projectResponse = await page.request.post("/api/v1/projects", {
      headers,
      data: { title: "候选对照与用量" },
    });
    expect(projectResponse.status()).toBe(201);
    const project = ((await projectResponse.json()) as { project_id: string })
      .project_id;
    const volumeResponse = await page.request.post(
      `/api/v1/projects/${project}/volumes`,
      { headers, data: { title: "第一卷", summary: "", position: 1 } },
    );
    expect(volumeResponse.status()).toBe(201);
    const volume = ((await volumeResponse.json()) as { volume_id: string })
      .volume_id;
    const chapterResponse = await page.request.post(
      `/api/v1/projects/${project}/volumes/${volume}/chapters`,
      { headers, data: { title: "雨夜", summary: "", position: 1 } },
    );
    expect(chapterResponse.status()).toBe(201);
    const chapter = ((await chapterResponse.json()) as { chapter_id: string })
      .chapter_id;
    const initial = "灯火摇曳，旅人把湿透的斗篷挂在门边。";
    const saved = await page.request.put(
      `/api/v1/chapters/${chapter}/content`,
      {
        headers: { ...headers, "If-Match": chapterResponse.headers().etag },
        data: { content: initial },
      },
    );
    expect(saved.status()).toBe(200);
    const serverContent = async () =>
      JSON.stringify(
        await (
          await page.request.get(`/api/v1/chapters/${chapter}/content`)
        ).json(),
      );

    await page.goto(`/projects/${project}/chapters/${chapter}/write`);
    const editor = page.getByLabel("章节正文");
    await expect(editor).toHaveValue(initial);
    const assistant = page.getByRole("region", { name: "AI写作助手" });
    const tabs = assistant.getByRole("tablist", { name: "AI 助手分区" });
    await expect(tabs.getByRole("tab", { name: "生成" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    // 本机模型（无需密钥存储），指向受控假模型服务。
    const summary = assistant.getByRole("region", { name: "当前模型" });
    // 模型状态异步读取；先等待读取结束，避免在“添加模型/管理模型”切换期间点击已失效的按钮。
    await expect(summary.getByText("正在读取模型配置…")).toHaveCount(0);
    if ((await summary.getByRole("button", { name: "添加模型" }).count()) > 0) {
      await summary.getByRole("button", { name: "添加模型" }).click();
    } else {
      await summary.getByRole("button", { name: "管理模型" }).click();
      await assistant.getByRole("button", { name: "添加新模型" }).click();
    }
    await assistant
      .getByLabel("配置名称", { exact: true })
      .fill("用量测试模型");
    await assistant
      .getByLabel("服务地址", { exact: true })
      .fill("http://127.0.0.1:18123");
    await assistant
      .getByLabel("模型名称", { exact: true })
      .fill("e2e-ai-model");
    await assistant
      .getByRole("button", { name: "保存模型配置", exact: true })
      .click();
    await expect(
      assistant.getByText(
        "配置已保存，已选中“用量测试模型”。密钥不会回显；尚未检查服务连接。",
      ),
    ).toBeVisible();
    await expect(
      assistant.getByLabel("使用模型").locator("option:checked"),
    ).toHaveText("用量测试模型 · 本地");

    // 打开“本章模型用量”：查看不调用模型，尚无记录。
    const usage = assistant.locator("details.model-usage");
    await usage.getByText("本章模型用量", { exact: true }).click();
    await expect(usage.getByText("还没有发出过模型请求。")).toBeVisible();
    expect(requests).toHaveLength(0);

    // 续写：候选显示插入位置，正文与服务器正文都不变。
    await assistant
      .getByRole("button", { name: "准备续写", exact: true })
      .click();
    const task = assistant.getByRole("region", { name: "当前AI任务" });
    expect(requests).toHaveLength(0);
    await task
      .getByRole("button", { name: "确认发送并生成", exact: true })
      .click();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(continued);
    expect(requests).toHaveLength(1);
    expect(requests[0].path).toBe("/chat/completions");
    const insertion = task.getByRole("region", { name: "候选插入位置" });
    await expect(insertion.getByText("插入位置：正文末尾")).toBeVisible();
    const tail = insertion.getByRole("group", { name: "正文末尾与候选" });
    await expect(tail).toContainText(initial);
    await expect(tail.locator("ins")).toHaveText(continued);
    await expect(editor).toHaveValue(initial);
    expect(await serverContent()).not.toContain(continued.slice(0, 10));

    // 打开中的用量面板在生成结束后自动重读：服务商报告的 token。
    const items = usage.getByRole("list", { name: "模型请求记录" });
    await expect(items.getByRole("listitem")).toHaveCount(1);
    await expect(items.getByRole("listitem").first()).toContainText(
      "服务商报告：输入 321 · 输出 123 token",
    );
    await expect(items.getByRole("listitem").first()).toContainText(
      "正文生成 · e2e-ai-model（本机） · 已返回",
    );
    await expect(usage).toContainText("输入 321 · 输出 123（来自 1 次报告）");

    await task.getByRole("button", { name: "丢弃", exact: true }).click();
    await expect(page.getByLabel("AI候选文本")).toHaveCount(0);
    await expect(editor).toHaveValue(initial);

    // 改写：对照显示任务准备时保存的原选区与候选；未报告 usage 记为未知。
    const selected = "灯火摇曳，旅人";
    await editor.evaluate((element: HTMLTextAreaElement, length: number) => {
      element.focus();
      element.setSelectionRange(0, length);
      document.dispatchEvent(new Event("selectionchange"));
      element.dispatchEvent(
        new KeyboardEvent("keyup", { bubbles: true, key: "Shift" }),
      );
    }, selected.length);
    const rewrite = assistant.getByRole("button", { name: "准备改写选中文本" });
    await expect(rewrite).toBeEnabled();
    await rewrite.click();
    await expect(task.getByLabel("本次发送的改写选区")).toHaveValue(selected);
    expect(requests).toHaveLength(1);
    // Preparing a new task also refreshes the open ledger; verify it before sending.
    await expect(usage.getByRole("button", { name: "刷新用量" })).toBeVisible();
    await task
      .getByRole("button", { name: "确认发送并生成", exact: true })
      .click();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(rewritten);
    expect(requests).toHaveLength(2);
    const comparison = task.getByRole("region", { name: "原文与候选对照" });
    const originalPane = comparison.getByRole("group", {
      name: "原文（删除部分划线）",
    });
    const candidatePane = comparison.getByRole("group", {
      name: "候选（新增部分标记）",
    });
    await expect(originalPane).toHaveText(selected);
    await expect(candidatePane).toHaveText(rewritten);
    await expect(comparison.getByRole("note")).toContainText(
      "采用前正文不会改变",
    );
    const views = comparison.getByRole("group", { name: "对照视图" });
    await views.getByRole("button", { name: "只看原文" }).click();
    await expect(originalPane).toBeVisible();
    await expect(candidatePane).toHaveCount(0);
    await views.getByRole("button", { name: "只看候选" }).click();
    await expect(originalPane).toHaveCount(0);
    await expect(candidatePane).toHaveText(rewritten);
    await views.getByRole("button", { name: "对照" }).click();
    await expect(originalPane).toHaveText(selected);
    await expect(editor).toHaveValue(initial);

    await expect(items.getByRole("listitem")).toHaveCount(2);
    const unknownRow = items
      .getByRole("listitem")
      .filter({ hasText: "用量未知（服务商未报告）" });
    await expect(unknownRow).toHaveCount(1);
    await expect(unknownRow).not.toContainText("token");
    await expect(
      items
        .getByRole("listitem")
        .filter({ hasText: "服务商报告：输入 321 · 输出 123 token" }),
    ).toHaveCount(1);
    await expect(usage).toContainText("2 次（已返回 2）");
    await expect(usage).toContainText("输入 321 · 输出 123（来自 1 次报告）");
    await expect(usage).toContainText(
      "1 次（未计入上方 token 合计，不按 0 计）",
    );

    // 台账接口与界面一致：已报告与未知分开，未知不计入 token。
    const ledger = (await (
      await page.request.get(
        `/api/v1/projects/${project}/usage?chapter_id=${chapter}`,
      )
    ).json()) as {
      totals: {
        attempts: number;
        reported_attempts: number;
        unknown_attempts: number;
        reported_input_tokens: number;
        reported_output_tokens: number;
        reported_total_tokens: number;
      };
    };
    expect(ledger.totals).toMatchObject({
      attempts: 2,
      reported_attempts: 1,
      unknown_attempts: 1,
      reported_input_tokens: 321,
      reported_output_tokens: 123,
      reported_total_tokens: 444,
    });

    // 刷新后候选仍待确认，正文未被自动采用；查看用量不再调用模型。
    await page.reload();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(rewritten);
    await expect(editor).toHaveValue(initial);
    await expect(
      task
        .getByRole("region", { name: "原文与候选对照" })
        .getByRole("group", { name: "原文（删除部分划线）" }),
    ).toHaveText(selected);
    const stored = await serverContent();
    expect(stored).toContain(initial);
    expect(stored).not.toContain(rewritten.slice(0, 10));
    expect(stored).not.toContain(continued.slice(0, 10));
    await usage.getByText("本章模型用量", { exact: true }).click();
    await expect(items.getByRole("listitem")).toHaveCount(2);
    await usage.getByRole("button", { name: "刷新用量" }).click();
    await expect(items.getByRole("listitem")).toHaveCount(2);
    expect(requests).toHaveLength(2);
    expectCleanBrowserAudit(browserAudit);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
