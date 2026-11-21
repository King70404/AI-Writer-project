import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { securitySession } from "../../frontend/src/api/security-session";
import { writingJobsClient } from "../../frontend/src/features/writing-jobs/client";

const job = {
  job_id: "job 1",
  project_id: "p 1",
  title: "首卷",
  status: "planned",
  version: 1,
  current_index: 0,
  steps: [{ chapter_id: "c1", status: "pending" }],
  max_requests: 10,
  max_output_characters: 3000,
  claimed_requests: 0,
  used_characters: 0,
  active_run_id: null,
  generated_characters: 0,
  adopted_characters: 0,
  scene_progress: [
    {
      step_index: 0,
      chapter_id: "c1",
      plan_revision_id: "plan-1",
      plan_version: 1,
      current_plan_revision_id: "plan-1",
      current_plan_version: 1,
      needs_recheck: false,
      has_adopted: false,
      scenes: [{ scene_id: "s1", title: "渡口", status: "pending" }],
      target_scene_id: null,
      next_scene_id: "s1",
      done_count: 0,
      skipped_count: 0,
      total: 1,
    },
  ],
};
const progress = job.scene_progress[0];

let fetcher: ReturnType<typeof vi.fn<typeof fetch>>;

beforeEach(() => {
  vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
    csrfToken: "fake-csrf-proof".repeat(3),
    expiresAtMilliseconds: Date.now() + 60_000,
  });
  fetcher = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetcher);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
});

function call(index: number): { url: string; init: RequestInit } {
  const [url, init] = fetcher.mock.calls[index];
  return { url: url as string, init: init ?? {} };
}

describe("写作任务 API 客户端", () => {
  it("读取列表与单个任务，编码路径", async () => {
    fetcher.mockResolvedValueOnce(Response.json([job]));
    fetcher.mockResolvedValueOnce(
      Response.json({ ...job, active_run_id: "run-1" }),
    );
    const list = await writingJobsClient.list("p 1");
    expect(list[0].title).toBe("首卷");
    expect(call(0).url).toContain("projects/p%201/writing-jobs");
    const one = await writingJobsClient.get("job 1");
    expect(one.active_run_id).toBe("run-1");
    expect(call(1).url).toContain("writing-jobs/job%201");
  });

  it("写操作带 CSRF 与预期版本", async () => {
    fetcher.mockImplementation(() => Promise.resolve(Response.json(job)));
    await writingJobsClient.create("p 1", "首卷", ["c1"], 3, 900);
    await writingJobsClient.bind("job 1", "run-1", 1);
    await writingJobsClient.act("job 1", "pause", 2);
    await writingJobsClient.markScene(
      "job 1",
      {
        step_index: 0,
        plan_revision_id: "plan-1",
        action: "target",
        scene_id: "s1",
      },
      3,
    );
    const bodies = fetcher.mock.calls.map(
      ([, init]) => JSON.parse(init?.body as string) as unknown,
    );
    expect(bodies).toEqual([
      {
        title: "首卷",
        chapter_ids: ["c1"],
        max_requests: 3,
        max_output_characters: 900,
      },
      { run_id: "run-1", expected_version: 1 },
      { expected_version: 2 },
      {
        step_index: 0,
        plan_revision_id: "plan-1",
        action: "target",
        scene_id: "s1",
        expected_version: 3,
      },
    ]);
    expect(call(3).url).toContain("writing-jobs/job%201/scene-progress");
    expect(call(1).url).toContain("writing-jobs/job%201/bind-run");
    expect(call(2).url).toContain("writing-jobs/job%201/pause");
    expect(new Headers(call(0).init.headers).get("X-CSRF-Token")).toBe(
      "fake-csrf-proof".repeat(3),
    );
  });

  it.each([
    ["非对象", []],
    ["状态未知", { ...job, status: "running" }],
    ["步骤不是数组", { ...job, steps: {} }],
    ["步骤为空", { ...job, steps: [] }],
    ["步骤状态未知", { ...job, steps: [{ chapter_id: "c1", status: "x" }] }],
    ["步骤非对象", { ...job, steps: ["c1"] }],
    ["当前序号越界", { ...job, current_index: 2 }],
    ["计数为负", { ...job, claimed_requests: -1 }],
    ["计数非整数", { ...job, version: 1.5 }],
    ["标识非字符串", { ...job, job_id: 1 }],
    ["运行标识非法", { ...job, active_run_id: 3 }],
    ["缺少场景进度", { ...job, scene_progress: undefined }],
    ["场景进度数量不符", { ...job, scene_progress: [] }],
    ["场景进度非对象", { ...job, scene_progress: [1] }],
    [
      "场景进度序号错位",
      { ...job, scene_progress: [{ ...progress, step_index: 1 }] },
    ],
    [
      "场景列表非数组",
      { ...job, scene_progress: [{ ...progress, scenes: {} }] },
    ],
    [
      "场景状态未知",
      {
        ...job,
        scene_progress: [
          {
            ...progress,
            scenes: [{ scene_id: "s1", title: "x", status: "y" }],
          },
        ],
      },
    ],
    [
      "核对标志非布尔",
      { ...job, scene_progress: [{ ...progress, needs_recheck: 1 }] },
    ],
    [
      "规划版本非法",
      { ...job, scene_progress: [{ ...progress, plan_version: -1 }] },
    ],
  ])("拒绝畸形任务：%s", async (_name, body) => {
    fetcher.mockResolvedValueOnce(Response.json(body));
    await expect(writingJobsClient.get("job 1")).rejects.toThrow();
  });

  it("接受尚无规划的空场景进度", async () => {
    fetcher.mockResolvedValueOnce(
      Response.json({
        ...job,
        scene_progress: [
          {
            ...progress,
            plan_revision_id: null,
            plan_version: null,
            current_plan_revision_id: null,
            current_plan_version: null,
            scenes: [],
            next_scene_id: null,
            total: 0,
          },
        ],
      }),
    );
    const parsed = await writingJobsClient.get("job 1");
    expect(parsed.scene_progress[0].plan_revision_id).toBeNull();
    expect(parsed.scene_progress[0].scenes).toEqual([]);
  });

  it("拒绝非数组列表", async () => {
    fetcher.mockResolvedValueOnce(Response.json({ items: [job] }));
    await expect(writingJobsClient.list("p 1")).rejects.toThrow();
  });
});
