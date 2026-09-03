import { act, fireEvent, render, screen } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChapterWritingPage } from "../../frontend/src/features/novel-structure/pages/ChapterWritingPage";
import type { NovelStructureApiClient } from "../../frontend/src/features/novel-structure/api/client";
import type { VersionedChapter } from "../../frontend/src/features/novel-structure/api/contracts";
import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import { chapterWritingPath } from "../../frontend/src/features/novel-structure/routing";
import {
  chapterId,
  secondChapterId,
  structureProjectId,
  structureError,
  versionedChapter,
} from "./novel-structure-support";
import {
  detailClient,
  secondProjectId,
  versionedResource,
} from "./project-detail-support";
import {
  flushReact,
  deferred,
  written,
  writingClient,
} from "./chapter-writing-support";

beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }));
afterEach(() => vi.useRealTimers());

async function show(
  client: NovelStructureApiClient = writingClient(),
  projectClient = detailClient(),
  path = chapterWritingPath(structureProjectId, chapterId),
) {
  let view!: ReturnType<typeof render>;
  await flushReact(() => {
    view = render(
      <MemoryRouter initialEntries={[path]}>
        <Link to={chapterWritingPath(structureProjectId, secondChapterId)}>
          另一章
        </Link>
        <Routes>
          <Route
            path="/projects/:projectId/chapters/:chapterId/write"
            element={
              <ChapterWritingPage
                client={client}
                projectClient={projectClient}
              />
            }
          />
          <Route
            path="/projects/:projectId/structure"
            element={<h2>结构返回页</h2>}
          />
        </Routes>
      </MemoryRouter>,
    );
  });
  return view;
}

describe("Chapter writing workspace", () => {
  it("loads project, chapter, volume and empty content before exposing the editor", async () => {
    const client = writingClient();
    const project = detailClient();
    await show(client, project);
    expect(project.getProject).toHaveBeenCalledTimes(1);
    expect(client.getChapter).toHaveBeenCalledWith(
      chapterId,
      structureProjectId,
      undefined,
      expect.any(AbortSignal),
    );
    expect(client.getVolume).toHaveBeenCalledTimes(1);
    expect(client.getChapterContent).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("region", { name: "第1章 / 第一章" }),
    ).toBeVisible();
    expect(screen.getByLabelText("章节正文")).toHaveValue("");
    expect(screen.getByLabelText("字符数")).toHaveTextContent("字符数：0");
    expect(screen.getByRole("status", { name: "保存状态" })).toHaveTextContent(
      "已保存",
    );
    expect(screen.getByRole("button", { name: "立即保存" })).toBeDisabled();
    expect(screen.getByText("所属卷：第一卷")).toBeVisible();
    fireEvent.click(screen.getByRole("link", { name: "返回小说结构" }));
    expect(screen.getByRole("heading", { name: "结构返回页" })).toBeVisible();
  });

  it("provides accessible real saving states, manual save, Ctrl+S and tab insertion", async () => {
    const pending = deferred<ReturnType<typeof written>>();
    const write = vi
      .fn()
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce(written("甲\t乙", 3));
    await show(writingClient({ updateChapterContent: write }));
    const editor = screen.getByLabelText<HTMLTextAreaElement>("章节正文");
    fireEvent.change(editor, { target: { value: "甲乙" } });
    expect(screen.getByRole("status", { name: "保存状态" })).toHaveTextContent(
      "未保存",
    );
    fireEvent.click(screen.getByRole("button", { name: "立即保存" }));
    expect(screen.getByRole("status", { name: "保存状态" })).toHaveTextContent(
      "正在保存",
    );
    await flushReact(() => pending.resolve(written("甲乙", 2)));
    editor.setSelectionRange(1, 1);
    fireEvent.keyDown(editor, { key: "Tab" });
    expect(editor).toHaveValue("甲\t乙");
    expect(screen.getByLabelText("字符数")).toHaveTextContent("字符数：3");
    const shortcut = new KeyboardEvent("keydown", {
      key: "s",
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    await flushReact(() => {
      editor.dispatchEvent(shortcut);
    });
    expect(shortcut.defaultPrevented).toBe(true);
    expect(write).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status", { name: "保存状态" })).toHaveTextContent(
      "已保存",
    );
    fireEvent.keyDown(editor, { key: "Tab", shiftKey: true });
    fireEvent.keyDown(editor, { key: "Tab", ctrlKey: true });
    fireEvent.keyDown(editor, { key: "Tab", altKey: true });
    expect(editor).toHaveValue("甲\t乙");
  });

  it("shows conflict without overwriting the local draft and labels destructive reload explicitly", async () => {
    const reload = deferred<ReturnType<typeof written>>();
    const get = vi
      .fn()
      .mockResolvedValueOnce(written())
      .mockRejectedValueOnce(new Error("private"))
      .mockReturnValueOnce(reload.promise);
    await show(
      writingClient({
        getChapterContent: get,
        updateChapterContent: vi
          .fn()
          .mockRejectedValue(structureError("conflict", "safe")),
      }),
    );
    fireEvent.change(screen.getByLabelText("章节正文"), {
      target: { value: "我的未保存稿" },
    });
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.getByRole("status", { name: "保存状态" })).toHaveTextContent(
      "版本冲突",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "当前内容尚未覆盖服务器版本",
    );
    expect(screen.getByLabelText("章节正文")).toHaveValue("我的未保存稿");
    const button = screen.getByRole("button", {
      name: "丢弃本地正文并重新加载服务器版本",
    });
    await flushReact(() => {
      fireEvent.click(button);
    });
    expect(
      screen.getByText("重新加载失败，本地正文仍保留，请手动重试。"),
    ).toBeVisible();
    fireEvent.click(button);
    expect(screen.getByText("正在重新读取服务器正文…")).toBeVisible();
    expect(screen.getByLabelText("章节正文")).toHaveAttribute("readonly");
    fireEvent.keyDown(screen.getByLabelText("章节正文"), { key: "Tab" });
    await flushReact(() => reload.resolve(written("服务器正文", 7)));
    expect(screen.getByLabelText("章节正文")).toHaveValue("服务器正文");
    expect(screen.getByRole("status", { name: "保存状态" })).toHaveTextContent(
      "已保存",
    );
  });

  it("shows a safe failure and uses the same manual retry pipeline", async () => {
    const write = vi
      .fn()
      .mockRejectedValueOnce(new Error("private body"))
      .mockResolvedValueOnce(written("保留", 2));
    await show(writingClient({ updateChapterContent: write }));
    fireEvent.change(screen.getByLabelText("章节正文"), {
      target: { value: "保留" },
    });
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "保存失败，当前正文已保留",
    );
    await flushReact(() => {
      fireEvent.click(screen.getByRole("button", { name: "立即保存" }));
    });
    expect(screen.getByRole("status", { name: "保存状态" })).toHaveTextContent(
      "已保存",
    );
  });

  it.each([
    `/projects/bad/chapters/${chapterId}/write`,
    `/projects/${structureProjectId}/chapters/bad/write`,
  ])("rejects invalid route %s before loading", async (path) => {
    const client = writingClient();
    const project = detailClient();
    await show(client, project, path);
    expect(screen.getByRole("alert")).toHaveTextContent("编号无效");
    expect(project.getProject).not.toHaveBeenCalled();
    expect(client.getChapter).not.toHaveBeenCalled();
  });

  it("does not expose any editor until the project and chapter have loaded", async () => {
    const project = deferred<ReturnType<typeof versionedResource>>();
    const chapter = deferred<VersionedChapter>();
    await show(
      writingClient({ getChapter: vi.fn().mockReturnValue(chapter.promise) }),
      detailClient(vi.fn().mockReturnValue(project.promise)),
    );
    expect(screen.getByText("正在加载项目…")).toBeVisible();
    expect(screen.queryByLabelText("章节正文")).not.toBeInTheDocument();
    await flushReact(() => project.resolve(versionedResource()));
    expect(screen.getByText("正在加载章节结构与正文…")).toBeVisible();
    await flushReact(() => chapter.resolve(versionedChapter()));
    expect(screen.getByLabelText("章节正文")).toHaveValue("");
  });

  it("renders missing project safely and can retry project transport failure", async () => {
    const get = vi
      .fn()
      .mockRejectedValueOnce(new Error("private"))
      .mockRejectedValueOnce(
        new ProjectApiError({
          kind: "not_found",
          code: "PROJECT_NOT_FOUND",
          message: "不存在",
        }),
      );
    await show(writingClient(), detailClient(get));
    expect(screen.getByRole("alert")).toHaveTextContent("项目加载失败");
    await flushReact(() => {
      fireEvent.click(screen.getByRole("button", { name: "重新加载项目" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("项目不存在");
  });

  it.each([{ project_id: secondProjectId }, { chapter_id: secondChapterId }])(
    "rejects Chapter ownership or identity mismatch before fetching content",
    async (overrides) => {
      const client = writingClient({
        getChapter: vi.fn().mockResolvedValue(versionedChapter(1, overrides)),
      });
      await show(client);
      expect(screen.getByRole("alert")).toHaveTextContent(
        "章节不存在或不属于当前项目",
      );
      expect(screen.queryByLabelText("章节正文")).not.toBeInTheDocument();
      expect(client.getChapterContent).not.toHaveBeenCalled();
    },
  );

  it.each([
    { project_id: secondProjectId },
    { chapter_id: secondChapterId },
    { volume_id: "wrong-volume" },
  ])("rejects content ownership mismatch", async (overrides) => {
    await show(
      writingClient({
        getChapterContent: vi.fn().mockResolvedValue({
          ...written(),
          resource: { ...written().resource, ...overrides },
        }),
      }),
    );
    expect(screen.queryByLabelText("章节正文")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("章节不存在");
  });

  it.each(["not_found", "project_not_found", "contract"] as const)(
    "renders safe missing state for %s",
    async (kind) => {
      await show(
        writingClient({
          getChapter: vi
            .fn()
            .mockRejectedValue(structureError(kind, "private")),
        }),
      );
      expect(screen.getByRole("alert")).toHaveTextContent("章节不存在");
    },
  );

  it("can retry a failed chapter load", async () => {
    const get = vi
      .fn()
      .mockRejectedValueOnce(new Error("private"))
      .mockResolvedValueOnce(versionedChapter());
    await show(writingClient({ getChapter: get }));
    expect(screen.getByRole("alert")).toHaveTextContent("章节加载失败");
    await flushReact(() => {
      fireEvent.click(screen.getByRole("button", { name: "重新加载章节" }));
    });
    expect(screen.getByLabelText("章节正文")).toHaveValue("");
  });

  it.each(["chapter", "volume", "content", "error"])(
    "ignores obsolete %s load after unmount",
    async (stage) => {
      const pending = deferred<never>();
      const client = writingClient(
        stage === "chapter" || stage === "error"
          ? { getChapter: vi.fn().mockReturnValue(pending.promise) }
          : stage === "volume"
            ? { getVolume: vi.fn().mockReturnValue(pending.promise) }
            : { getChapterContent: vi.fn().mockReturnValue(pending.promise) },
      );
      const view = await show(client);
      view.unmount();
      await flushReact(() => {
        if (stage === "error") pending.reject(new Error("private"));
        else pending.resolve(undefined as never);
      });
      expect(screen.queryByLabelText("章节正文")).not.toBeInTheDocument();
    },
  );

  it("does not retain old editable content during a Chapter route change", async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(versionedChapter())
      .mockReturnValueOnce(new Promise<VersionedChapter>(() => undefined));
    await show(
      writingClient({
        getChapter: get,
        getChapterContent: vi.fn().mockResolvedValue(written("旧章正文")),
      }),
    );
    expect(screen.getByLabelText("章节正文")).toHaveValue("旧章正文");
    await flushReact(() => {
      fireEvent.click(screen.getByRole("link", { name: "另一章" }));
    });
    expect(screen.queryByLabelText("章节正文")).not.toBeInTheDocument();
    expect(screen.getByText("正在加载章节结构与正文…")).toBeVisible();
  });
});
