import { createServer } from "node:http";
import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-INT-026 Candidate edit adopted as the author's version; strict budget refuses before any model request, warn mode needs confirmation", async ({
  page,
  browserAudit,
}) => {
  const requests: { path: string | undefined; body: string }[] = [];
  const first = "门外的风声停了，旅人侧耳听见远处的马蹄。".repeat(10);
  const second = "灯火忽明忽暗，旅人抖落斗篷上的雨水。".repeat(12);
  const edited = "山道上传来铃声，旅人提灯走进夜色。".repeat(12);
  const server = createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk: string) => {
      body += chunk;
    });
    request.on("end", () => {
      requests.push({ path: request.url, body });
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          choices: [
            { message: { content: requests.length === 1 ? first : second } },
          ],
          usage: {
            prompt_tokens: 300,
            completion_tokens: 120,
            total_tokens: 420,
          },
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
    const origin = new URL(page.url()).origin;
    const session = (await (
      await page.request.get("/api/v1/security/session")
    ).json()) as { csrf_token: string };
    const headers = { "X-CSRF-Token": session.csrf_token, Origin: origin };
    // 页面刷新后会话令牌可能轮换：直接调用接口前重新读取。
    const freshHeaders = async () => ({
      "X-CSRF-Token": (
        (await (await page.request.get("/api/v1/security/session")).json()) as {
          csrf_token: string;
        }
      ).csrf_token,
      Origin: origin,
    });
    const projectResponse = await page.request.post("/api/v1/projects", {
      headers,
      data: { title: "候选修改与预算" },
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
      { headers, data: { title: "山道", summary: "", position: 1 } },
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
    const ledgerAttempts = async () =>
      (
        (await (
          await page.request.get(
            `/api/v1/projects/${project}/usage?chapter_id=${chapter}`,
          )
        ).json()) as { totals: { attempts: number } }
      ).totals.attempts;

    await page.goto(`/projects/${project}/chapters/${chapter}/write`);
    const editor = page.getByLabel("章节正文");
    await expect(editor).toHaveValue(initial);
    const assistant = page.getByRole("region", { name: "AI写作助手" });

    // 本机模型（无需密钥存储），指向受控假模型服务。
    const summary = assistant.getByRole("region", { name: "当前模型" });
    // AI 环境已提供默认本地模型：等模型列表读完再添加，避免与首屏加载竞争。
    await summary.getByRole("button", { name: "管理模型" }).click();
    await assistant.getByRole("button", { name: "添加新模型" }).click();
    await assistant
      .getByLabel("配置名称", { exact: true })
      .fill("预算测试模型");
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
      assistant.getByLabel("使用模型").locator("option:checked"),
    ).toHaveText("预算测试模型 · 本地");

    // 作者填写价格（不预置）；预算暂不启用。读取与保存都不调用模型。
    const budgetPanel = assistant.locator("details.budget-settings");
    await budgetPanel.getByText("费用与预算", { exact: true }).click();
    const priceForm = budgetPanel.getByRole("form", { name: "模型价格" });
    await expect(priceForm).toContainText("价格未填写");
    await priceForm.getByLabel("币种（如 CNY、USD）").fill("CNY");
    await priceForm.getByLabel("输入价格（每百万 token）").fill("1000");
    await priceForm.getByLabel("输出价格（每百万 token）").fill("1000");
    await priceForm
      .getByRole("button", { name: "保存价格", exact: true })
      .click();
    await expect(
      priceForm.getByText("价格已保存为新版本；之前的请求仍按当时的价格计算。"),
    ).toBeVisible();
    await expect(priceForm).toContainText(
      "当前价格：每百万 token 输入 1000.00 / 输出 1000.00 CNY（第 1 版）",
    );
    const budgetForm = budgetPanel.getByRole("form", { name: "本书预算" });
    await expect(budgetForm.getByLabel("预算方式")).toHaveValue("off");
    expect(requests).toHaveLength(0);

    // 续写一段：预算关闭时可直接发送，发送前可见保守上限。
    await assistant
      .getByRole("button", { name: "准备续写", exact: true })
      .click();
    const task = assistant.getByRole("region", { name: "当前AI任务" });
    const estimate = task.getByRole("region", { name: "发送前预估" });
    await expect(estimate).toContainText("发送前预估（保守上限，不是账单）");
    await expect(estimate).toContainText("本书未设预算。");
    expect(requests).toHaveLength(0);
    await task
      .getByRole("button", { name: "确认发送并生成", exact: true })
      .click();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(first);
    expect(requests).toHaveLength(1);

    // 编辑候选：保存为新版本，不写正文，不改原始候选。
    const candidateEditor = task.getByRole("region", { name: "编辑候选" });
    await candidateEditor
      .getByRole("button", { name: "编辑候选", exact: true })
      .click();
    await candidateEditor.getByLabel("编辑候选文本").fill(edited);
    await expect(
      task.getByRole("button", { name: "追加到正文", exact: true }),
    ).toBeDisabled();
    await candidateEditor
      .getByRole("button", { name: "保存修改", exact: true })
      .click();
    await expect(
      candidateEditor.getByText("修改已保存为新版本，尚未写入正文。"),
    ).toBeVisible();
    await expect(candidateEditor).toContainText("已保存作者修改第 1 版");
    await expect(page.getByLabel("AI候选文本")).toHaveValue(first);
    await expect(editor).toHaveValue(initial);
    expect(await serverContent()).not.toContain(edited.slice(0, 8));
    expect(requests).toHaveLength(1);

    // 采用修改后的文本：正文追加作者版本，原始候选仍保留可查。
    await task
      .getByRole("button", { name: "追加修改后的文本", exact: true })
      .click();
    await expect.poll(async () => editor.inputValue()).toContain(edited);
    await expect.poll(serverContent).toContain(edited.slice(0, 8));
    const stored = await serverContent();
    expect(stored).toContain(initial);
    expect(stored).not.toContain(first.slice(0, 7));
    const processed = task.locator("details").filter({
      has: page.getByText("查看已处理候选", { exact: true }),
    });
    await processed.getByText("查看已处理候选", { exact: true }).click();
    await expect(processed).toContainText("已采纳（采用作者修改版本）");
    await expect(processed.locator("pre")).toHaveText(first);
    expect(requests).toHaveLength(1);
    expect(await ledgerAttempts()).toBe(1);

    // 严格预算：单任务上限低于保守预估，界面禁止发送，服务端同样拒绝且不调用模型。
    await budgetForm.getByLabel("预算方式").selectOption("strict");
    await budgetForm.getByLabel("预算币种").fill("CNY");
    await budgetForm.getByLabel("单任务上限（可空）").fill("0.01");
    await budgetForm
      .getByRole("button", { name: "保存预算", exact: true })
      .click();
    await expect(budgetForm.getByText("预算已保存为新版本。")).toBeVisible();
    await page.reload();
    await expect.poll(async () => editor.inputValue()).toContain(edited);
    const strictEstimate = task.getByRole("region", { name: "发送前预估" });
    await expect(strictEstimate).toContainText("严格模式");
    await expect(strictEstimate).toContainText("本次最多约");
    await expect(strictEstimate.getByRole("alert")).toContainText(
      "按严格预算不会发送：加上本次保守预估会超过单任务预算",
    );
    await expect(
      task.getByRole("button", { name: "确认发送并生成", exact: true }),
    ).toBeDisabled();
    const runs = (await (
      await page.request.get(`/api/v1/chapters/${chapter}/ai/runs`)
    ).json()) as { run_id: string; status: string }[];
    const ready = runs.filter((item) => item.status === "ready");
    expect(ready).toHaveLength(1);
    const refused = await page.request.post(
      `/api/v1/chapters/${chapter}/ai/runs/${ready[0].run_id}/generate`,
      { headers: await freshHeaders(), data: {} },
    );
    expect(refused.status()).toBe(409);
    expect(JSON.stringify(await refused.json())).toContain("AI_BUDGET_REFUSED");
    expect(requests).toHaveLength(1);
    expect(await ledgerAttempts()).toBe(1);

    // 提示模式：超出时需作者勾选确认后才能发送这一次。
    await page.reload();
    await budgetPanel.getByText("费用与预算", { exact: true }).click();
    await budgetForm.getByLabel("预算方式").selectOption("warn");
    await budgetForm
      .getByRole("button", { name: "保存预算", exact: true })
      .click();
    await expect(budgetForm.getByText("预算已保存为新版本。")).toBeVisible();
    await page.reload();
    const warnEstimate = task.getByRole("region", { name: "发送前预估" });
    await expect(warnEstimate).toContainText("提示模式");
    await expect(warnEstimate.getByRole("alert")).toContainText(
      "预算提示：加上本次保守预估会超过单任务预算",
    );
    const send = task.getByRole("button", {
      name: "确认发送并生成",
      exact: true,
    });
    await expect(send).toBeDisabled();
    expect(requests).toHaveLength(1);
    await warnEstimate
      .getByLabel("我已知晓可能超出预算，仍要发送这一次")
      .check();
    await expect(send).toBeEnabled();
    await send.click();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(second);
    expect(requests).toHaveLength(2);
    expect(await ledgerAttempts()).toBe(2);
    expectCleanBrowserAudit(browserAudit);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
