import { createServer } from "node:http";
import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

type ChatBody = { messages: { role: string; content: string }[] };
type EmbeddingBody = { model: string; input: string[] };

test("E2E-INT-031 Plan split proposal adopted, foreshadow card adopted then undone, whole-chapter draft edited/discarded/adopted and semantic index built, all against a controlled model", async ({
  page,
  browserAudit,
}) => {
  // 受控 OpenAI 兼容服务：按系统提示区分规划建议、伏笔提取与章节候选稿，/embeddings 返回确定向量。
  const chatKinds: string[] = [];
  const embeddingInputs: number[] = [];
  const segments = [
    "码头的灯笼在风里摇晃，主角压低斗笠混进搬货的人群。".repeat(9),
    "远处传来巡夜守卫的梆子声，人群一阵骚动又很快平息。".repeat(9),
    "船夫收起渔网，抬眼望向主角，左臂旧伤让他动作一顿。".repeat(9),
  ];
  const editedSegment = "主角在码头尽头停下，望见船夫独自修补渔网。".repeat(6);
  let firstChapter = "";
  const server = createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk: string) => {
      body += chunk;
    });
    request.on("end", () => {
      response.writeHead(200, { "Content-Type": "application/json" });
      if (String(request.url).endsWith("/embeddings")) {
        const input = (JSON.parse(body) as EmbeddingBody).input;
        embeddingInputs.push(input.length);
        response.end(
          JSON.stringify({
            data: input.map((text, index) => ({
              index,
              embedding: [1, (text.length % 7) + 1, index + 1, 0.5],
            })),
          }),
        );
        return;
      }
      const system = (JSON.parse(body) as ChatBody).messages[0].content;
      let content: string;
      if (system.includes("长篇小说规划助手")) {
        chatKinds.push("plan");
        content = JSON.stringify({
          summary: "先潜入再夺取",
          cards: [
            {
              kind: "child_goal",
              title: "潜入码头",
              volume_id: null,
              conflict: "守卫盘查",
              obstacle: "",
              turn: "",
              outcome: "摸清渡口布防",
              chapter_ids: [],
              reason: "夺回前需要情报",
            },
          ],
        });
      } else if (system.includes("伏笔整理助手")) {
        chatKinds.push("foreshadow");
        content = JSON.stringify({
          summary: "发现一条新伏笔",
          cards: [
            {
              kind: "new_thread",
              title: "船夫的旧伤",
              content: "船夫左臂旧伤的来历",
              chapter_id: firstChapter,
              quote: "船夫的左臂旧伤隐隐作痛",
              reason: "旧伤被特意点出",
            },
          ],
        });
      } else if (system.includes("章节候选稿")) {
        content = segments[chatKinds.filter((kind) => kind === "draft").length];
        chatKinds.push("draft");
      } else {
        chatKinds.push("unexpected");
        content = "";
      }
      response.end(
        JSON.stringify({
          choices: [{ message: { content } }],
          usage: {
            prompt_tokens: 200,
            completion_tokens: 100,
            total_tokens: 300,
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
    const headers = async () => ({
      "X-CSRF-Token": (
        (await (await page.request.get("/api/v1/security/session")).json()) as {
          csrf_token: string;
        }
      ).csrf_token,
      Origin: origin,
    });
    const post = async (path: string, data: unknown) =>
      page.request.post(path, { headers: await headers(), data });
    const projectResponse = await post("/api/v1/projects", {
      title: "核心AI流程",
    });
    expect(projectResponse.status()).toBe(201);
    const project = ((await projectResponse.json()) as { project_id: string })
      .project_id;
    const volumeResponse = await post(`/api/v1/projects/${project}/volumes`, {
      title: "第一卷",
      summary: "",
      position: 1,
    });
    expect(volumeResponse.status()).toBe(201);
    const volume = ((await volumeResponse.json()) as { volume_id: string })
      .volume_id;
    const chapter = async (title: string, position: number, text: string) => {
      const created = await post(
        `/api/v1/projects/${project}/volumes/${volume}/chapters`,
        { title, summary: "", position },
      );
      expect(created.status()).toBe(201);
      const id = ((await created.json()) as { chapter_id: string }).chapter_id;
      const saved = await page.request.put(`/api/v1/chapters/${id}/content`, {
        headers: { ...(await headers()), "If-Match": created.headers().etag },
        data: { content: text },
      });
      expect(saved.status()).toBe(200);
      return id;
    };
    firstChapter = await chapter(
      "雨夜",
      1,
      "雨夜，船夫的左臂旧伤隐隐作痛。渡口下着冷雨。",
    );
    const initial = "渡口烈日当空，主角走近码头。";
    const second = await chapter("渡口", 2, initial);

    // C-1：结构页新建全书目标 → 准备（不调用模型）→ 发送一次 → 采用建议卡写回规划。
    // 尚未创建大纲，结构页读取大纲预期 404。
    browserAudit.allowExpectedConsoleHttpFailure(
      `/api/v1/projects/${project}/outline`,
      404,
    );
    await page.goto(`/projects/${project}/structure`);
    const section = page.locator("details.story-control-section");
    await section.getByText(/长篇规划与伏笔（/u).click();
    const panel = section.getByRole("region", { name: "长篇规划与伏笔" });
    await panel.getByRole("button", { name: "新建目标", exact: true }).click();
    const goalForm = panel.getByRole("form", { name: "新建目标" });
    await goalForm.getByLabel("目标名称").fill("夺回渡口");
    await goalForm.getByLabel("主要阻碍").fill("夜禁与守卫");
    await goalForm.getByRole("button", { name: "保存目标" }).click();
    await expect(panel.getByText("目标已保存。")).toBeVisible();
    await panel
      .getByRole("button", { name: "建议拆分「夺回渡口」", exact: true })
      .click();
    const split = panel.getByRole("region", { name: "「夺回渡口」的建议拆分" });
    await split
      .getByRole("button", { name: "准备建议（冻结快照，不调用模型）" })
      .click();
    await expect(split.getByText(/已冻结：目标「夺回渡口」/u)).toBeVisible();
    expect(chatKinds).toEqual([]);
    const sendPlan = split.getByRole("button", {
      name: "发送一次，生成建议卡",
    });
    await expect(sendPlan).toBeEnabled();
    await sendPlan.click();
    await expect(split.getByText(/新子目标「潜入码头」/u)).toBeVisible();
    expect(chatKinds).toEqual(["plan"]);
    await split.getByRole("checkbox", { name: "选择建议卡 1" }).check();
    await split.getByRole("button", { name: "采用所选（1）" }).click();
    await expect(
      panel.getByText("已采用所选建议卡，规划已更新。"),
    ).toBeVisible();
    await expect(split.getByText(/· 已采用/u)).toBeVisible();
    const arcPlan = (await (
      await page.request.get(`/api/v1/projects/${project}/arc-plans`)
    ).json()) as {
      goals: {
        goal: { id: string; title: string; parent_goal_ids: string[] };
      }[];
    };
    const source = arcPlan.goals.find((view) => view.goal.title === "夺回渡口");
    const child = arcPlan.goals.find((view) => view.goal.title === "潜入码头");
    expect(child?.goal.parent_goal_ids).toEqual([source?.goal.id]);
    await split.getByRole("button", { name: "关闭建议拆分" }).click();

    // C-2：批量提取伏笔 → 采用一张卡（新建伏笔）→ 撤销采用（伏笔被移除）。
    const threadTitles = async () =>
      (
        (await (
          await page.request.get(`/api/v1/projects/${project}/timeline`)
        ).json()) as { threads: { thread: { title: string } }[] }
      ).threads.map((view) => view.thread.title);
    await panel
      .getByRole("button", { name: "批量提取伏笔建议", exact: true })
      .click();
    const extract = panel.getByRole("region", { name: "批量提取伏笔建议" });
    await extract
      .getByRole("checkbox", { name: /第1卷第1章「雨夜」/u })
      .check();
    await extract
      .getByRole("button", { name: "预览所选范围（不调用模型）" })
      .click();
    await extract
      .getByRole("button", { name: "准备提取（冻结正文，不调用模型）" })
      .click();
    await expect(extract.getByText(/已冻结 1 章正文/u)).toBeVisible();
    expect(chatKinds).toEqual(["plan"]);
    const sendExtract = extract.getByRole("button", {
      name: "发送一次，生成伏笔建议卡",
    });
    await expect(sendExtract).toBeEnabled();
    await sendExtract.click();
    await expect(extract.getByText(/新伏笔「船夫的旧伤」/u)).toBeVisible();
    expect(chatKinds).toEqual(["plan", "foreshadow"]);
    expect(await threadTitles()).toEqual([]);
    await extract.getByRole("checkbox", { name: "选择伏笔建议卡 1" }).check();
    await extract.getByRole("button", { name: "采用所选（1）" }).click();
    await expect(
      panel.getByText("已采用所选伏笔建议卡，伏笔已更新。"),
    ).toBeVisible();
    await expect.poll(threadTitles).toEqual(["船夫的旧伤"]);
    await extract.getByRole("button", { name: "撤销采用伏笔建议卡 1" }).click();
    await expect(
      panel.getByText("已撤销该伏笔建议卡的采用，伏笔已回滚。"),
    ).toBeVisible();
    await expect.poll(threadTitles).toEqual([]);
    await expect(
      extract.getByRole("checkbox", { name: "选择伏笔建议卡 1" }),
    ).toBeEnabled();
    expect(chatKinds).toEqual(["plan", "foreshadow"]);

    // D3-C：写作台整章候选稿 → 三段生成 → 编辑第 1 段、丢弃第 2 段 → 采用其余。
    await page.goto(`/projects/${project}/chapters/${second}/write`);
    const editor = page.getByLabel("章节正文");
    await expect(editor).toHaveValue(initial);
    const assistant = page.getByRole("region", { name: "AI写作助手" });
    await expect(
      assistant.getByLabel("使用模型").locator("option:checked"),
    ).toHaveText("默认本地模型 · 本地");
    await assistant.getByText("章节候选稿（整章多段，可选）").click();
    const draft = assistant.getByRole("region", { name: "章节候选稿" });
    await draft.getByLabel("最多请求次数").fill("3");
    await draft
      .getByRole("button", { name: "准备候选稿", exact: true })
      .click();
    await expect(draft.getByText(/已请求 0\/3 次/u)).toBeVisible();
    expect(chatKinds).toEqual(["plan", "foreshadow"]);
    await draft.getByLabel("本次生成段数").fill("3");
    const sendDraft = draft.getByRole("button", {
      name: "确认发送",
      exact: true,
    });
    await expect(sendDraft).toBeEnabled();
    await sendDraft.click();
    await expect(draft.getByText(/已请求 3\/3 次/u)).toBeVisible();
    expect(chatKinds).toEqual([
      "plan",
      "foreshadow",
      "draft",
      "draft",
      "draft",
    ]);
    const comparison = draft.getByLabel("整章候选稿对照");
    for (const text of segments)
      await expect(
        comparison.locator("ins").filter({ hasText: text }),
      ).toHaveCount(1);
    await expect(editor).toHaveValue(initial);

    await draft
      .getByRole("button", { name: "编辑第 1 段", exact: true })
      .click();
    await draft
      .getByRole("textbox", { name: "编辑第 1 段" })
      .fill(editedSegment);
    await draft.getByRole("button", { name: "保存第 1 段修改" }).click();
    await expect(
      draft.getByText(/第 1 段的修改已保存（正文未改变/u),
    ).toBeVisible();
    await draft
      .getByRole("button", { name: "丢弃第 2 段", exact: true })
      .click();
    await expect(
      draft.getByText(/第 2 段已丢弃：不会再发送给模型/u),
    ).toBeVisible();
    await expect(editor).toHaveValue(initial);
    await draft
      .getByRole("button", { name: "采用全部未采用段落", exact: true })
      .click();
    await expect(draft.getByText("已采用，正文已更新。")).toBeVisible();
    await expect.poll(async () => editor.inputValue()).toContain(editedSegment);
    const serverText = (
      (await (
        await page.request.get(`/api/v1/chapters/${second}/content`)
      ).json()) as { content: string }
    ).content;
    expect(serverText.startsWith(initial)).toBe(true);
    expect(serverText).toContain(editedSegment);
    expect(serverText).toContain(segments[2]);
    expect(serverText).not.toContain(segments[0]);
    expect(serverText).not.toContain(segments[1]);
    expect(chatKinds).toHaveLength(5);

    // C-4：模型配置添加用途为“嵌入”的本机模型 → 语义索引选用 → 预估 → 确认建立 → 已是最新。
    const summary = assistant.getByRole("region", { name: "当前模型" });
    await summary.getByRole("button", { name: "管理模型" }).click();
    await assistant.getByRole("button", { name: "添加新模型" }).click();
    await assistant.getByLabel("配置名称", { exact: true }).fill("语义嵌入");
    await assistant
      .getByLabel("用途", { exact: true })
      .selectOption("embedding");
    await assistant
      .getByLabel("服务地址", { exact: true })
      .fill("http://127.0.0.1:18123");
    await assistant.getByLabel("模型名称", { exact: true }).fill("e2e-embed");
    await assistant
      .getByRole("button", { name: "保存模型配置", exact: true })
      .click();
    await expect(
      assistant.getByText(/嵌入模型“语义嵌入”已保存。/u),
    ).toBeVisible();
    await expect(
      assistant.getByLabel("使用模型").locator("option:checked"),
    ).toHaveText("默认本地模型 · 本地");
    await assistant.getByRole("tab", { name: "评审", exact: true }).click();
    const memory = page.getByRole("region", { name: "长篇记忆与评审工作台" });
    await memory.getByText("语义索引（可选，建立索引会计费）").click();
    const semantic = memory.getByRole("region", { name: "语义索引" });
    await semantic
      .getByLabel("嵌入模型")
      .selectOption({ label: "语义嵌入 · e2e-embed · 本地" });
    await semantic
      .getByRole("checkbox", { name: /召回时使用语义召回/u })
      .check();
    await semantic.getByRole("button", { name: "保存语义索引设置" }).click();
    await expect(
      semantic.getByText("语义索引设置已保存。保存设置不会调用模型。"),
    ).toBeVisible();
    const estimate = semantic.getByLabel("索引更新预估");
    await expect(estimate).toContainText(
      /本次待更新：事实 0 项、正文分块 \d+/u,
    );
    await expect(semantic).toContainText("章节正文 0 / 2");
    expect(embeddingInputs).toEqual([]);
    await estimate
      .getByRole("checkbox", { name: "我已核对以上预估，确认发送并计费" })
      .check();
    await estimate.getByRole("button", { name: "确认并建立/更新索引" }).click();
    await expect(semantic.getByText(/已发送 \d+ 个嵌入请求/u)).toBeVisible();
    await expect(semantic.getByText("语义索引已是最新。")).toBeVisible();
    await expect(semantic).toContainText("章节正文 2 / 2");
    expect(embeddingInputs.length).toBeGreaterThan(0);
    expect(chatKinds).toHaveLength(5);
    expectCleanBrowserAudit(browserAudit);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
