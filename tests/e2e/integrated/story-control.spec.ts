import { createServer } from "node:http";
import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-INT-027 Whole-book plan, plot thread due to-do, story timeline and pinned recall frozen into a prepared task with zero model requests", async ({
  page,
  browserAudit,
}) => {
  // 受控“模型”只用来证明整个流程不发出任何模型请求。
  const requests: string[] = [];
  const server = createServer((request, response) => {
    requests.push(String(request.url));
    response.writeHead(500);
    response.end();
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
    const project = (
      (await (
        await post("/api/v1/projects", { title: "长篇故事控制" })
      ).json()) as { project_id: string }
    ).project_id;
    const volume = (
      (await (
        await post(`/api/v1/projects/${project}/volumes`, {
          title: "第一卷",
          summary: "",
          position: 1,
        })
      ).json()) as { volume_id: string }
    ).volume_id;
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
    const first = await chapter(
      "雨夜",
      1,
      "雨夜，船夫的左臂旧伤隐隐作痛。渡口下着冷雨。",
    );
    const second = await chapter("渡口", 2, "渡口烈日当空，主角走近码头。");
    const fact = async (title: string, text: string, quote: string) => {
      const source = (
        (await (
          await page.request.get(`/api/v1/chapters/${first}/memory`)
        ).json()) as { source_revision: string }
      ).source_revision;
      const created = (await (
        await post(`/api/v1/chapters/${first}/memory/facts`, {
          expected_version: 0,
          source_revision: source,
          title,
          text,
          quote,
        })
      ).json()) as { id: string };
      const confirmed = await page.request.put(
        `/api/v1/chapters/${first}/memory/facts/${created.id}`,
        {
          headers: await headers(),
          data: {
            expected_version: 1,
            source_revision: source,
            title,
            text,
            quote,
            status: "confirmed",
          },
        },
      );
      expect(confirmed.status()).toBe(200);
      return created.id;
    };
    const injury = await fact(
      "船夫旧伤",
      "船夫左臂有旧伤",
      "船夫的左臂旧伤隐隐作痛",
    );
    const weather = await fact("渡口天气", "渡口下着冷雨", "渡口下着冷雨");
    // 本机模型配置只用于冻结任务；准备任务不发送请求。
    const model = await post("/api/v1/ai/models", {
      name: "故事控制模型",
      kind: "local",
      base_url: "http://127.0.0.1:18123",
      model: "e2e-ai-model",
    });
    expect(model.status()).toBe(201);
    const profile = ((await model.json()) as { id: string }).id;

    // 小说结构：长篇规划默认折叠，展开后录入全书目标、伏笔与事件。
    // 尚未创建大纲，结构页读取大纲预期 404。
    browserAudit.allowExpectedConsoleHttpFailure(
      `/api/v1/projects/${project}/outline`,
      404,
    );
    await page.goto(`/projects/${project}/structure`);
    const section = page.locator("details.story-control-section");
    await section.getByText(/长篇规划与伏笔（/u).click();
    const panel = section.getByRole("region", { name: "长篇规划与伏笔" });
    await expect(panel.getByText(/还没有目标/u)).toBeVisible();
    await panel.getByRole("button", { name: "新建目标", exact: true }).click();
    const goalForm = panel.getByRole("form", { name: "新建目标" });
    await goalForm.getByLabel("目标名称").fill("夺回渡口");
    await goalForm.getByLabel("主要阻碍").fill("夜禁与守卫");
    await goalForm.getByLabel("添加章节").selectOption(second);
    await goalForm.getByLabel("本章说明").fill("主角第一次靠近渡口");
    await goalForm.getByRole("button", { name: "保存目标" }).click();
    await expect(panel.getByText("目标已保存。")).toBeVisible();
    await expect(panel.getByText(/全书：夺回渡口/u)).toBeVisible();

    await panel.getByRole("button", { name: "新建伏笔", exact: true }).click();
    const threadForm = panel.getByRole("form", { name: "新建伏笔" });
    await threadForm.getByLabel("伏笔名称").fill("船夫的旧伤");
    await threadForm.getByLabel("预计埋设章").selectOption(first);
    await threadForm.getByLabel("预计兑现章").selectOption(second);
    await threadForm.getByLabel(/^状态（/u).selectOption("planted");
    await threadForm.getByLabel("证据所在章").selectOption(first);
    await threadForm
      .getByLabel("已保存正文中的原句")
      .fill("船夫的左臂旧伤隐隐作痛");
    await threadForm.getByRole("button", { name: "添加证据" }).click();
    await threadForm.getByRole("button", { name: "保存伏笔" }).click();
    await expect(panel.getByText("伏笔已保存。")).toBeVisible();
    // 预计兑现章已有正文：出现到期待办，但不会自动改变伏笔状态。
    await expect(panel.getByText("需要处理的伏笔（1）")).toBeVisible();
    await expect(panel.getByText(/船夫的旧伤（已埋设/u)).toBeVisible();

    await panel.getByRole("button", { name: "新建事件", exact: true }).click();
    let eventForm = panel.getByRole("form", { name: "新建事件" });
    await eventForm.getByLabel("事件名称").fill("渡口失火");
    await eventForm.getByLabel("叙述所在章").selectOption(first);
    await eventForm.getByRole("button", { name: "保存事件" }).click();
    await expect(panel.getByText("事件已保存。")).toBeVisible();
    await panel.getByRole("button", { name: "新建事件", exact: true }).click();
    eventForm = panel.getByRole("form", { name: "新建事件" });
    await eventForm.getByLabel("事件名称").fill("十年前的大火");
    await eventForm.getByLabel("故事时间（可留空，如“十年前”）").fill("十年前");
    await eventForm.getByLabel("叙述所在章").selectOption(second);
    await eventForm
      .getByRole("group", { name: "发生在这些事件之前" })
      .getByLabel("渡口失火")
      .check();
    await eventForm.getByRole("button", { name: "保存事件" }).click();
    await expect(panel.getByText("事件已保存。")).toBeVisible();
    // 倒叙：第二章叙述的事件在故事时间上排第一。
    const events = panel.locator("ol.story-control__list > li");
    await expect(events.nth(0)).toContainText("十年前的大火（十年前）");
    await expect(events.nth(0)).toContainText("叙述位置：第1卷第2章");
    await expect(events.nth(1)).toContainText("渡口失火");

    // 写作台：本章任务与本次依据；固定一条事实、排除一条。
    await page.goto(`/projects/${project}/chapters/${second}/write`);
    const assistant = page.getByRole("region", { name: "AI写作助手" });
    await assistant.getByRole("tab", { name: "准备" }).click();
    const desk = assistant.locator("details.story-control-desk");
    await desk.getByText(/本章任务与本次依据/u).click();
    await expect(
      desk.getByText(/全书：夺回渡口（计划） · 主角第一次靠近渡口/u),
    ).toBeVisible();
    await expect(desk.getByText("计划在本章或本卷兑现")).toBeVisible();
    const recall = desk.getByRole("region", {
      name: "本次依据（前文事实召回）",
    });
    await expect(recall).toContainText("已选 2 / 24 项（作者固定 0 项）");
    await recall.getByText("调整依据", { exact: true }).click();
    await recall.getByRole("button", { name: "检索事实" }).click();
    await expect(recall.getByText("找到 2 条已确认事实。")).toBeVisible();
    await recall.getByRole("button", { name: "固定「船夫旧伤」" }).click();
    await recall.getByRole("button", { name: "排除「渡口天气」" }).click();
    await expect(recall).toContainText("已选 1 / 24 项（作者固定 1 项）");
    await recall.getByRole("button", { name: "保存为本章召回设置" }).click();
    await expect(
      recall.getByText(/已保存为本章召回设置第 1 版/u),
    ).toBeVisible();

    // 准备任务：冻结固定事实与计划（标为计划），排除项不进入；不发送模型请求。
    const run = await post(`/api/v1/chapters/${second}/ai/runs`, {
      profile_id: profile,
    });
    expect(run.status()).toBe(201);
    const sources = (
      (await run.json()) as {
        context: {
          manifest: {
            sources: {
              source: string;
              references: string[][];
              text: string;
              reason: string;
            }[];
          };
        };
      }
    ).context.manifest.sources;
    const memory = sources.find((item) => item.source === "story_memory");
    expect(memory?.references.map((item) => item[0])).toEqual([injury]);
    expect(memory?.reason).toContain("本章召回设置第 1 版");
    expect(JSON.stringify(sources)).not.toContain(weather);
    const guide = sources.find((item) => item.source === "story_guide");
    expect(guide?.reason).toContain("不是已发生的正文事实");
    expect(guide?.text).toContain("全书目标: 夺回渡口");

    // 修改前文：固定事实来源过期，准备被拒绝而不是悄悄丢掉固定项。
    const current = await page.request.get(`/api/v1/chapters/${first}/content`);
    const edited = await page.request.put(`/api/v1/chapters/${first}/content`, {
      headers: { ...(await headers()), "If-Match": current.headers().etag },
      data: { content: "雨夜，船夫沉默。渡口下着冷雨。" },
    });
    expect(edited.status()).toBe(200);
    const refused = await post(`/api/v1/chapters/${second}/ai/runs`, {
      profile_id: profile,
    });
    expect(refused.status()).toBe(409);
    expect(JSON.stringify(await refused.json())).toContain(
      "AI_RECALL_PINS_INVALID",
    );
    await page.reload();
    await assistant.getByRole("tab", { name: "准备" }).click();
    await desk.getByText(/本章任务与本次依据/u).click();
    await expect(recall.getByRole("alert")).toContainText(
      "船夫旧伤：固定项来源正文已修改，需重新确认",
    );
    // 证据所在正文改变：结构页的伏笔显示“证据待复核”。
    // 尚未创建大纲，结构页读取大纲预期 404。
    browserAudit.allowExpectedConsoleHttpFailure(
      `/api/v1/projects/${project}/outline`,
      404,
    );
    await page.goto(`/projects/${project}/structure`);
    await section.getByText(/长篇规划与伏笔（/u).click();
    await expect(panel.getByText(/证据待复核/u).first()).toBeVisible();
    expect(requests).toHaveLength(0);
    expectCleanBrowserAudit(browserAudit);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
