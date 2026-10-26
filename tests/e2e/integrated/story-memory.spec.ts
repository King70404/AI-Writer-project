import { createServer } from "node:http";
import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test("E2E-INT-021 story memory review and guarded rewrite", async ({
  page,
  browserAudit,
}) => {
  const requests: string[] = [];
  const replacement =
    "他抬起受伤的手腕，疼痛使动作慢了半拍，便换另一只手挪开木箱。".repeat(8);
  const server = createServer((request, response) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk: string) => {
      body += chunk;
    });
    request.on("end", () => {
      requests.push(body);
      const payload = JSON.parse(body) as { messages: { content: string }[] };
      let content = replacement;
      if (payload.messages[0].content.includes("一致性编辑")) {
        const input = JSON.parse(payload.messages[1].content) as {
          confirmed_facts: { id: string; text: string }[];
        };
        const prior = input.confirmed_facts[0];
        content = JSON.stringify({
          summary: prior ? "需要交代伤势影响" : "提取已发生的伤势",
          facts: prior
            ? []
            : [
                {
                  title: "手腕伤势",
                  text: "他左手腕受伤，抬手会痛",
                  quote: "他左手腕受伤，抬手便痛。",
                },
              ],
          findings: prior
            ? [
                {
                  quote: "他左手轻松举起重箱。",
                  explanation: "前文伤势尚未交代恢复",
                  instruction: "保留伤势，改用另一只手搬箱并写出疼痛影响",
                  fact_ids: [prior.id],
                },
              ]
            : [],
        });
      }
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ choices: [{ message: { content } }] }));
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
    const headers = {
      "X-CSRF-Token": session.csrf_token,
      Origin: origin,
    };
    const projectResponse = await page.request.post("/api/v1/projects", {
      headers,
      data: { title: "隔离长篇记忆流程" },
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
    const chapters: string[] = [];
    for (const [index, text] of [
      "他左手腕受伤，抬手便痛。",
      "他左手轻松举起重箱。",
    ].entries()) {
      const response = await page.request.post(
        `/api/v1/projects/${project}/volumes/${volume}/chapters`,
        {
          headers,
          data: {
            title: `记忆章节${index + 1}`,
            summary: "",
            position: index + 1,
          },
        },
      );
      expect(response.status()).toBe(201);
      const chapter = ((await response.json()) as { chapter_id: string })
        .chapter_id;
      const saved = await page.request.put(
        `/api/v1/chapters/${chapter}/content`,
        {
          headers: { ...headers, "If-Match": response.headers().etag },
          data: { content: text },
        },
      );
      expect(saved.status()).toBe(200);
      chapters.push(chapter);
    }
    const path = (chapter: string) =>
      `/projects/${project}/chapters/${chapter}/write`;
    await page.goto(path(chapters[0]));
    await page.getByRole("tab", { name: "评审", exact: true }).click();
    const memory = page.getByRole("region", { name: "长篇记忆与评审工作台" });
    await memory.getByRole("button", { name: "准备本章评审" }).click();
    await expect(memory.getByText(/评审已准备/u)).toBeVisible();
    expect(requests).toHaveLength(0);
    await memory.getByText("查看评审实际发送内容").click();
    await expect(memory.getByLabel("评审发送正文")).toHaveValue(
      "他左手腕受伤，抬手便痛。",
    );
    await memory.getByRole("button", { name: "确认发送并评审" }).click();
    await expect(memory.getByText("提取已发生的伤势")).toBeVisible();
    expect(requests).toHaveLength(1);
    await memory.getByRole("button", { name: "编辑这条候选事实" }).click();
    await memory.getByRole("button", { name: "保存为待确认事实" }).click();
    await expect(memory.getByText("事实状态已保存。")).toBeVisible();
    await memory.getByRole("button", { name: "确认此事实" }).click();
    await expect(
      memory.getByText("事实已由你确认，可供后文章节召回。"),
    ).toBeVisible();
    await expect(
      memory.getByText("正在处理记忆或评审，请勿重复发送…", { exact: true }),
    ).not.toBeVisible();
    await page.goto(path(chapters[1]));
    await page.getByRole("tab", { name: "评审", exact: true }).click();
    await memory.getByText("查看本章可召回的前文事实（1）").click();
    await expect(
      memory.getByText("手腕伤势：他左手腕受伤，抬手会痛", { exact: false }),
    ).toBeVisible();
    await memory.getByRole("button", { name: "准备本章评审" }).click();
    await expect(memory.getByText(/评审已准备/u)).toBeVisible();
    expect(requests).toHaveLength(1);
    await memory.getByRole("button", { name: "确认发送并评审" }).click();
    await expect(memory.getByText("前文伤势尚未交代恢复")).toBeVisible();
    expect(requests).toHaveLength(2);
    const reviewPayload = JSON.parse(requests[1]) as {
      messages: { content: string }[];
    };
    const reviewInput = JSON.parse(reviewPayload.messages[1].content) as {
      confirmed_facts: { text: string }[];
    };
    expect(reviewInput.confirmed_facts[0].text).toBe("他左手腕受伤，抬手会痛");
    await page.reload();
    await page.getByRole("tab", { name: "评审", exact: true }).click();
    await memory.getByRole("button", { name: "按此建议准备改写" }).click();
    const task = page.getByRole("region", { name: "当前AI任务" });
    await expect(
      task.getByText("可以生成下一段", { exact: false }),
    ).toBeVisible();
    expect(requests).toHaveLength(2);
    await task.getByRole("button", { name: "确认发送并生成" }).click();
    await expect(page.getByLabel("AI候选文本")).toHaveValue(replacement);
    expect(requests).toHaveLength(3);
    await expect(page.getByLabel("章节正文")).toHaveValue(
      "他左手轻松举起重箱。",
    );
    await page
      .getByRole("button", { name: "替换选中文本", exact: true })
      .click();
    await expect(page.getByLabel("章节正文")).toHaveValue(replacement);
    await expect(page.getByRole("status", { name: "保存状态" })).toHaveText(
      "已保存",
    );
    await page.getByRole("tab", { name: "评审", exact: true }).click();
    await memory.getByRole("button", { name: "刷新记忆与评审" }).click();
    await expect(
      memory.getByText(
        "正文或依据事实已变化，此评审仅供追溯。请重新准备评审。",
      ),
    ).toBeVisible();
    await expect(
      memory.getByText("正在处理记忆或评审，请勿重复发送…", { exact: true }),
    ).not.toBeVisible();
    await page.goto(path(chapters[0]));
    await page.getByLabel("章节正文").fill("他左手腕的伤已经痊愈。");
    await expect(page.getByRole("status", { name: "保存状态" })).toHaveText(
      "已保存",
    );
    await page.goto(path(chapters[1]));
    await page.getByRole("tab", { name: "评审", exact: true }).click();
    await expect(
      memory.getByText("查看本章可召回的前文事实（0）"),
    ).toBeVisible();
    await expect(memory.getByRole("link", { name: "记忆章节1" })).toBeVisible();
    expect(requests).toHaveLength(3);
    expectCleanBrowserAudit(browserAudit);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
