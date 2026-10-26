import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthorHomePage } from "../../frontend/src/features/workbench/pages/AuthorHomePage";
import { BookshelfPage } from "../../frontend/src/features/workbench/pages/BookshelfPage";
import {
  forgetRecentChapter,
  lastRecentChapter,
  recentChapterForProject,
  recordRecentChapter,
  RECENT_WRITING_KEY,
} from "../../frontend/src/features/workbench/recentWriting";
import { ChapterWritingPage } from "../../frontend/src/features/novel-structure/pages/ChapterWritingPage";
import { aiWorkflowClient } from "../../frontend/src/features/novel-structure/api/ai-workflow";
import { storyMemoryClient } from "../../frontend/src/features/novel-structure/api/story-memory";
import { writingPreparationClient } from "../../frontend/src/features/novel-structure/api/writing-preparation";
import type { NovelStructureApiClient } from "../../frontend/src/features/novel-structure/api/client";
import { chapterWritingPath } from "../../frontend/src/features/novel-structure/routing";
import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import type { ProjectApiClient } from "../../frontend/src/features/projects/api/client";
import {
  chapterId,
  chapterResponse,
  secondChapterId,
  secondVolumeId,
  structureError,
  structureProjectId,
  versionedChapter,
  volumeResponse,
} from "./novel-structure-support";
import {
  detailClient,
  secondProjectId,
  timestamp,
  versionedResource,
} from "./project-detail-support";
import { deferred, written, writingClient } from "./chapter-writing-support";
import { memoryWorkspace } from "./story-memory-support";
import { chapterPlan } from "./writing-preparation-support";

const localModel = {
  id: "default-local",
  name: "测试模型",
  kind: "local" as const,
  base_url: "http://127.0.0.1:1234",
  model: "local-model",
  max_output_tokens: 2048,
  has_key: false,
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

beforeEach(() => {
  localStorage.clear();
  vi.spyOn(aiWorkflowClient, "models").mockResolvedValue([localModel]);
  vi.spyOn(aiWorkflowClient, "list").mockResolvedValue([]);
});
afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("recent writing record", () => {
  it("stores only identifiers and time, per project, and forgets stale targets", () => {
    expect(lastRecentChapter()).toBeNull();
    recordRecentChapter(structureProjectId, chapterId, new Date(0));
    recordRecentChapter(secondProjectId, secondChapterId, new Date(1000));
    expect(lastRecentChapter()).toEqual({
      projectId: secondProjectId,
      chapterId: secondChapterId,
      openedAt: new Date(1000).toISOString(),
    });
    expect(recentChapterForProject(structureProjectId)?.chapterId).toBe(
      chapterId,
    );
    const stored = localStorage.getItem(RECENT_WRITING_KEY) ?? "";
    expect(stored).not.toMatch(/content|title|etag|token|正文/iu);
    forgetRecentChapter(secondProjectId, secondChapterId);
    expect(lastRecentChapter()).toBeNull();
    expect(recentChapterForProject(secondProjectId)).toBeNull();
    expect(recentChapterForProject(structureProjectId)).not.toBeNull();
    forgetRecentChapter(structureProjectId, chapterId);
    expect(localStorage.getItem(RECENT_WRITING_KEY)).toBeNull();
  });

  it("ignores invalid identifiers, corrupted records and unavailable storage", () => {
    recordRecentChapter("bad", chapterId);
    recordRecentChapter(structureProjectId, "bad");
    expect(localStorage.getItem(RECENT_WRITING_KEY)).toBeNull();
    localStorage.setItem(RECENT_WRITING_KEY, "{not json");
    expect(lastRecentChapter()).toBeNull();
    localStorage.setItem(
      RECENT_WRITING_KEY,
      JSON.stringify({
        last: { projectId: structureProjectId, chapterId, openedAt: "never" },
        byProject: [null, { projectId: 1 }],
      }),
    );
    expect(lastRecentChapter()).toBeNull();
    expect(recentChapterForProject(structureProjectId)).toBeNull();
    localStorage.setItem(RECENT_WRITING_KEY, JSON.stringify({ last: null }));
    expect(recentChapterForProject(structureProjectId)).toBeNull();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() =>
      recordRecentChapter(structureProjectId, chapterId),
    ).not.toThrow();
  });

  it("keeps at most fifty projects", () => {
    const ulid = (index: number) =>
      `prj_01ARZ3NDEKTSV4RRFFQ69G${String(index)
        .padStart(4, "0")
        .replace(/[ILOU]/gu, "0")}`;
    for (let index = 0; index < 55; index += 1)
      recordRecentChapter(ulid(1000 + index), chapterId);
    const stored = JSON.parse(
      localStorage.getItem(RECENT_WRITING_KEY) ?? "{}",
    ) as { byProject: unknown[] };
    expect(stored.byProject).toHaveLength(50);
  });
});

function renderHome(
  projectClient = detailClient(),
  structureClient: NovelStructureApiClient = writingClient(),
) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route
          path="/"
          element={
            <AuthorHomePage
              projectClient={projectClient}
              structureClient={structureClient}
            />
          }
        />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("author home continue card", () => {
  it("shows the real novel and chapter titles and continues to the chapter", async () => {
    recordRecentChapter(structureProjectId, chapterId, new Date(timestamp));
    const project = detailClient();
    const structure = writingClient();
    renderHome(project, structure);
    expect(screen.getByText("正在读取上次写作的章节…")).toHaveAttribute(
      "role",
      "status",
    );
    const link = await screen.findByRole("link", { name: "继续写作" });
    expect(link).toHaveAttribute(
      "href",
      chapterWritingPath(structureProjectId, chapterId),
    );
    expect(screen.getByText("项目版本1")).toBeVisible();
    expect(screen.getByText("第1章 · 第一章")).toBeVisible();
    expect(structure.getChapterContent).not.toHaveBeenCalled();
    expect(project.getProject).toHaveBeenCalledOnce();
    fireEvent.click(link);
    expect(screen.getByTestId("location")).toHaveTextContent(
      chapterWritingPath(structureProjectId, chapterId),
    );
  });

  it("drops a deleted novel and points back to the bookshelf", async () => {
    recordRecentChapter(structureProjectId, chapterId);
    renderHome(
      detailClient(
        vi.fn().mockRejectedValue(
          new ProjectApiError({
            kind: "not_found",
            code: "PROJECT_NOT_FOUND",
            message: "missing",
          }),
        ),
      ),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "上次写作的小说已不存在",
    );
    expect(lastRecentChapter()).toBeNull();
    fireEvent.click(screen.getAllByRole("link", { name: "打开书架" })[0]);
    expect(screen.getByTestId("location")).toHaveTextContent("/projects");
  });

  it("returns to the novel structure when the chapter is missing", async () => {
    recordRecentChapter(structureProjectId, chapterId);
    renderHome(
      detailClient(),
      writingClient({
        getChapter: vi
          .fn()
          .mockRejectedValue(structureError("not_found", "missing")),
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "上次写作的章节已不存在",
    );
    expect(screen.getByRole("link", { name: "打开小说结构" })).toHaveAttribute(
      "href",
      `/projects/${structureProjectId}/structure`,
    );
    expect(lastRecentChapter()).toBeNull();
  });

  it("treats a chapter from another novel as missing", async () => {
    recordRecentChapter(structureProjectId, chapterId);
    renderHome(
      detailClient(),
      writingClient({
        getChapter: vi.fn().mockResolvedValue({
          ...versionedChapter(),
          resource: chapterResponse(1, { project_id: secondProjectId }),
        }),
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "上次写作的章节已不存在",
    );
  });

  it("keeps a direct link and retries when reading details fails", async () => {
    recordRecentChapter(structureProjectId, chapterId);
    const getChapter = vi
      .fn()
      .mockRejectedValueOnce(structureError("unavailable", "down"))
      .mockResolvedValue(versionedChapter());
    renderHome(detailClient(), writingClient({ getChapter }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "暂时无法读取上次章节的信息",
    );
    expect(
      screen.getByRole("link", { name: "直接打开上次章节" }),
    ).toHaveAttribute(
      "href",
      chapterWritingPath(structureProjectId, chapterId),
    );
    expect(lastRecentChapter()).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    expect(await screen.findByRole("link", { name: "继续写作" })).toBeVisible();
  });

  it("reports a project read failure without forgetting the record", async () => {
    recordRecentChapter(structureProjectId, chapterId);
    renderHome(
      detailClient(
        vi.fn().mockRejectedValue(
          new ProjectApiError({
            kind: "network",
            code: "NETWORK",
            message: "offline",
          }),
        ),
      ),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "暂时无法读取上次章节的信息",
    );
    expect(lastRecentChapter()).not.toBeNull();
  });
});

describe("bookshelf continue links", () => {
  it("offers 继续写作 only for novels written on this device", async () => {
    recordRecentChapter(structureProjectId, chapterId);
    const item = (id: string, title: string) => ({
      project_id: id,
      current_revision_id: "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV",
      revision_number: 1,
      concurrency_version: 1,
      title,
      created_at: timestamp,
      updated_at: timestamp,
      revision_created_at: timestamp,
    });
    const client = {
      listProjects: vi.fn().mockResolvedValue({
        items: [
          item(structureProjectId, "写过的小说"),
          item(secondProjectId, "新小说"),
        ],
        next_cursor: null,
        has_more: false,
      }),
      createProject: vi.fn(),
    } as unknown as ProjectApiClient;
    render(
      <MemoryRouter>
        <BookshelfPage client={client} />
      </MemoryRouter>,
    );
    const link = await screen.findByRole("link", {
      name: "继续写作《写过的小说》",
    });
    expect(link).toHaveAttribute(
      "href",
      chapterWritingPath(structureProjectId, chapterId),
    );
    expect(
      screen.queryByRole("link", { name: "继续写作《新小说》" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "打开小说" })).toHaveLength(2);
  });
});

function structureForDesk(overrides: Partial<NovelStructureApiClient> = {}) {
  return writingClient({
    listVolumes: vi.fn().mockResolvedValue([
      volumeResponse(1, {
        volume_id: secondVolumeId,
        position: 2,
        title: "第二卷",
      }),
      volumeResponse(),
    ]),
    listChapters: vi
      .fn()
      .mockImplementation((_project: string, volume: string) =>
        Promise.resolve(
          volume === secondVolumeId
            ? []
            : [
                chapterResponse(1, {
                  chapter_id: secondChapterId,
                  position: 2,
                  title: "夜渡",
                }),
                chapterResponse(),
              ],
        ),
      ),
    getChapterContent: vi.fn().mockResolvedValue(written("甲乙丙丁")),
    ...overrides,
  });
}

async function showDesk(client: NovelStructureApiClient = structureForDesk()) {
  const view = render(
    <MemoryRouter
      initialEntries={[chapterWritingPath(structureProjectId, chapterId)]}
    >
      <Routes>
        <Route
          path="/projects/:projectId/chapters/:chapterId/write"
          element={
            <>
              <ChapterWritingPage
                client={client}
                projectClient={detailClient()}
              />
              <LocationProbe />
            </>
          }
        />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByLabelText("章节正文");
  return view;
}

describe("three-column writing desk", () => {
  it("records the chapter locally and renders volume/chapter navigation in order", async () => {
    await showDesk();
    expect(lastRecentChapter()?.chapterId).toBe(chapterId);
    const nav = screen.getByRole("navigation", { name: "卷章导航" });
    await within(nav).findByRole("link", { name: "第1章 第一章" });
    expect(within(nav).getByText("项目版本1")).toBeVisible();
    expect(
      within(nav).getByRole("link", { name: "第1章 第一章" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      within(nav).getByRole("link", { name: "第2章 夜渡" }),
    ).not.toHaveAttribute("aria-current");
    const volumes = within(nav).getAllByText(/^第\d卷 · /u);
    expect(volumes.map((item) => item.textContent)).toEqual([
      "第1卷 · 第一卷",
      "第2卷 · 第二卷",
    ]);
    expect(within(nav).getByText("本卷还没有章节。")).toBeVisible();
    for (const name of ["返回书架", "返回小说结构", "小说设定", "人物"])
      expect(within(nav).getByRole("link", { name })).toBeVisible();
    fireEvent.change(within(nav).getByRole("searchbox", { name: "搜索章节" }), {
      target: { value: "夜" },
    });
    expect(
      within(nav).queryByRole("link", { name: "第1章 第一章" }),
    ).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "第2章 夜渡" })).toBeVisible();
    fireEvent.change(within(nav).getByRole("searchbox", { name: "搜索章节" }), {
      target: { value: "不存在" },
    });
    expect(within(nav).getByText("没有匹配的章节。")).toBeVisible();
    const status = screen.getByRole("region", { name: "写作状态" });
    expect(within(status).getByLabelText("AI 任务状态")).toHaveTextContent(
      "没有进行中的 AI 任务",
    );
    expect(within(status).getByLabelText("字符数")).toHaveTextContent(
      "字符数：4",
    );
  });

  it("shows an empty novel and keeps writing when the directory fails", async () => {
    const listVolumes = vi
      .fn()
      .mockRejectedValueOnce(structureError("unavailable", "down"))
      .mockResolvedValue([]);
    await showDesk(structureForDesk({ listVolumes }));
    const nav = screen.getByRole("navigation", { name: "卷章导航" });
    expect(await within(nav).findByRole("alert")).toHaveTextContent(
      "卷章目录读取失败",
    );
    expect(screen.getByLabelText("章节正文")).toHaveValue("甲乙丙丁");
    fireEvent.click(within(nav).getByRole("button", { name: "重新读取目录" }));
    expect(await within(nav).findByText("还没有卷。")).toBeVisible();
  });

  it("navigates directly between saved chapters", async () => {
    await showDesk();
    const nav = screen.getByRole("navigation", { name: "卷章导航" });
    fireEvent.click(
      await within(nav).findByRole("link", { name: "第2章 夜渡" }),
    );
    await waitFor(() =>
      expect(screen.getAllByTestId("location").at(-1)).toHaveTextContent(
        secondChapterId,
      ),
    );
  });

  it("saves unsaved prose before leaving the chapter", async () => {
    const client = structureForDesk();
    await showDesk(client);
    fireEvent.change(screen.getByLabelText("章节正文"), {
      target: { value: "甲乙丙丁戊" },
    });
    const nav = screen.getByRole("navigation", { name: "卷章导航" });
    fireEvent.click(within(nav).getByRole("link", { name: "返回小说结构" }));
    await waitFor(() =>
      expect(screen.getAllByTestId("location").at(-1)).toHaveTextContent(
        `/projects/${structureProjectId}/structure`,
      ),
    );
    expect(client.updateChapterContent).toHaveBeenCalledWith(
      chapterId,
      structureProjectId,
      "甲乙丙丁戊",
      '"1"',
      expect.any(AbortSignal),
    );
  });

  it("stays on the chapter and keeps prose when saving before leaving fails", async () => {
    const pending = deferred<ReturnType<typeof written>>();
    const client = structureForDesk({
      updateChapterContent: vi.fn().mockReturnValue(pending.promise),
    });
    await showDesk(client);
    fireEvent.change(screen.getByLabelText("章节正文"), {
      target: { value: "未保存的新段落" },
    });
    const nav = screen.getByRole("navigation", { name: "卷章导航" });
    const link = within(nav).getByRole("link", { name: "返回书架" });
    fireEvent.click(link);
    fireEvent.click(link);
    await act(async () => {
      pending.reject(structureError("unavailable", "down"));
      await pending.promise.catch(() => undefined);
    });
    expect(
      await screen.findByText(/当前章节尚未保存，已留在本章/u),
    ).toBeVisible();
    expect(client.updateChapterContent).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("章节正文")).toHaveValue("未保存的新段落");
    expect(screen.getAllByTestId("location").at(-1)).toHaveTextContent(
      "/write",
    );
  });

  it("enters and leaves focus mode without remounting the editor", async () => {
    await showDesk();
    const editor = screen.getByLabelText<HTMLTextAreaElement>("章节正文");
    fireEvent.change(editor, { target: { value: "专注时的正文" } });
    const navigator = document.getElementById("writing-desk-navigator");
    const assistant = document.getElementById("writing-desk-assistant");
    expect(navigator).toBeVisible();
    expect(assistant).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "专注写作" }));
    expect(navigator).not.toBeVisible();
    expect(assistant).not.toBeVisible();
    expect(
      screen.queryByRole("button", { name: "收起目录" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "保存状态" })).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape", isComposing: true });
    expect(navigator).not.toBeVisible();
    fireEvent.keyDown(document, { key: "a" });
    expect(navigator).not.toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(navigator).toBeVisible();
    expect(assistant).toBeVisible();
    expect(screen.getByLabelText("章节正文")).toBe(editor);
    expect(editor).toHaveValue("专注时的正文");
    expect(screen.getByRole("button", { name: "专注写作" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "专注写作" }));
    fireEvent.click(screen.getByRole("button", { name: "退出专注（Esc）" }));
    expect(navigator).toBeVisible();
  });

  it("collapses either side column on request", async () => {
    await showDesk();
    const navigator = document.getElementById("writing-desk-navigator");
    const assistant = document.getElementById("writing-desk-assistant");
    fireEvent.click(screen.getByRole("button", { name: "收起目录" }));
    expect(navigator).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "收起助手" }));
    expect(assistant).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "显示目录" }));
    fireEvent.click(screen.getByRole("button", { name: "显示助手" }));
    expect(navigator).toBeVisible();
    expect(assistant).toBeVisible();
  });

  it("starts with side panels closed on narrow screens", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false }));
    await showDesk();
    expect(document.getElementById("writing-desk-navigator")).not.toBeVisible();
    expect(document.getElementById("writing-desk-assistant")).not.toBeVisible();
    expect(screen.getByRole("button", { name: "显示目录" })).toBeVisible();
  });

  it("offers the structure page and forgets the record when the chapter is gone", async () => {
    recordRecentChapter(structureProjectId, chapterId);
    render(
      <MemoryRouter
        initialEntries={[chapterWritingPath(structureProjectId, chapterId)]}
      >
        <Routes>
          <Route
            path="/projects/:projectId/chapters/:chapterId/write"
            element={
              <ChapterWritingPage
                client={writingClient({
                  getChapter: vi
                    .fn()
                    .mockRejectedValue(structureError("not_found", "gone")),
                })}
                projectClient={detailClient()}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "章节不存在或不属于当前项目。",
    );
    expect(screen.getByRole("link", { name: "打开小说结构" })).toHaveAttribute(
      "href",
      `/projects/${structureProjectId}/structure`,
    );
    expect(lastRecentChapter()).toBeNull();
  });

  it("forgets the record when the chapter belongs to another novel", async () => {
    recordRecentChapter(structureProjectId, chapterId);
    render(
      <MemoryRouter
        initialEntries={[chapterWritingPath(structureProjectId, chapterId)]}
      >
        <Routes>
          <Route
            path="/projects/:projectId/chapters/:chapterId/write"
            element={
              <ChapterWritingPage
                client={writingClient({
                  getChapter: vi.fn().mockResolvedValue({
                    ...versionedChapter(),
                    resource: chapterResponse(1, {
                      project_id: secondProjectId,
                    }),
                  }),
                })}
                projectClient={detailClient(
                  vi.fn().mockResolvedValue(versionedResource()),
                )}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "章节不存在或不属于当前项目。",
    );
    expect(lastRecentChapter()).toBeNull();
  });
});

describe("assistant panels and in-place model settings", () => {
  it("switches 准备/生成/评审 tabs by click and keyboard, mounting panels on demand", async () => {
    const references = vi
      .spyOn(writingPreparationClient, "references")
      .mockResolvedValue([]);
    vi.spyOn(writingPreparationClient, "rules").mockResolvedValue([]);
    vi.spyOn(writingPreparationClient, "plan").mockResolvedValue(null);
    const workspace = vi
      .spyOn(storyMemoryClient, "workspace")
      .mockResolvedValue(memoryWorkspace());
    await showDesk();
    const tabs = screen.getByRole("tablist", { name: "AI 助手分区" });
    const generate = within(tabs).getByRole("tab", { name: "生成" });
    expect(generate).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "准备续写" })).toBeVisible();
    expect(references).not.toHaveBeenCalled();
    expect(workspace).not.toHaveBeenCalled();
    fireEvent.click(within(tabs).getByRole("tab", { name: "准备" }));
    expect(
      await screen.findByRole("region", { name: "范文分析与章节规划" }),
    ).toBeVisible();
    expect(references).toHaveBeenCalledOnce();
    expect(
      screen.queryByRole("button", { name: "准备续写" }),
    ).not.toBeInTheDocument();
    fireEvent.keyDown(within(tabs).getByRole("tab", { name: "准备" }), {
      key: "ArrowRight",
    });
    expect(generate).toHaveFocus();
    expect(generate).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(generate, { key: "ArrowRight" });
    const review = within(tabs).getByRole("tab", { name: "评审" });
    expect(review).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(workspace).toHaveBeenCalledOnce());
    fireEvent.keyDown(review, { key: "Home" });
    expect(within(tabs).getByRole("tab", { name: "准备" })).toHaveFocus();
    fireEvent.keyDown(within(tabs).getByRole("tab", { name: "准备" }), {
      key: "End",
    });
    expect(review).toHaveFocus();
    fireEvent.keyDown(review, { key: "ArrowLeft" });
    expect(generate).toHaveFocus();
    fireEvent.keyDown(generate, { key: "Enter" });
    expect(generate).toHaveAttribute("aria-selected", "true");
    // Returning to a panel keeps it mounted instead of reloading.
    fireEvent.click(within(tabs).getByRole("tab", { name: "准备" }));
    expect(references).toHaveBeenCalledOnce();
  });

  it("returns from a saved plan to 生成 and focuses 准备续写", async () => {
    vi.spyOn(writingPreparationClient, "references").mockResolvedValue([]);
    vi.spyOn(writingPreparationClient, "rules").mockResolvedValue([]);
    vi.spyOn(writingPreparationClient, "plan").mockResolvedValue(chapterPlan());
    vi.spyOn(writingPreparationClient, "savePlan").mockResolvedValue(
      chapterPlan({ version: 2 }),
    );
    await showDesk();
    const tabs = screen.getByRole("tablist", { name: "AI 助手分区" });
    fireEvent.click(within(tabs).getByRole("tab", { name: "准备" }));
    fireEvent.change(
      await screen.findByRole("textbox", { name: "章节重点 1" }),
      { target: { value: "新的章节重点" } },
    );
    expect(
      screen.getByText("章节规划有未保存修改；保存后再准备新任务。"),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "保存章节规划" }));
    const notice = await screen.findByRole("group", { name: "规划已保存" });
    fireEvent.click(
      within(notice).getByRole("button", { name: "去“生成”准备续写" }),
    );
    expect(within(tabs).getByRole("tab", { name: "生成" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "准备续写" })).toHaveFocus(),
    );
  });

  it("offers 添加模型 in place when no model exists and focuses the form", async () => {
    vi.mocked(aiWorkflowClient.models).mockResolvedValue([]);
    await showDesk();
    const summary = screen.getByRole("region", { name: "当前模型" });
    expect(
      await within(summary).findByText(/当前没有模型。手动写作可继续/u),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "准备续写" })).toBeDisabled();
    expect(
      screen.getByText("添加并选择模型后才能准备 AI 任务。"),
    ).toBeVisible();
    const details = document.querySelector("details.ai-model-settings");
    expect(details).not.toHaveAttribute("open");
    fireEvent.click(within(summary).getByRole("button", { name: "添加模型" }));
    expect(details).toHaveAttribute("open");
    expect(screen.getByLabelText("配置名称")).toHaveFocus();
  });

  it("summarises the current model and toggles management", async () => {
    vi.mocked(aiWorkflowClient.models).mockResolvedValue([
      localModel,
      {
        ...localModel,
        id: "cloud-model",
        name: "云端模型",
        kind: "cloud",
        has_key: false,
      },
    ]);
    await showDesk();
    const summary = screen.getByRole("region", { name: "当前模型" });
    expect(
      await within(summary).findByText(/当前模型：测试模型 · 本机模型/u),
    ).toBeVisible();
    expect(summary).toHaveTextContent("尚未检查服务连接");
    fireEvent.change(screen.getByLabelText("使用模型"), {
      target: { value: "cloud-model" },
    });
    expect(summary).toHaveTextContent(
      "云端 · 未保存密钥，发送前需补充 API Key",
    );
    fireEvent.click(within(summary).getByRole("button", { name: "管理模型" }));
    expect(document.querySelector("details.ai-model-settings")).toHaveAttribute(
      "open",
    );
    fireEvent.click(
      within(summary).getByRole("button", { name: "收起模型管理" }),
    );
    expect(
      document.querySelector("details.ai-model-settings"),
    ).not.toHaveAttribute("open");
  });

  it("explains that a prepared task keeps its frozen model snapshot", async () => {
    const run = {
      run_id: "run-one",
      chapter_id: chapterId,
      operation: "continue" as const,
      status: "ready" as const,
      base_revision_id: "revision-one",
      base_version: 1,
      current_revision_id: "revision-one",
      current_version: 1,
      instruction: "",
      selected_text: "",
      profile_id: localModel.id,
      model_snapshot: localModel,
      max_steps: 5,
      max_output_characters: 1500,
      generated_steps: 0,
      generated_characters: 0,
      context: {
        text: "甲乙丙丁",
        sha256: "a".repeat(64),
        manifest: {
          included_sources: ["current_chapter"],
          omitted_sources: [],
          truncated: false,
          character_count: 4,
          sources: [],
        },
      },
      candidates: [],
      last_error: null,
    };
    vi.mocked(aiWorkflowClient.models).mockResolvedValue([
      localModel,
      { ...localModel, id: "other-model", name: "另一个模型" },
    ]);
    vi.mocked(aiWorkflowClient.list).mockResolvedValue([run]);
    await showDesk();
    const status = screen.getByRole("region", { name: "写作状态" });
    await waitFor(() =>
      expect(within(status).getByLabelText("AI 任务状态")).toHaveTextContent(
        "AI 任务：可以生成下一段",
      ),
    );
    expect(screen.queryByText(/冻结的模型/u)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("使用模型"), {
      target: { value: "other-model" },
    });
    expect(
      screen.getByText(
        "当前任务使用准备时冻结的模型“测试模型”；切换模型只影响下一次新准备的任务。",
      ),
    ).toBeVisible();
  });

  it("shows a waiting candidate in the fixed status area", async () => {
    vi.mocked(aiWorkflowClient.list).mockResolvedValue([
      {
        run_id: "run-two",
        chapter_id: chapterId,
        operation: "continue",
        status: "ready",
        base_revision_id: "revision-one",
        base_version: 1,
        current_revision_id: "revision-one",
        current_version: 1,
        instruction: "",
        selected_text: "",
        profile_id: null,
        model_snapshot: localModel,
        max_steps: 5,
        max_output_characters: 1500,
        generated_steps: 1,
        generated_characters: 240,
        context: {
          text: "甲",
          sha256: "a".repeat(64),
          manifest: {
            included_sources: [],
            omitted_sources: [],
            truncated: false,
            character_count: 1,
            sources: [],
          },
        },
        candidates: [
          {
            candidate_id: "candidate-one",
            sequence: 1,
            text: "文".repeat(240),
            model: "local-model",
            character_count: 240,
            status: "pending",
            adopted_revision_id: null,
            adopted_version: null,
            latest_edit: null,
            edit_count: 0,
            adopted_edit_id: null,
          },
        ],
        last_error: null,
      },
    ]);
    await showDesk();
    const status = screen.getByRole("region", { name: "写作状态" });
    await waitFor(() =>
      expect(within(status).getByLabelText("AI 任务状态")).toHaveTextContent(
        "AI 候选待你确认 · 第 1 段",
      ),
    );
  });
});
