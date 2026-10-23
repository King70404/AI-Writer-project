import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../frontend/src/api/errors";
import { securitySession } from "../../frontend/src/api/security-session";
import {
  parseActionItem,
  parseChapterSummary,
  parseEditorialState,
  parseWorkspaceSummary,
  workbenchError,
  WorkbenchError,
  workspaceClient,
  type EditorialState,
  type WorkspaceClient,
} from "../../frontend/src/features/workbench/api/workspace";
import { EditorialStatusControl } from "../../frontend/src/features/workbench/components/EditorialStatusControl";
import { WorkspaceSummaryPanel } from "../../frontend/src/features/workbench/components/WorkspaceSummaryPanel";
import {
  chapterId,
  secondChapterId,
  structureProjectId,
  volumeId,
} from "./novel-structure-support";

const generatedAt = "2026-10-23T14:00:00+00:00";

function rawSummary(changes: Record<string, unknown> = {}) {
  return {
    project_id: structureProjectId,
    characters: 12345,
    chapter_count: 2,
    volume_count: 1,
    editorial: { draft: 1, review: 0, final: 1 },
    latest_chapter: {
      chapter_id: chapterId,
      volume_id: volumeId,
      title: "雨夜",
      position: 1,
      updated_at: generatedAt,
    },
    volumes: [
      {
        volume_id: volumeId,
        title: "第一卷",
        position: 1,
        chapter_count: 2,
        characters: 12345,
        editorial: { draft: 1, review: 0, final: 1 },
      },
    ],
    actions: [
      { kind: "stale_fact", items: 1, chapters: 1 },
      { kind: "pending_candidate", items: 2, chapters: 1 },
    ],
    action_total: 3,
    generated_at: generatedAt,
    ...changes,
  };
}

function rawAction(changes: Record<string, unknown> = {}) {
  return {
    kind: "stale_fact",
    chapter_id: chapterId,
    volume_id: volumeId,
    chapter_title: "雨夜",
    chapter_position: 1,
    volume_position: 1,
    count: 1,
    ...changes,
  };
}

function rawChapter(changes: Record<string, unknown> = {}) {
  return {
    chapter_id: chapterId,
    volume_id: volumeId,
    title: "雨夜",
    position: 1,
    characters: 12000,
    updated_at: generatedAt,
    editorial_status: "final",
    editorial_version: 2,
    content_changed_since_editorial: true,
    open_actions: 1,
    ...changes,
  };
}

function page(
  items: unknown[],
  total: number,
  next: number | null,
  offset = 0,
) {
  return {
    project_id: structureProjectId,
    total,
    offset,
    limit: 10,
    next_offset: next,
    items,
  };
}

function rawEditorial(changes: Record<string, unknown> = {}) {
  return {
    chapter_id: chapterId,
    project_id: structureProjectId,
    status: "draft",
    version: 0,
    chapter_revision_id: null,
    content_changed: false,
    open_actions: 0,
    updated_at: null,
    ...changes,
  };
}

function editorialState(changes: Partial<EditorialState> = {}): EditorialState {
  return parseEditorialState(rawEditorial(changes), chapterId);
}

function apiError(code: string, status = 409) {
  return new ApiError({
    code,
    status,
    message: "private",
    details: {},
    retryable: false,
    suggestedAction: null,
    requestId: null,
  });
}

function fakeClient(overrides: Partial<WorkspaceClient> = {}): WorkspaceClient {
  return {
    summary: vi
      .fn()
      .mockResolvedValue(
        parseWorkspaceSummary(rawSummary(), structureProjectId),
      ),
    actions: vi.fn().mockResolvedValue({
      total: 2,
      offset: 0,
      next_offset: null,
      items: [
        parseActionItem(rawAction()),
        parseActionItem(
          rawAction({
            kind: "pending_candidate",
            chapter_id: secondChapterId,
            count: 2,
            chapter_position: 2,
            chapter_title: "晨光",
          }),
        ),
      ],
    }),
    chapters: vi.fn().mockResolvedValue({
      total: 1,
      offset: 0,
      next_offset: null,
      items: [parseChapterSummary(rawChapter())],
    }),
    editorial: vi.fn().mockResolvedValue(editorialState()),
    saveEditorial: vi.fn(),
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
});

describe("workspace API contracts", () => {
  it("decodes server-derived summaries, pages and editorial state", () => {
    const summary = parseWorkspaceSummary(rawSummary(), structureProjectId);
    expect(summary.characters).toBe(12345);
    expect(summary.latest_chapter?.title).toBe("雨夜");
    expect(
      parseWorkspaceSummary(
        rawSummary({ latest_chapter: null }),
        structureProjectId,
      ).latest_chapter,
    ).toBeNull();
    expect(parseChapterSummary(rawChapter()).editorial_status).toBe("final");
    expect(parseActionItem(rawAction()).kind).toBe("stale_fact");
    expect(
      parseEditorialState(
        rawEditorial({ chapter_revision_id: "chv_1", updated_at: generatedAt }),
        chapterId,
      ).chapter_revision_id,
    ).toBe("chv_1");
  });

  it.each([
    { project_id: "other" },
    { characters: -1 },
    { characters: 1.5 },
    { editorial: { draft: 1, review: 0 } },
    { actions: [{ kind: "invented", items: 1, chapters: 1 }] },
    { volumes: null },
    { latest_chapter: { chapter_id: "../x" } },
    { generated_at: 1 },
  ])("rejects malformed summaries: %j", (patch) => {
    expect(() =>
      parseWorkspaceSummary(rawSummary(patch), structureProjectId),
    ).toThrow("无法安全读取");
  });

  it.each([
    [() => parseChapterSummary(rawChapter({ editorial_status: "done" }))],
    [
      () =>
        parseChapterSummary(
          rawChapter({ content_changed_since_editorial: "no" }),
        ),
    ],
    [() => parseActionItem(rawAction({ count: "1" }))],
    [() => parseEditorialState(rawEditorial(), secondChapterId)],
    [() => parseEditorialState(rawEditorial({ status: "auto" }), chapterId)],
    [() => parseEditorialState(null, chapterId)],
  ])("rejects malformed rows %#", (decode) => {
    expect(decode).toThrow("无法安全读取");
  });

  it("requests bounded pages and guards editorial writes with CSRF", async () => {
    vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
      csrfToken: "test-proof",
      expiresAtMilliseconds: Date.now() + 60000,
    });
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(Response.json(rawSummary()))
      .mockResolvedValueOnce(Response.json(page([rawChapter()], 1, null)))
      .mockResolvedValueOnce(Response.json(page([rawAction()], 3, 1)))
      .mockResolvedValueOnce(Response.json(rawEditorial()))
      .mockResolvedValueOnce(
        Response.json(rawEditorial({ status: "final", version: 1 })),
      );
    vi.stubGlobal("fetch", fetcher);
    await workspaceClient.summary(structureProjectId);
    const chapters = await workspaceClient.chapters(
      structureProjectId,
      20,
      20,
      volumeId,
    );
    const actions = await workspaceClient.actions(structureProjectId, 0, 1);
    await workspaceClient.editorial(chapterId);
    const saved = await workspaceClient.saveEditorial(chapterId, "final", 0);
    expect(chapters.items[0].chapter_id).toBe(chapterId);
    expect(actions.next_offset).toBe(1);
    expect(saved.version).toBe(1);
    const urls = fetcher.mock.calls.map((call) => String(call[0]));
    expect(urls[0]).toContain(`/projects/${structureProjectId}/workspace`);
    expect(urls[1]).toContain(
      `workspace/chapters?offset=20&limit=20&volume_id=${volumeId}`,
    );
    expect(urls[2]).toContain("workspace/actions?offset=0&limit=1");
    expect(urls[3]).toContain(`/chapters/${chapterId}/editorial-state`);
    const put = fetcher.mock.calls[4][1] as RequestInit;
    expect(put.method).toBe("PUT");
    expect(new Headers(put.headers).get("X-CSRF-Token")).toBe("test-proof");
    expect(JSON.parse(put.body as string)).toEqual({
      status: "final",
      expected_version: 0,
    });
  });

  it("maps failures to author-facing messages without transport details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("private details")),
    );
    await expect(workspaceClient.summary(structureProjectId)).rejects.toThrow(
      "正文没有受到影响",
    );
    expect(
      workbenchError(apiError("AI_WORKFLOW_SCHEMA_REQUIRED", 503)).message,
    ).toContain("备份并启用 AI 协作");
    expect(workbenchError(apiError("SOMETHING", 500)).message).toContain(
      "稍后重试",
    );
    expect(workbenchError(apiError("INVALID_RESPONSE", 200)).code).toBe(
      "INVALID_RESPONSE",
    );
    const own = new WorkbenchError("x", "X");
    expect(workbenchError(own)).toBe(own);
    const clear = vi.spyOn(securitySession, "clear");
    workbenchError(apiError("SESSION", 401));
    expect(clear).toHaveBeenCalledOnce();
    await expect(workspaceClient.editorial("../escape")).rejects.toThrow(
      "无法安全读取",
    );
  });
});

function renderPanel(client: WorkspaceClient, compact = false) {
  return render(
    <MemoryRouter>
      <WorkspaceSummaryPanel
        projectId={structureProjectId}
        client={client}
        compact={compact}
      />
    </MemoryRouter>,
  );
}

describe("workspace summary panel", () => {
  it("shows real totals, volume counts and linked to-dos, and pages chapters on demand", async () => {
    const client = fakeClient();
    renderPanel(client);
    expect(screen.getByText("正在读取写作进度…")).toBeInTheDocument();
    expect(await screen.findByTestId("workspace-characters")).toHaveTextContent(
      "12,345 字",
    );
    expect(screen.getByTestId("workspace-action-total")).toHaveTextContent(
      "3 项",
    );
    expect(screen.getByText(/第1卷 · 第一卷：2 章/)).toBeInTheDocument();
    const todo = screen.getByRole("region", { name: "待处理事项" });
    expect(
      within(todo).getByRole("link", { name: "第1章 · 雨夜" }),
    ).toHaveAttribute(
      "href",
      `/projects/${structureProjectId}/chapters/${chapterId}/write`,
    );
    expect(within(todo).getByText("未处理的 AI 候选 ×2")).toBeInTheDocument();
    expect(client.chapters).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "查看各章字数与状态" }));
    expect(
      await screen.findByRole("cell", { name: "12,000" }),
    ).toBeInTheDocument();
    expect(screen.getByText("定稿（之后有修改）")).toBeInTheDocument();
    expect(client.chapters).toHaveBeenCalledWith(structureProjectId, 0, 20);
  });

  it("loads more to-dos and chapters, reports page errors and retries", async () => {
    const actions = vi
      .fn()
      .mockResolvedValueOnce({
        total: 2,
        offset: 0,
        next_offset: 1,
        items: [parseActionItem(rawAction())],
      })
      .mockRejectedValueOnce(apiError("SOMETHING", 500))
      .mockResolvedValueOnce({
        total: 2,
        offset: 1,
        next_offset: null,
        items: [
          parseActionItem(
            rawAction({ kind: "pending_fact", chapter_id: secondChapterId }),
          ),
        ],
      });
    const chapters = vi
      .fn()
      .mockResolvedValueOnce({
        total: 2,
        offset: 0,
        next_offset: 1,
        items: [parseChapterSummary(rawChapter())],
      })
      .mockRejectedValueOnce(apiError("SOMETHING", 500))
      .mockResolvedValueOnce({
        total: 2,
        offset: 1,
        next_offset: null,
        items: [
          parseChapterSummary(
            rawChapter({
              chapter_id: secondChapterId,
              title: "晨光",
              position: 2,
              content_changed_since_editorial: false,
              editorial_status: "draft",
            }),
          ),
        ],
      });
    renderPanel(fakeClient({ actions, chapters }));
    const more = await screen.findByRole("button", { name: "显示更多待处理" });
    fireEvent.click(more);
    expect(await screen.findByText(/稍后重试/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "显示更多待处理" }));
    expect(await screen.findByText("待确认事实")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "显示更多待处理" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "查看各章字数与状态" }));
    fireEvent.click(
      await screen.findByRole("button", {
        name: /加载更多章节（已显示 1\/2）/,
      }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "重试" }));
    expect(
      await screen.findByRole("link", { name: "第2章 · 晨光" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /加载更多章节/ })).toBeNull();
  });

  it("states empty projects and empty to-do lists without invented numbers", async () => {
    const client = fakeClient({
      summary: vi.fn().mockResolvedValue(
        parseWorkspaceSummary(
          rawSummary({
            characters: 0,
            chapter_count: 0,
            volume_count: 0,
            volumes: [],
            latest_chapter: null,
            actions: [],
            action_total: 0,
            editorial: { draft: 0, review: 0, final: 0 },
          }),
          structureProjectId,
        ),
      ),
      actions: vi.fn().mockResolvedValue({
        total: 0,
        offset: 0,
        next_offset: null,
        items: [],
      }),
      chapters: vi.fn().mockResolvedValue({
        total: 0,
        offset: 0,
        next_offset: null,
        items: [],
      }),
    });
    renderPanel(client);
    expect(
      await screen.findByText("目前没有需要处理的事项。"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("workspace-characters")).toHaveTextContent(
      "0 字",
    );
    expect(screen.queryByRole("list", { name: "各卷字数" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "查看各章字数与状态" }));
    expect(await screen.findByText("还没有章节。")).toBeInTheDocument();
  });

  it("keeps failures local with a retry, and compact mode links to the full list", async () => {
    const summary = vi
      .fn()
      .mockRejectedValueOnce(apiError("AI_WORKFLOW_SCHEMA_REQUIRED", 503))
      .mockResolvedValue(
        parseWorkspaceSummary(rawSummary(), structureProjectId),
      );
    const actions = vi.fn().mockResolvedValue({
      total: 7,
      offset: 0,
      next_offset: 5,
      items: [parseActionItem(rawAction())],
    });
    renderPanel(fakeClient({ summary, actions }), true);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "备份并启用 AI 协作",
    );
    fireEvent.click(screen.getByRole("button", { name: "重新读取汇总" }));
    expect(
      await screen.findByRole("link", { name: "查看全部 7 处" }),
    ).toHaveAttribute("href", `/projects/${structureProjectId}/structure`);
    expect(
      screen.queryByRole("button", { name: "查看各章字数与状态" }),
    ).toBeNull();
    expect(actions).toHaveBeenLastCalledWith(structureProjectId, 0, 5);
    fireEvent.click(screen.getByRole("button", { name: "刷新汇总" }));
    await waitFor(() => expect(summary).toHaveBeenCalledTimes(3));
  });

  it("ignores results after unmount", async () => {
    let resolve: (value: unknown) => void = () => undefined;
    const summary = vi.fn().mockReturnValue(new Promise((r) => (resolve = r)));
    const { unmount } = renderPanel(fakeClient({ summary }));
    await waitFor(() => expect(summary).toHaveBeenCalled());
    unmount();
    await act(async () => {
      resolve(parseWorkspaceSummary(rawSummary(), structureProjectId));
      await Promise.resolve();
    });
  });
});

function renderControl(
  client: WorkspaceClient,
  flush = vi.fn().mockResolvedValue(true),
  revision = "chv_1",
) {
  render(
    <EditorialStatusControl
      chapterId={chapterId}
      savedRevisionId={revision}
      flush={flush}
      client={client}
    />,
  );
  return flush;
}

describe("editorial status control", () => {
  it("saves the author's choice against the saved text and never changes it on its own", async () => {
    const saveEditorial = vi.fn().mockResolvedValue(
      editorialState({
        status: "review",
        version: 1,
        chapter_revision_id: "chv_1",
      }),
    );
    const client = fakeClient({ saveEditorial });
    const flush = renderControl(client);
    const select = await screen.findByLabelText("章节状态");
    expect(select).toHaveValue("draft");
    expect(saveEditorial).not.toHaveBeenCalled();
    fireEvent.change(select, { target: { value: "review" } });
    expect(await screen.findByText("已标记为“待检查”。")).toBeInTheDocument();
    expect(flush).toHaveBeenCalledOnce();
    expect(saveEditorial).toHaveBeenCalledWith(chapterId, "review", 0);
    expect(screen.getByLabelText("章节状态")).toHaveValue("review");
  });

  it("asks before marking a chapter with open to-dos as final", async () => {
    const saveEditorial = vi.fn().mockResolvedValue(
      editorialState({
        status: "final",
        version: 1,
        chapter_revision_id: "chv_1",
      }),
    );
    const client = fakeClient({
      editorial: vi.fn().mockResolvedValue(editorialState({ open_actions: 2 })),
      saveEditorial,
    });
    renderControl(client);
    fireEvent.change(await screen.findByLabelText("章节状态"), {
      target: { value: "final" },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("本章还有 2 项待处理");
    fireEvent.click(screen.getByRole("button", { name: "暂不标记" }));
    expect(saveEditorial).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("章节状态"), {
      target: { value: "final" },
    });
    fireEvent.click(screen.getByRole("button", { name: "仍标为定稿" }));
    expect(await screen.findByText("已标记为“定稿”。")).toBeInTheDocument();
    expect(saveEditorial).toHaveBeenCalledWith(chapterId, "final", 0);
  });

  it("does not mark when the manuscript cannot be saved and reloads after conflicts", async () => {
    const saveEditorial = vi
      .fn()
      .mockRejectedValue(apiError("EDITORIAL_CONFLICT"));
    const editorial = vi
      .fn()
      .mockResolvedValueOnce(editorialState())
      .mockResolvedValue(
        editorialState({
          status: "final",
          version: 3,
          chapter_revision_id: "chv_1",
        }),
      );
    const flush = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true);
    renderControl(fakeClient({ editorial, saveEditorial }), flush);
    fireEvent.change(await screen.findByLabelText("章节状态"), {
      target: { value: "review" },
    });
    expect(await screen.findByText(/正文尚未保存/)).toBeInTheDocument();
    expect(saveEditorial).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("章节状态"), {
      target: { value: "review" },
    });
    await waitFor(() => expect(editorial).toHaveBeenCalledTimes(2));
    expect(await screen.findByLabelText("章节状态")).toHaveValue("final");
    expect(screen.getByText(/其他窗口修改/)).toBeInTheDocument();
  });

  it("shows when the saved text changed after marking and re-marks on request", async () => {
    const saveEditorial = vi.fn().mockResolvedValue(
      editorialState({
        status: "final",
        version: 2,
        chapter_revision_id: "chv_2",
      }),
    );
    const client = fakeClient({
      editorial: vi.fn().mockResolvedValue(
        editorialState({
          status: "final",
          version: 1,
          chapter_revision_id: "chv_1",
          content_changed: true,
        }),
      ),
      saveEditorial,
    });
    renderControl(client, vi.fn().mockResolvedValue(true), "chv_2");
    expect(await screen.findByText(/标记后正文已修改/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("章节状态"), {
      target: { value: "final" },
    });
    fireEvent.click(screen.getByRole("button", { name: "按当前正文重新标记" }));
    expect(await screen.findByText("已标记为“定稿”。")).toBeInTheDocument();
    expect(saveEditorial).toHaveBeenCalledWith(chapterId, "final", 1);
    expect(screen.queryByText(/标记后正文已修改/)).toBeNull();
  });

  it("keeps load failures local and retries", async () => {
    const editorial = vi
      .fn()
      .mockRejectedValueOnce(apiError("SOMETHING", 500))
      .mockResolvedValue(editorialState());
    renderControl(fakeClient({ editorial }));
    expect(await screen.findByRole("alert")).toHaveTextContent("章节状态");
    fireEvent.click(screen.getByRole("button", { name: "重新读取状态" }));
    expect(await screen.findByLabelText("章节状态")).toHaveValue("draft");
  });
});

describe("workspace edge states", () => {
  it("rejects pages for another project", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ ...page([], 0, null), project_id: "prj_other" }),
        ),
    );
    await expect(
      workspaceClient.actions(structureProjectId, 0, 10),
    ).rejects.toThrow("无法安全读取");
  });

  it("drops late failures after unmount and hides the compact link when all to-dos fit", async () => {
    let reject: (reason: unknown) => void = () => undefined;
    const summary = vi
      .fn()
      .mockReturnValue(new Promise((_, r) => (reject = r)));
    const first = renderPanel(fakeClient({ summary }));
    await waitFor(() => expect(summary).toHaveBeenCalled());
    first.unmount();
    await act(async () => {
      reject(apiError("SOMETHING", 500));
      await Promise.resolve();
    });
    renderPanel(fakeClient(), true);
    expect(await screen.findByText("未处理的 AI 候选 ×2")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /查看全部/ })).toBeNull();
  });

  it("reports non-conflict save failures without reloading and ignores late loads", async () => {
    const saveEditorial = vi.fn().mockRejectedValue(apiError("SOMETHING", 500));
    const editorial = vi.fn().mockResolvedValue(editorialState());
    renderControl(fakeClient({ editorial, saveEditorial }));
    fireEvent.change(await screen.findByLabelText("章节状态"), {
      target: { value: "final" },
    });
    expect(await screen.findByText(/稍后重试/)).toBeInTheDocument();
    expect(editorial).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("章节状态")).toHaveValue("draft");

    let resolve: (value: EditorialState) => void = () => undefined;
    let fail: (reason: unknown) => void = () => undefined;
    const late = vi
      .fn()
      .mockReturnValueOnce(new Promise((r) => (resolve = r)))
      .mockReturnValueOnce(new Promise((_, r) => (fail = r)));
    const view = render(
      <EditorialStatusControl
        chapterId={chapterId}
        savedRevisionId="chv_1"
        flush={vi.fn()}
        client={fakeClient({ editorial: late })}
      />,
    );
    await waitFor(() => expect(late).toHaveBeenCalledOnce());
    view.unmount();
    await act(async () => {
      resolve(editorialState());
      await Promise.resolve();
    });
    const second = render(
      <EditorialStatusControl
        chapterId={chapterId}
        savedRevisionId="chv_1"
        flush={vi.fn()}
        client={fakeClient({ editorial: late })}
      />,
    );
    await waitFor(() => expect(late).toHaveBeenCalledTimes(2));
    second.unmount();
    await act(async () => {
      fail(apiError("SOMETHING", 500));
      await Promise.resolve();
    });
  });
});

it("re-reads the derived summary when the page reports a structure change", async () => {
  const client = fakeClient();
  const view = render(
    <MemoryRouter>
      <WorkspaceSummaryPanel projectId={structureProjectId} client={client} />
    </MemoryRouter>,
  );
  await screen.findByTestId("workspace-characters");
  view.rerender(
    <MemoryRouter>
      <WorkspaceSummaryPanel
        projectId={structureProjectId}
        client={client}
        refreshKey={1}
      />
    </MemoryRouter>,
  );
  await waitFor(() => expect(client.summary).toHaveBeenCalledTimes(2));
});
