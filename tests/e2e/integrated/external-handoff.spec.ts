import { readFile } from "node:fs/promises";
import { inflateRawSync } from "node:zlib";
import { expectCleanBrowserAudit } from "../support/assertions";
import { expect, test } from "../support/fixture";

test.use({ acceptDownloads: true });

test("E2E-INT-029 External handoff selects sources, exports, imports and adopts only after confirmation", async ({
  page,
  browserAudit,
}) => {
  browserAudit.allowOneExpectedSessionCookie();
  const calls: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      /\/(generate|analyze|review|chat\/completions)(?:\/|$)/u.test(
        url.pathname,
      )
    )
      calls.push(url.pathname);
  });
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
  const post = async (url: string, data: unknown) =>
    page.request.post(url, { headers: await headers(), data });
  const projectResponse = await post("/api/v1/projects", { title: "交接测试" });
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
  const chapterResponse = await post(
    `/api/v1/projects/${project}/volumes/${volume}/chapters`,
    { title: "渡口", summary: "", position: 1 },
  );
  expect(chapterResponse.status()).toBe(201);
  const chapter = ((await chapterResponse.json()) as { chapter_id: string })
    .chapter_id;
  const initial = "雨夜，船夫左臂有伤。";
  const saved = await page.request.put(`/api/v1/chapters/${chapter}/content`, {
    headers: {
      ...(await headers()),
      "If-Match": chapterResponse.headers().etag,
    },
    data: { content: initial },
  });
  expect(saved.status()).toBe(200);
  const plan = await page.request.put(`/api/v1/chapters/${chapter}/planning`, {
    headers: await headers(),
    data: {
      expected_version: 0,
      memory_focuses: ["寻找线索"],
      target_characters: 3000,
      chapter_goal: "渡口寻线索",
      conflict: "船夫不愿回答",
      continuity_notes: "延续雨夜",
      scenes: [],
      include_story_bible: false,
      writing_rule_revision_ids: [],
    },
  });
  expect(plan.status()).toBe(200);
  const rule = await post(`/api/v1/projects/${project}/writing/rules`, {
    title: "动作衔接",
    reference_id: null,
    confirmed: true,
    rules: [{ name: "动作", instruction: "连接动作", applies_to: "全部" }],
  });
  expect(rule.status()).toBe(201);
  const source = (
    (await (
      await page.request.get(`/api/v1/chapters/${chapter}/memory`)
    ).json()) as { source_revision: string }
  ).source_revision;
  const fact = await post(`/api/v1/chapters/${chapter}/memory/facts`, {
    expected_version: 0,
    source_revision: source,
    title: "船夫旧伤",
    text: "船夫左臂有伤",
    quote: "船夫左臂有伤",
  });
  expect(fact.status()).toBe(201);
  const factId = ((await fact.json()) as { id: string }).id;
  const confirmed = await page.request.put(
    `/api/v1/chapters/${chapter}/memory/facts/${factId}`,
    {
      headers: await headers(),
      data: {
        expected_version: 1,
        source_revision: source,
        title: "船夫旧伤",
        text: "船夫左臂有伤",
        quote: "船夫左臂有伤",
        status: "confirmed",
      },
    },
  );
  expect(confirmed.status()).toBe(200);
  await page.goto(`/projects/${project}/chapters/${chapter}/write`);
  const editor = page.getByLabel("章节正文");
  await expect(editor).toHaveValue(initial);
  const panel = page.getByRole("region", { name: "外部 AI 交接" });
  await panel
    .getByRole("button", { name: "外部 AI 交接", exact: true })
    .click();
  await panel.getByLabel("本次任务说明").fill("从渡口继续");
  await panel.getByRole("button", { name: "读取可选规划、规则和事实" }).click();
  await panel.getByLabel(/本章规划 · 版本/).check();
  await panel.getByLabel(/写作规则：动作衔接/).check();
  await panel.getByLabel(/已确认事实：船夫旧伤/).check();
  await panel.getByRole("button", { name: "预览交接内容" }).click();
  await expect(panel.getByText("确认交接内容")).toBeVisible();
  const preview = panel.locator("pre").first();
  await expect(preview).toContainText("渡口寻线索");
  await expect(preview).toContainText("动作衔接");
  await expect(preview).toContainText("船夫旧伤");
  await expect(preview).not.toContainText(initial);
  await panel.getByRole("button", { name: "确认保存交接任务" }).click();
  await expect(panel.getByRole("button", { name: "下载交接包" })).toBeVisible();
  browserAudit.allowOneExpectedHandoffDownload();
  const downloaded = page.waitForEvent("download");
  await panel.getByRole("button", { name: "下载交接包" }).click();
  const file = await downloaded;
  expect(file.suggestedFilename()).toBe("handoff.zip");
  expect(await file.failure()).toBeNull();
  const archive = await readFile(await file.path());
  const entries = new Map<string, string>();
  for (
    let offset = 0;
    offset + 30 <= archive.length &&
    archive.readUInt32LE(offset) === 0x04034b50;
  ) {
    const method = archive.readUInt16LE(offset + 8);
    const size = archive.readUInt32LE(offset + 18);
    const nameLength = archive.readUInt16LE(offset + 26);
    const extraLength = archive.readUInt16LE(offset + 28);
    const name = archive
      .subarray(offset + 30, offset + 30 + nameLength)
      .toString("utf8");
    const start = offset + 30 + nameLength + extraLength;
    const bytes = archive.subarray(start, start + size);
    expect([0, 8]).toContain(method);
    entries.set(
      name,
      (method === 8 ? inflateRawSync(bytes) : bytes).toString("utf8"),
    );
    offset = start + size;
  }
  expect([...entries.keys()].sort()).toEqual([
    "context.json",
    "manifest.json",
    "task.md",
  ]);
  expect(entries.get("context.json")).toContain("渡口寻线索");
  expect(entries.get("context.json")).toContain("船夫旧伤");
  expect(entries.get("context.json")).not.toContain(initial);

  const external = "渡口的风掠过河面，旅人提灯向船夫走去。".repeat(11);
  await panel.getByLabel("粘贴外部返回正文").fill(external);
  await panel.getByRole("button", { name: "导入为外部候选" }).click();
  await expect(
    panel.getByRole("region", { name: "外部候选对照" }),
  ).toContainText(external);
  await expect(editor).toHaveValue(initial);
  await panel.getByRole("button", { name: "确认追加候选到正文" }).click();
  await expect(editor).toHaveValue(`${initial}\n\n${external}`);
  expect(calls).toEqual([]);
  expectCleanBrowserAudit(browserAudit);
});
