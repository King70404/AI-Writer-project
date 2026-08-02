import {
  act,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  type GetStoryBibleForProjectOptions,
  type ListStoryBibleRevisionsOptions,
  storyBibleRevisionHistoryApiClient,
  type StoryBibleRevisionHistoryApiClient,
} from "../../frontend/src/features/story-bible/api/client";
import type {
  StoryBibleRevisionHistoryPageResponse,
  StoryBibleRevisionResponse,
} from "../../frontend/src/features/story-bible/api/contracts";
import {
  StoryBibleRevisionHistoryList,
  StoryBibleRevisionHistoryStatus,
  StoryBibleRevisionViewer,
} from "../../frontend/src/features/story-bible/components/StoryBibleRevisionHistory";
import { useStoryBibleRevisionHistory } from "../../frontend/src/features/story-bible/hooks/useStoryBibleRevisionHistory";
import { StoryBibleApiError } from "../../frontend/src/features/story-bible/api/errors";
import {
  parseStoryBibleRevisionHistoryPageResponse,
  parseStoryBibleRevisionResponse,
  StoryBibleContractError,
} from "../../frontend/src/features/story-bible/api/parsers";
import { StoryBibleRevisionHistoryPage } from "../../frontend/src/features/story-bible/pages/StoryBibleRevisionHistoryPage";
import {
  storyBibleClient,
  storyBibleError,
  storyBibleErrorEnvelope,
  storyBibleId,
  storyBibleJsonResponse,
  storyProjectId,
  storyTimestamp,
} from "./story-bible-support";

const revisionIds = [
  "sbr_01ARZ3NDEKTSV4RRFFQ69G5FAX",
  "sbr_01ARZ3NDEKTSV4RRFFQ69G5FAW",
  "sbr_01ARZ3NDEKTSV4RRFFQ69G5FAV",
] as const;

function item(number: number, current = false) {
  return {
    revision_id: revisionIds[3 - number],
    revision_number: number,
    title: `设定修订 ${number}`,
    created_at: storyTimestamp,
    is_current: current,
  };
}

function page(
  items = [item(3, true), item(2)],
  overrides: Partial<StoryBibleRevisionHistoryPageResponse> = {},
): StoryBibleRevisionHistoryPageResponse {
  return {
    story_bible_id: storyBibleId,
    project_id: storyProjectId,
    current_revision_number: 3,
    items,
    next_cursor: "opaque-next",
    has_more: true,
    ...overrides,
  };
}

function revision(number: number): StoryBibleRevisionResponse {
  return {
    story_bible_id: storyBibleId,
    project_id: storyProjectId,
    revision_id: revisionIds[3 - number],
    revision_number: number,
    title: `设定修订 ${number}`,
    content: `只读正文 ${number}`,
    created_at: storyTimestamp,
    is_current: number === 3,
    current_revision_number: 3,
  };
}

function historyClient(
  listStoryBibleRevisions = vi.fn().mockResolvedValue(page()),
  getStoryBibleRevision = vi
    .fn()
    .mockImplementation(
      ({ revisionNumber }: { readonly revisionNumber: number }) =>
        Promise.resolve(revision(revisionNumber)),
    ),
): StoryBibleRevisionHistoryApiClient {
  return { listStoryBibleRevisions, getStoryBibleRevision };
}

function renderHistory(client: StoryBibleRevisionHistoryApiClient) {
  return render(
    <MemoryRouter
      initialEntries={[`/projects/${storyProjectId}/story-bible/history`]}
    >
      <Routes>
        <Route
          path="/projects/:projectId/story-bible/history"
          element={
            <StoryBibleRevisionHistoryPage
              currentClient={storyBibleClient()}
              historyClient={client}
            />
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Story Bible revision history contracts and page", () => {
  it("strictly parses list and exact revision contracts", () => {
    expect(
      parseStoryBibleRevisionHistoryPageResponse(
        page(),
        storyBibleId,
        storyProjectId,
      ).items,
    ).toHaveLength(2);
    expect(
      parseStoryBibleRevisionResponse(
        revision(1),
        storyBibleId,
        storyProjectId,
        1,
      ).content,
    ).toBe("只读正文 1");
    expect(() =>
      parseStoryBibleRevisionHistoryPageResponse(
        { ...page(), extra: true },
        storyBibleId,
        storyProjectId,
      ),
    ).toThrow(StoryBibleContractError);
    expect(() =>
      parseStoryBibleRevisionHistoryPageResponse(
        page([item(2), item(3, true)]),
        storyBibleId,
        storyProjectId,
      ),
    ).toThrow(StoryBibleContractError);
    expect(() =>
      parseStoryBibleRevisionResponse(
        { ...revision(1), is_current: true },
        storyBibleId,
        storyProjectId,
        1,
      ),
    ).toThrow(StoryBibleContractError);
  });

  it("loads identity then summaries and fetches body only after selection", async () => {
    const user = userEvent.setup();
    const list = vi.fn().mockResolvedValue(page());
    const get = vi.fn().mockResolvedValue(revision(2));
    const current = storyBibleClient();
    render(
      <MemoryRouter
        initialEntries={[`/projects/${storyProjectId}/story-bible/history`]}
      >
        <Routes>
          <Route
            path="/projects/:projectId/story-bible/history"
            element={
              <StoryBibleRevisionHistoryPage
                currentClient={current}
                historyClient={historyClient(list, get)}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("设定修订 3")).toBeVisible();
    expect(current.getStoryBibleForProject).toHaveBeenCalledOnce();
    expect(list).toHaveBeenCalledWith(
      expect.objectContaining({
        storyBibleId,
        expectedProjectId: storyProjectId,
        limit: 20,
      }),
    );
    expect(get).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent("只读正文 2");
    await user.click(screen.getAllByRole("button", { name: "查看正文" })[1]);
    expect(await screen.findByText("只读正文 2")).toBeVisible();
    expect(get).toHaveBeenCalledWith(
      expect.objectContaining({ storyBibleId, revisionNumber: 2 }),
    );
    expect(document.body).not.toHaveTextContent(/回滚|恢复|采用|删除|Diff/u);
  });

  it("uses the opaque cursor and preserves rows across paging", async () => {
    const user = userEvent.setup();
    const list = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(
        page([item(1)], { next_cursor: null, has_more: false }),
      );
    renderHistory(historyClient(list));
    await screen.findByText("设定修订 3");
    await user.click(screen.getByRole("button", { name: "加载更多" }));
    expect(await screen.findByText("设定修订 1")).toBeVisible();
    expect(list).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: "opaque-next" }),
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("aborts an older selected revision and ignores its late result", async () => {
    const user = userEvent.setup();
    let resolveTwo!: (value: StoryBibleRevisionResponse) => void;
    let resolveThree!: (value: StoryBibleRevisionResponse) => void;
    const two = new Promise<StoryBibleRevisionResponse>(
      (resolve) => (resolveTwo = resolve),
    );
    const three = new Promise<StoryBibleRevisionResponse>(
      (resolve) => (resolveThree = resolve),
    );
    const signals: AbortSignal[] = [];
    const get = vi.fn(
      ({
        revisionNumber,
        signal,
      }: {
        revisionNumber: number;
        signal?: AbortSignal;
      }) => {
        if (signal !== undefined) signals.push(signal);
        return revisionNumber === 2 ? two : three;
      },
    );
    renderHistory(historyClient(vi.fn().mockResolvedValue(page()), get));
    await screen.findByText("设定修订 3");
    const buttons = screen.getAllByRole("button", { name: "查看正文" });
    await user.click(buttons[1]);
    await user.click(buttons[0]);
    expect(signals[0]?.aborted).toBe(true);
    resolveThree(revision(3));
    expect(await screen.findByText("只读正文 3")).toBeVisible();
    resolveTwo(revision(2));
    await waitFor(() =>
      expect(screen.queryByText("只读正文 2")).not.toBeInTheDocument(),
    );
  });

  it("GET client encodes cursor and sends no write security headers", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(storyBibleJsonResponse(page()));
    vi.stubGlobal("fetch", fetchMock);
    await storyBibleRevisionHistoryApiClient.listStoryBibleRevisions({
      storyBibleId,
      expectedProjectId: storyProjectId,
      limit: 20,
      cursor: "opaque+/=cursor",
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `/api/v1/story-bibles/${storyBibleId}/revisions?limit=20&cursor=opaque%2B%2F%3Dcursor`,
    );
    expect(init?.method).toBe("GET");
    expect(init).not.toHaveProperty("body");
    expect(new Headers(init?.headers).has("X-CSRF-Token")).toBe(false);
    expect(new Headers(init?.headers).has("If-Match")).toBe(false);
  });

  it.each([
    { storyBibleId: "bad", expectedProjectId: storyProjectId, limit: 20 },
    { storyBibleId, expectedProjectId: "bad", limit: 20 },
    { storyBibleId, expectedProjectId: storyProjectId, limit: 0 },
    { storyBibleId, expectedProjectId: storyProjectId, limit: 101 },
    {
      storyBibleId,
      expectedProjectId: storyProjectId,
      limit: 20,
      cursor: "",
    },
  ])("rejects malformed list input before fetch %#", async (options) => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      storyBibleRevisionHistoryApiClient.listStoryBibleRevisions(options),
    ).rejects.toMatchObject({ kind: "validation" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uses the exact revision GET path and safely normalizes a revision 404", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(storyBibleJsonResponse(revision(1)))
      .mockResolvedValueOnce(
        storyBibleJsonResponse(
          storyBibleErrorEnvelope("STORY_BIBLE_REVISION_NOT_FOUND"),
          { status: 404 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      storyBibleRevisionHistoryApiClient.getStoryBibleRevision({
        storyBibleId,
        expectedProjectId: storyProjectId,
        revisionNumber: 1,
      }),
    ).resolves.toEqual(revision(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/v1/story-bibles/${storyBibleId}/revisions/1`,
    );
    await expect(
      storyBibleRevisionHistoryApiClient.getStoryBibleRevision({
        storyBibleId,
        expectedProjectId: storyProjectId,
        revisionNumber: 99,
      }),
    ).rejects.toMatchObject({ kind: "story_bible_revision_not_found" });
    await expect(
      storyBibleRevisionHistoryApiClient.getStoryBibleRevision({
        storyBibleId,
        expectedProjectId: storyProjectId,
        revisionNumber: 0,
      }),
    ).rejects.toMatchObject({ kind: "validation" });
    expect(JSON.stringify(fetchMock.mock.results)).not.toContain(
      "STORY_BIBLE_FRONTEND_SECRET_CANARY",
    );
  });

  it.each([
    page([item(3, true), { ...item(2), revision_id: revisionIds[0] }]),
    page([item(3, true), { ...item(2), revision_number: 3 }]),
    page([], { has_more: true, next_cursor: "opaque" }),
    page(undefined, { has_more: false, next_cursor: "opaque" }),
    page(undefined, { story_bible_id: "sbl_01ARZ3NDEKTSV4RRFFQ69G5FAW" }),
    page(undefined, { project_id: "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW" }),
  ])("rejects malformed list ownership, identity, or paging %#", (value) => {
    expect(() =>
      parseStoryBibleRevisionHistoryPageResponse(
        value,
        storyBibleId,
        storyProjectId,
      ),
    ).toThrow(StoryBibleContractError);
  });

  it("represents all status, list, and viewer accessibility states", async () => {
    const user = userEvent.setup();
    const retryHistory = vi.fn();
    const retryViewer = vi.fn();
    const select = vi.fn();
    const loadMore = vi.fn();
    const safeError = new StoryBibleApiError({
      kind: "unknown",
      code: "SAFE",
      message: "safe message",
      requestId: "req-safe",
    });
    const { rerender } = render(
      <StoryBibleRevisionHistoryStatus kind="loading" />,
    );
    expect(screen.getByRole("status")).toBeVisible();
    rerender(<StoryBibleRevisionHistoryStatus kind="invalid" />);
    expect(screen.getByRole("alert")).toBeVisible();
    rerender(
      <StoryBibleRevisionHistoryStatus kind="not_found" error={safeError} />,
    );
    expect(screen.getByText(/req-safe/u)).toBeVisible();
    rerender(
      <StoryBibleRevisionHistoryStatus
        kind="error"
        error={safeError}
        onRetry={retryHistory}
      />,
    );
    await user.click(screen.getByRole("button"));
    expect(retryHistory).toHaveBeenCalledOnce();

    rerender(
      <StoryBibleRevisionHistoryList
        items={[item(3, true)]}
        selectedRevisionNumber={3}
        hasMore={false}
        loadMoreStatus="idle"
        loadMoreError={null}
        onSelect={select}
        onLoadMore={loadMore}
      />,
    );
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button"));
    expect(select).toHaveBeenCalledWith(3);
    rerender(
      <StoryBibleRevisionHistoryList
        items={[item(3, true)]}
        selectedRevisionNumber={null}
        hasMore
        loadMoreStatus="error"
        loadMoreError={safeError}
        onSelect={select}
        onLoadMore={loadMore}
      />,
    );
    await user.click(screen.getByRole("button", { name: /重试|閲嶈瘯/u }));
    expect(loadMore).toHaveBeenCalledOnce();
    rerender(
      <StoryBibleRevisionHistoryList
        items={[item(3, true)]}
        selectedRevisionNumber={null}
        hasMore
        loadMoreStatus="loading"
        loadMoreError={null}
        onSelect={select}
        onLoadMore={loadMore}
      />,
    );
    expect(screen.getAllByRole("button")[1]).toBeDisabled();

    rerender(
      <StoryBibleRevisionViewer
        state={{ status: "loading", revisionNumber: 2 }}
        onRetry={retryViewer}
      />,
    );
    expect(screen.getByRole("status")).toBeVisible();
    rerender(
      <StoryBibleRevisionViewer
        state={{ status: "error", revisionNumber: 2, error: safeError }}
        onRetry={retryViewer}
      />,
    );
    await user.click(screen.getByRole("button"));
    expect(retryViewer).toHaveBeenCalledOnce();
    rerender(
      <StoryBibleRevisionViewer
        state={{ status: "ready", revisionNumber: 3, revision: revision(3) }}
        onRetry={retryViewer}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 3 })).toHaveFocus(),
    );
  });

  it("distinguishes invalid, not-found, and retryable initial failures", async () => {
    const invalidCurrent = storyBibleClient();
    const invalidHistory = historyClient();
    const invalid = renderHook(() =>
      useStoryBibleRevisionHistory("bad", invalidCurrent, invalidHistory),
    );
    expect(invalid.result.current.history.status).toBe("invalid");
    await act(async () => {
      expect(await invalid.result.current.reload()).toBe(false);
    });
    expect(invalidCurrent.getStoryBibleForProject).not.toHaveBeenCalled();
    invalid.unmount();

    const missingCurrent = storyBibleClient({
      getStoryBibleForProject: vi
        .fn()
        .mockRejectedValue(storyBibleError("project_not_found")),
    });
    const missingHistory = historyClient();
    const missing = renderHook(() =>
      useStoryBibleRevisionHistory(
        storyProjectId,
        missingCurrent,
        missingHistory,
      ),
    );
    await waitFor(() =>
      expect(missing.result.current.history.status).toBe("not_found"),
    );
    missing.unmount();

    const list = vi
      .fn()
      .mockRejectedValueOnce(storyBibleError("unknown"))
      .mockResolvedValueOnce(page());
    const retryCurrent = storyBibleClient();
    const retryHistory = historyClient(list);
    const failure = renderHook(() =>
      useStoryBibleRevisionHistory(storyProjectId, retryCurrent, retryHistory),
    );
    await waitFor(() =>
      expect(failure.result.current.history.status).toBe("error"),
    );
    await act(async () => {
      expect(await failure.result.current.reload()).toBe(true);
    });
    expect(failure.result.current.history.status).toBe("ready");
    failure.unmount();
  });

  it("retains loaded rows on load-more failure and retries the same cursor", async () => {
    const list = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockRejectedValueOnce(storyBibleError("network"))
      .mockResolvedValueOnce(
        page([item(1)], { has_more: false, next_cursor: null }),
      );
    const current = storyBibleClient();
    const history = historyClient(list);
    const hook = renderHook(() =>
      useStoryBibleRevisionHistory(storyProjectId, current, history),
    );
    await waitFor(() =>
      expect(hook.result.current.history.status).toBe("ready"),
    );
    await act(async () => {
      await hook.result.current.loadMore();
    });
    expect(hook.result.current.history.items).toHaveLength(2);
    expect(hook.result.current.history.loadMoreStatus).toBe("error");
    await act(async () => {
      await hook.result.current.loadMore();
    });
    expect(hook.result.current.history.items).toHaveLength(3);
    expect(
      (list.mock.calls[1]?.[0] as ListStoryBibleRevisionsOptions | undefined)
        ?.cursor,
    ).toBe("opaque-next");
    expect(
      (list.mock.calls[2]?.[0] as ListStoryBibleRevisionsOptions | undefined)
        ?.cursor,
    ).toBe("opaque-next");
    await act(async () => {
      await hook.result.current.loadMore();
      await hook.result.current.selectRevision(0);
    });
    expect(list).toHaveBeenCalledTimes(3);
    hook.unmount();
  });

  it("rejects duplicate later pages and supports selected revision retry", async () => {
    const list = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(
        page([{ ...item(1), revision_id: revisionIds[0] }], {
          has_more: false,
          next_cursor: null,
        }),
      );
    const get = vi
      .fn()
      .mockRejectedValueOnce(storyBibleError("unknown"))
      .mockResolvedValueOnce(revision(2));
    const current = storyBibleClient();
    const history = historyClient(list, get);
    const hook = renderHook(() =>
      useStoryBibleRevisionHistory(storyProjectId, current, history),
    );
    await waitFor(() =>
      expect(hook.result.current.history.status).toBe("ready"),
    );
    await act(async () => {
      await hook.result.current.loadMore();
    });
    expect(hook.result.current.history.loadMoreStatus).toBe("error");
    await act(async () => {
      await hook.result.current.selectRevision(2);
    });
    expect(hook.result.current.viewer.status).toBe("error");
    await act(async () => {
      await hook.result.current.retrySelectedRevision();
    });
    expect(hook.result.current.viewer.status).toBe("ready");
    hook.unmount();
  });

  it("aborts initial history work when unmounted", async () => {
    let capturedSignal: AbortSignal | undefined;
    const pending = new Promise<never>(() => undefined);
    const current = storyBibleClient({
      getStoryBibleForProject: vi.fn(
        ({ signal }: GetStoryBibleForProjectOptions) => {
          capturedSignal = signal;
          return pending;
        },
      ),
    });
    const history = historyClient();
    const hook = renderHook(() =>
      useStoryBibleRevisionHistory(storyProjectId, current, history),
    );
    await waitFor(() => expect(capturedSignal).toBeDefined());
    hook.unmount();
    expect(capturedSignal?.aborted).toBe(true);
  });

  it("retries initial and selected failures through page controls", async () => {
    const user = userEvent.setup();
    const list = vi
      .fn()
      .mockRejectedValueOnce(storyBibleError("unknown"))
      .mockResolvedValueOnce(page());
    const get = vi
      .fn()
      .mockRejectedValueOnce(storyBibleError("unknown"))
      .mockResolvedValueOnce(revision(2));
    renderHistory(historyClient(list, get));
    expect(await screen.findByRole("alert")).toBeVisible();
    await user.click(screen.getByRole("button"));
    expect(await screen.findByRole("list")).toBeVisible();
    await user.click(
      screen.getAllByRole("button", { name: /查看正文|鏌ョ湅姝ｆ枃/u })[1],
    );
    expect(await screen.findByRole("alert")).toBeVisible();
    await user.click(screen.getByRole("button", { name: /重试|閲嶈瘯/u }));
    expect(
      await screen.findByRole("heading", { level: 3, name: /：/u }),
    ).toHaveFocus();
  });

  it("renders a missing route parameter without requesting data", async () => {
    render(
      <MemoryRouter initialEntries={["/missing-project"]}>
        <Routes>
          <Route
            path="/missing-project"
            element={<StoryBibleRevisionHistoryPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/projects");
  });
});
