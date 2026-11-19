import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../frontend/src/api/errors";
import { WritingJobsPanel } from "../../frontend/src/features/writing-jobs/WritingJobsPanel";
import type {
  StepSceneProgress,
  WritingJob,
  WritingJobsClient,
} from "../../frontend/src/features/writing-jobs/client";
import {
  workspaceClient,
  type ChapterSummary,
} from "../../frontend/src/features/workbench/api/workspace";
import {
  chapterId,
  secondChapterId,
  structureProjectId,
  volumeId,
} from "./novel-structure-support";

function chapter(id: string, title: string, position: number): ChapterSummary {
  return {
    chapter_id: id,
    volume_id: volumeId,
    title,
    position,
    characters: 0,
    updated_at: "2026-01-01T00:00:00Z",
    editorial_status: "draft",
    editorial_version: 0,
    content_changed_since_editorial: false,
    open_actions: 0,
  };
}
const chapters = [
  chapter(chapterId, "晨光", 1),
  chapter(secondChapterId, "夜行", 2),
];
function progress(
  step_index: number,
  chapter_id: string,
  changes: Partial<StepSceneProgress> = {},
): StepSceneProgress {
  return {
    step_index,
    chapter_id,
    plan_revision_id: null,
    plan_version: null,
    current_plan_revision_id: null,
    current_plan_version: null,
    needs_recheck: false,
    has_adopted: false,
    scenes: [],
    target_scene_id: null,
    next_scene_id: null,
    done_count: 0,
    skipped_count: 0,
    total: 0,
    ...changes,
  };
}
function job(
  chapterIds: readonly string[],
  changes: Partial<WritingJob> = {},
): WritingJob {
  return {
    job_id: "job-1",
    project_id: structureProjectId,
    title: "首卷写作",
    status: "planned",
    version: 1,
    current_index: 0,
    max_requests: 10,
    max_output_characters: 3000,
    claimed_requests: 0,
    used_characters: 0,
    active_run_id: null,
    steps: chapterIds.map((chapter_id) => ({ chapter_id, status: "pending" })),
    scene_progress: chapterIds.map((chapter_id, index) =>
      progress(index, chapter_id),
    ),
    ...changes,
  };
}
function apiError(status: number): ApiError {
  return new ApiError({
    status,
    code: "X",
    message: "失败",
    details: {},
    retryable: false,
    suggestedAction: null,
    requestId: null,
  });
}
function setup(
  initial: readonly WritingJob[] = [],
  overrides: Partial<WritingJobsClient> = {},
  pages = [
    {
      items: chapters,
      total: 2,
      offset: 0,
      next_offset: null as number | null,
    },
  ],
) {
  const jobs: WritingJobsClient = {
    list: vi.fn().mockResolvedValue(initial),
    get: vi.fn(),
    bind: vi.fn(),
    markScene: vi.fn(),
    create: vi
      .fn()
      .mockImplementation(
        (_project: string, _title: string, ids: readonly string[]) =>
          Promise.resolve(job(ids)),
      ),
    act: vi.fn().mockImplementation((_id: string, action: string) =>
      Promise.resolve(
        action === "finish-step"
          ? job([chapterId, secondChapterId], {
              version: 2,
              current_index: 1,
              steps: [
                { chapter_id: chapterId, status: "completed" },
                { chapter_id: secondChapterId, status: "pending" },
              ],
            })
          : job([chapterId], {
              status: action === "pause" ? "paused" : "planned",
              version: 2,
            }),
      ),
    ),
    ...overrides,
  };
  const chaptersMock = vi.fn();
  for (const page of pages) chaptersMock.mockResolvedValueOnce(page);
  const workspace = { ...workspaceClient, chapters: chaptersMock };
  render(
    <MemoryRouter>
      <WritingJobsPanel
        projectId={structureProjectId}
        client={jobs}
        chaptersClient={workspace}
      />
    </MemoryRouter>,
  );
  return { jobs, workspace };
}

describe("跨章写作任务", () => {
  it("创建前不请求，按作者选择顺序创建并进入当前章节", async () => {
    const { jobs, workspace } = setup();
    expect(jobs.list).not.toHaveBeenCalled();
    expect(workspace.chapters).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    const second = await screen.findByRole("checkbox", { name: /夜行/u });
    fireEvent.click(second);
    fireEvent.click(screen.getByRole("checkbox", { name: /晨光/u }));
    fireEvent.change(screen.getByRole("textbox", { name: "任务名称" }), {
      target: { value: "首卷写作" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建任务清单" }));
    expect(
      await screen.findByText("任务已创建；请选择当前章节进入写作台。"),
    ).toBeInTheDocument();
    expect(jobs.create).toHaveBeenCalledWith(
      structureProjectId,
      "首卷写作",
      [secondChapterId, chapterId],
      10,
      3000,
    );
    expect(
      screen.getByRole("link", { name: "进入当前章节写作" }),
    ).toHaveAttribute(
      "href",
      `/projects/${structureProjectId}/chapters/${secondChapterId}/write?job=job-1`,
    );
    expect(screen.getByText(/任务总额度限制本清单的发送/u)).toBeInTheDocument();
  });
  it("恢复已保存清单，作者结束当前章后才显示下一章", async () => {
    const { jobs } = setup([job([chapterId, secondChapterId])]);
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    const item = (
      await screen.findByRole("heading", { name: "首卷写作" })
    ).closest("li");
    expect(item).not.toBeNull();
    expect(
      within(item!).getByRole("link", { name: "进入当前章节写作" }),
    ).toHaveAttribute(
      "href",
      `/projects/${structureProjectId}/chapters/${chapterId}/write?job=job-1`,
    );
    fireEvent.click(
      within(item!).getByRole("button", { name: "结束本章任务" }),
    );
    expect(
      await screen.findByText("已结束本章任务；章节定稿状态没有改变。"),
    ).toBeInTheDocument();
    expect(jobs.act).toHaveBeenCalledWith("job-1", "finish-step", 1);
    expect(
      within(item!).getByRole("link", { name: "进入当前章节写作" }),
    ).toHaveAttribute(
      "href",
      `/projects/${structureProjectId}/chapters/${secondChapterId}/write?job=job-1`,
    );
  });
  it("暂停、恢复与终止只改变状态，按钮随状态切换", async () => {
    const act = vi
      .fn()
      .mockResolvedValueOnce(job([chapterId], { status: "paused", version: 2 }))
      .mockResolvedValueOnce(
        job([chapterId], { status: "planned", version: 3 }),
      )
      .mockResolvedValueOnce(
        job([chapterId], { status: "cancelled", version: 4 }),
      );
    setup([job([chapterId])], { act });
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    fireEvent.click(await screen.findByRole("button", { name: "暂停任务" }));
    fireEvent.click(await screen.findByRole("button", { name: "恢复任务" }));
    expect(act).toHaveBeenNthCalledWith(2, "job-1", "resume", 2);
    fireEvent.click(await screen.findByRole("button", { name: "暂停任务" }));
    expect(act).toHaveBeenNthCalledWith(3, "job-1", "pause", 3);
  });
  it("终止任务后不再提供写作入口", async () => {
    const act = vi
      .fn()
      .mockResolvedValue(job([chapterId], { status: "cancelled", version: 2 }));
    setup([job([chapterId])], { act });
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    fireEvent.click(await screen.findByRole("button", { name: "终止任务" }));
    expect(await screen.findByText("任务状态已更新。")).toBeInTheDocument();
    expect(screen.getByText(/已终止/u)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "进入当前章节写作" })).toBeNull();
    expect(act).toHaveBeenCalledWith("job-1", "cancel", 1);
  });
  it.each([
    [409, "任务状态已变化，请刷新后再操作。"],
    [503, "当前数据库需要升级后才能使用写作任务，请先停止服务并备份。"],
    [404, "任务或章节已不存在，请刷新后重试。"],
    [422, "请检查任务名称和选择的章节。"],
  ])("操作失败 %s 显示可理解原因", async (status, text) => {
    setup([job([chapterId])], {
      act: vi.fn().mockRejectedValue(apiError(status)),
    });
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "结束本章任务" }),
    );
    expect(await screen.findByText(text)).toBeInTheDocument();
  });
  it("加载失败可刷新，创建失败保留选择", async () => {
    const list = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue([]);
    const create = vi.fn().mockRejectedValue(apiError(422));
    setup([], { list, create }, [
      { items: chapters, total: 2, offset: 0, next_offset: null },
      { items: chapters, total: 2, offset: 0, next_offset: null },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    expect(
      await screen.findByText("写作任务未能完成，请检查连接后重试。"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "刷新任务" }));
    expect(await screen.findByText("还没有写作任务。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /晨光/u }));
    fireEvent.change(screen.getByRole("textbox", { name: "任务名称" }), {
      target: { value: "失败任务" },
    });
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "任务最多发送次数" }),
      {
        target: { value: "3" },
      },
    );
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "任务最多生成字数" }),
      {
        target: { value: "900" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "创建任务清单" }));
    expect(
      await screen.findByText("请检查任务名称和选择的章节。"),
    ).toBeInTheDocument();
    expect(create).toHaveBeenCalledWith(
      structureProjectId,
      "失败任务",
      [chapterId],
      3,
      900,
    );
    expect(screen.getByRole("checkbox", { name: /晨光/u })).toBeChecked();
    fireEvent.click(screen.getByRole("checkbox", { name: /晨光/u }));
    expect(screen.getByRole("button", { name: "创建任务清单" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "收起写作任务" }));
    expect(screen.queryByText("跨章写作任务")).toBeNull();
  });
  it("分页加载更多章节，空书提示先建章", async () => {
    setup([], {}, [
      { items: [chapters[0]], total: 2, offset: 0, next_offset: 1 },
      { items: [chapters[1]], total: 2, offset: 1, next_offset: null },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "加载更多章节" }),
    );
    expect(
      await screen.findByRole("checkbox", { name: /夜行/u }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "加载更多章节" })).toBeNull();
  });
  it("没有章节时提示先创建，分页失败显示错误", async () => {
    const chaptersPage = { items: [], total: 0, offset: 0, next_offset: 5 };
    const { workspace } = setup([], {}, [chaptersPage]);
    workspace.chapters.mockRejectedValueOnce(apiError(404));
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    expect(await screen.findByText("请先创建章节。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "加载更多章节" }));
    expect(
      await screen.findByText("任务或章节已不存在，请刷新后重试。"),
    ).toBeInTheDocument();
  });

  it("显示当前章场景进度，作者标记目标与跳过，生成不会自动完成", async () => {
    const planned = progress(0, chapterId, {
      plan_revision_id: "plan-1",
      plan_version: 1,
      current_plan_revision_id: "plan-1",
      current_plan_version: 1,
      scenes: [
        { scene_id: "quay", title: "渡口盘问", status: "pending" },
        { scene_id: "deck", title: "甲板夜谈", status: "pending" },
      ],
      next_scene_id: "quay",
      total: 2,
    });
    const markScene = vi.fn().mockResolvedValue(
      job([chapterId], {
        version: 2,
        scene_progress: [
          {
            ...planned,
            scenes: [
              { scene_id: "quay", title: "渡口盘问", status: "pending" },
              { scene_id: "deck", title: "甲板夜谈", status: "skipped" },
            ],
            skipped_count: 1,
            target_scene_id: "quay",
          },
        ],
      }),
    );
    const { jobs } = setup([job([chapterId], { scene_progress: [planned] })], {
      markScene,
    });
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    const section = await screen.findByRole("region", {
      name: "当前章节场景进度",
    });
    expect(within(section).getByText(/场景 0\/2/u)).toBeInTheDocument();
    expect(within(section).getByText("下一场景：渡口盘问")).toBeInTheDocument();
    expect(
      within(section).getByText("采用本章候选后才能标记场景完成。"),
    ).toBeInTheDocument();
    expect(
      within(section).getByRole("button", { name: "标记完成：渡口盘问" }),
    ).toBeDisabled();
    expect(screen.getByText(/场景 0\/2$/u)).toBeInTheDocument();
    fireEvent.click(
      within(section).getByRole("button", { name: "标记跳过：甲板夜谈" }),
    );
    expect(
      await screen.findByText("场景进度已更新；正文和章节状态没有改变。"),
    ).toBeInTheDocument();
    expect(markScene).toHaveBeenCalledWith(
      "job-1",
      {
        step_index: 0,
        plan_revision_id: "plan-1",
        action: "skipped",
        scene_id: "deck",
      },
      1,
    );
    expect(within(section).getByText(/场景 1\/2/u)).toBeInTheDocument();
    expect(
      within(section).getByText("下一场景：渡口盘问（本步目标）"),
    ).toBeInTheDocument();
    expect(
      within(section).getByRole("button", { name: "恢复待写：甲板夜谈" }),
    ).toBeEnabled();
    expect(jobs.act).not.toHaveBeenCalled();
  });
  it("采用后才可标记完成；规划变化时需重新核对", async () => {
    const stale = progress(0, chapterId, {
      plan_revision_id: "plan-1",
      plan_version: 1,
      current_plan_revision_id: "plan-2",
      current_plan_version: 2,
      needs_recheck: true,
      has_adopted: true,
      scenes: [{ scene_id: "quay", title: "渡口盘问", status: "done" }],
      done_count: 1,
      total: 1,
    });
    const markScene = vi.fn().mockResolvedValue(
      job([chapterId], {
        version: 3,
        scene_progress: [
          {
            ...stale,
            plan_revision_id: "plan-2",
            plan_version: 2,
            needs_recheck: false,
            scenes: [{ scene_id: "hold", title: "货舱", status: "pending" }],
            next_scene_id: "hold",
            done_count: 0,
          },
        ],
      }),
    );
    setup([job([chapterId], { version: 2, scene_progress: [stale] })], {
      markScene,
    });
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    const section = await screen.findByRole("region", {
      name: "当前章节场景进度",
    });
    expect(
      within(section).getByText(/已更新为第 2 版，以下进度仍按原规划显示/u),
    ).toBeInTheDocument();
    expect(
      within(section).getByRole("button", { name: "恢复待写：渡口盘问" }),
    ).toBeDisabled();
    fireEvent.click(
      within(section).getByRole("button", { name: "按新规划重新核对" }),
    );
    expect(
      await within(section).findByText("下一场景：货舱"),
    ).toBeInTheDocument();
    expect(markScene).toHaveBeenCalledWith(
      "job-1",
      { step_index: 0, plan_revision_id: "plan-2", action: "recheck" },
      2,
    );
    expect(
      within(section).getByRole("button", { name: "标记完成：货舱" }),
    ).toBeEnabled();
    expect(within(section).queryByRole("note")).toBeNull();
  });
  it("场景标记冲突显示规划变化原因", async () => {
    const planned = progress(0, chapterId, {
      plan_revision_id: "plan-1",
      plan_version: 1,
      current_plan_revision_id: "plan-1",
      current_plan_version: 1,
      scenes: [{ scene_id: "quay", title: "渡口盘问", status: "pending" }],
      next_scene_id: "quay",
      total: 1,
    });
    const failure = new ApiError({
      status: 409,
      code: "WRITING_JOB_SCENE_PLAN_CHANGED",
      message: "失败",
      details: {},
      retryable: false,
      suggestedAction: null,
      requestId: null,
    });
    setup([job([chapterId], { scene_progress: [planned] })], {
      markScene: vi.fn().mockRejectedValue(failure),
    });
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "设为本步目标：渡口盘问" }),
    );
    expect(
      await screen.findByText("章节规划已变化，请刷新任务后重新核对场景。"),
    ).toBeInTheDocument();
  });
  it("没有场景规划时提示先在章节规划中添加", async () => {
    setup([job([chapterId])]);
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    expect(
      await screen.findByText(
        "本章还没有保存场景规划；可在章节规划中按顺序添加场景。",
      ),
    ).toBeInTheDocument();
  });
});

describe("写作任务抽屉中的章节候选稿", () => {
  it("列出本任务产出的候选稿计数并链接到该章，不显示段落正文", async () => {
    setup([
      job([chapterId, secondChapterId], {
        active_run_id: "draft-2",
        active_draft_id: "draft-2",
        current_index: 1,
        steps: [
          { chapter_id: chapterId, status: "completed" },
          { chapter_id: secondChapterId, status: "pending" },
        ],
        drafts: [
          {
            draft_id: "draft-1",
            chapter_id: chapterId,
            step_index: 0,
            status: "exhausted",
            segments: 3,
            pending: 0,
            adopted: 2,
            discarded: 1,
            edited: 1,
            generated_characters: 660,
            adopted_characters: 430,
          },
          {
            draft_id: "draft-2",
            chapter_id: secondChapterId,
            step_index: 1,
            status: "ready",
            segments: 1,
            pending: 1,
            adopted: 0,
            discarded: 0,
            edited: 0,
            generated_characters: 220,
            adopted_characters: 0,
          },
        ],
      }),
    ]);
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    const region = await screen.findByRole("region", {
      name: "「首卷写作」产出的章节候选稿",
    });
    const items = within(region).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent(
      "第 1 章 · 晨光 · 额度已用完 · 共 3 段：已采用 2 · 待采用 0 · 已丢弃 1 · 作者编辑 1 · 生成 660 字 / 采用 430 字",
    );
    expect(items[1]).toHaveTextContent(
      "第 2 章 · 夜行 · 可继续生成（当前步骤）",
    );
    expect(items[1]).not.toHaveTextContent("已丢弃");
    expect(
      within(items[0]).getByRole("link", { name: "打开该章查看候选稿" }),
    ).toHaveAttribute(
      "href",
      `/projects/${structureProjectId}/chapters/${chapterId}/write?job=job-1`,
    );
  });

  it("没有候选稿时不显示该区域", async () => {
    setup([job([chapterId])]);
    fireEvent.click(screen.getByRole("button", { name: "安排写作任务" }));
    await screen.findByRole("heading", { name: "首卷写作" });
    expect(
      screen.queryByRole("region", { name: "「首卷写作」产出的章节候选稿" }),
    ).toBeNull();
  });

  it("客户端严格解析任务候选稿", async () => {
    const { writingJobsClient } =
      await import("../../frontend/src/features/writing-jobs/client");
    const base = {
      job_id: "job-1",
      project_id: structureProjectId,
      title: "t",
      status: "planned",
      version: 1,
      current_index: 0,
      steps: [{ chapter_id: chapterId, status: "pending" }],
      max_requests: 10,
      max_output_characters: 3000,
      claimed_requests: 0,
      used_characters: 0,
      active_run_id: null,
      active_draft_id: null,
      scene_progress: [progress(0, chapterId)],
    };
    const draft = {
      draft_id: "draft-1",
      chapter_id: chapterId,
      step_index: 0,
      status: "ready",
      segments: 1,
      pending: 1,
      adopted: 0,
      discarded: 0,
      edited: 0,
      generated_characters: 220,
      adopted_characters: 0,
      created_at: "t",
    };
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockResolvedValueOnce(Response.json({ ...base, drafts: [draft] }));
    expect((await writingJobsClient.get("job-1")).drafts).toEqual([
      {
        draft_id: "draft-1",
        chapter_id: chapterId,
        step_index: 0,
        status: "ready",
        segments: 1,
        pending: 1,
        adopted: 0,
        discarded: 0,
        edited: 0,
        generated_characters: 220,
        adopted_characters: 0,
      },
    ]);
    fetcher.mockResolvedValueOnce(Response.json(base));
    expect((await writingJobsClient.get("job-1")).drafts).toEqual([]);
    fetcher.mockResolvedValueOnce(
      Response.json({ ...base, drafts: [{ ...draft, status: "done" }] }),
    );
    await expect(writingJobsClient.get("job-1")).rejects.toThrow();
    fetcher.mockResolvedValueOnce(Response.json({ ...base, drafts: {} }));
    await expect(writingJobsClient.get("job-1")).rejects.toThrow();
    vi.unstubAllGlobals();
  });
});
