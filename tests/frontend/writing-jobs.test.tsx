import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../frontend/src/api/errors";
import { WritingJobsPanel } from "../../frontend/src/features/writing-jobs/WritingJobsPanel";
import type {
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
});
