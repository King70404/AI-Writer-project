import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
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
    steps: chapterIds.map((chapter_id) => ({ chapter_id, status: "pending" })),
    ...changes,
  };
}
function setup(initial: readonly WritingJob[] = []) {
  const jobs: WritingJobsClient = {
    list: vi.fn().mockResolvedValue(initial),
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
  };
  const workspace = {
    ...workspaceClient,
    chapters: vi
      .fn()
      .mockResolvedValue({
        items: chapters,
        total: 2,
        offset: 0,
        next_offset: null,
      }),
  };
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
    expect(jobs.create).toHaveBeenCalledWith(structureProjectId, "首卷写作", [
      secondChapterId,
      chapterId,
    ]);
    expect(
      screen.getByRole("link", { name: "进入当前章节写作" }),
    ).toHaveAttribute(
      "href",
      `/projects/${structureProjectId}/chapters/${secondChapterId}/write`,
    );
    expect(screen.getByText(/本清单尚未设置跨章总额度/u)).toBeInTheDocument();
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
      `/projects/${structureProjectId}/chapters/${chapterId}/write`,
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
      `/projects/${structureProjectId}/chapters/${secondChapterId}/write`,
    );
  });
});
