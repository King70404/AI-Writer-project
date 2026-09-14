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
  type ListCharacterRevisionsOptions,
  characterRevisionHistoryApiClient,
  type CharacterRevisionHistoryApiClient,
} from "../../frontend/src/features/character/api/history";
import type {
  CharacterRevisionHistoryPageResponse,
  CharacterRevisionResponse,
} from "../../frontend/src/features/character/api/contracts";
import {
  CharacterRevisionHistoryList,
  CharacterRevisionHistoryStatus,
} from "../../frontend/src/features/character/components/CharacterRevisionHistory";
import { CharacterRevisionViewer } from "../../frontend/src/features/character/components/CharacterRevisionViewer";
import { useCharacterRevisionHistory } from "../../frontend/src/features/character/hooks/useCharacterRevisionHistory";
import { CharacterApiError } from "../../frontend/src/features/character/api/errors";
import {
  parseCharacterRevisionHistoryPageResponse,
  parseCharacterRevisionResponse,
  CharacterContractError,
} from "../../frontend/src/features/character/api/parsers";
import { CharacterRevisionHistoryPage } from "../../frontend/src/features/character/pages/CharacterRevisionHistoryPage";
import {
  characterError,
  characterErrorEnvelope,
  characterId,
  characterJsonResponse,
  characterProjectId,
  characterTimestamp,
} from "./character-support";

const revisionIds = [
  "crv_01ARZ3NDEKTSV4RRFFQ69G5FAX",
  "crv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
  "crv_01ARZ3NDEKTSV4RRFFQ69G5FAV",
] as const;

function item(number: number, current = false) {
  return {
    revision_id: revisionIds[3 - number],
    revision_number: number,
    name: `设定修订 ${number}`,
    role: "主角",
    created_at: characterTimestamp,
    is_current: current,
  };
}

function page(
  items = [item(3, true), item(2)],
  overrides: Partial<CharacterRevisionHistoryPageResponse> = {},
): CharacterRevisionHistoryPageResponse {
  return {
    character_id: characterId,
    project_id: characterProjectId,
    current_revision_number: 3,
    items,
    next_cursor: "opaque-next",
    has_more: true,
    ...overrides,
  };
}

function revision(number: number): CharacterRevisionResponse {
  return {
    character_id: characterId,
    project_id: characterProjectId,
    revision_id: revisionIds[3 - number],
    revision_number: number,
    name: `设定修订 ${number}`,
    role: "主角",
    profile: `只读正文 ${number}`,
    created_at: characterTimestamp,
    is_current: number === 3,
    current_revision_number: 3,
  };
}

function historyClient(
  listCharacterRevisions = vi.fn().mockResolvedValue(page()),
  getCharacterRevision = vi
    .fn()
    .mockImplementation(
      ({ revisionNumber }: { readonly revisionNumber: number }) =>
        Promise.resolve(revision(revisionNumber)),
    ),
): CharacterRevisionHistoryApiClient {
  return { listCharacterRevisions, getCharacterRevision };
}

function renderHistory(client: CharacterRevisionHistoryApiClient) {
  return render(
    <MemoryRouter
      initialEntries={[
        `/projects/${characterProjectId}/characters/${characterId}/history`,
      ]}
    >
      <Routes>
        <Route
          path="/projects/:projectId/characters/:characterId/history"
          element={<CharacterRevisionHistoryPage client={client} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Character revision history contracts and page", () => {
  it("strictly parses list and exact revision contracts", () => {
    expect(
      parseCharacterRevisionHistoryPageResponse(
        page(),
        characterId,
        characterProjectId,
      ).items,
    ).toHaveLength(2);
    expect(
      parseCharacterRevisionResponse(
        revision(1),
        characterId,
        characterProjectId,
        1,
      ).profile,
    ).toBe("只读正文 1");
    expect(() =>
      parseCharacterRevisionHistoryPageResponse(
        { ...page(), extra: true },
        characterId,
        characterProjectId,
      ),
    ).toThrow(CharacterContractError);
    expect(() =>
      parseCharacterRevisionHistoryPageResponse(
        page([item(2), item(3, true)]),
        characterId,
        characterProjectId,
      ),
    ).toThrow(CharacterContractError);
    expect(() =>
      parseCharacterRevisionResponse(
        { ...revision(1), is_current: true },
        characterId,
        characterProjectId,
        1,
      ),
    ).toThrow(CharacterContractError);
  });

  it("loads summaries once and fetches profile only after selection", async () => {
    const user = userEvent.setup();
    const list = vi.fn().mockResolvedValue(page());
    const get = vi.fn().mockResolvedValue(revision(2));
    renderHistory(historyClient(list, get));

    expect(await screen.findByText("设定修订 3")).toBeVisible();
    expect(screen.getByRole("link", { name: "返回当前角色" })).toHaveAttribute(
      "href",
      `/projects/${characterProjectId}/characters/${characterId}`,
    );
    for (const id of [characterId, characterProjectId, ...revisionIds])
      expect(document.body).not.toHaveTextContent(id);
    expect(list).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        characterId,
        expectedProjectId: characterProjectId,
        limit: 20,
      }),
    );
    expect(get).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent("只读正文 2");
    await user.click(screen.getAllByRole("button", { name: "查看此修订" })[1]);
    expect(await screen.findByText("只读正文 2")).toBeVisible();
    for (const id of [characterId, characterProjectId, ...revisionIds])
      expect(document.body).not.toHaveTextContent(id);
    expect(screen.getAllByRole("time").at(-1)).toHaveAttribute(
      "datetime",
      characterTimestamp,
    );
    expect(get).toHaveBeenCalledWith(
      expect.objectContaining({ characterId, revisionNumber: 2 }),
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
    let resolveTwo!: (value: CharacterRevisionResponse) => void;
    let resolveThree!: (value: CharacterRevisionResponse) => void;
    const two = new Promise<CharacterRevisionResponse>(
      (resolve) => (resolveTwo = resolve),
    );
    const three = new Promise<CharacterRevisionResponse>(
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
    const buttons = screen.getAllByRole("button", { name: "查看此修订" });
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
      .mockResolvedValue(characterJsonResponse(page()));
    vi.stubGlobal("fetch", fetchMock);
    await characterRevisionHistoryApiClient.listCharacterRevisions({
      characterId,
      expectedProjectId: characterProjectId,
      limit: 20,
      cursor: "opaque+/=cursor",
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `/api/v1/characters/${characterId}/revisions?limit=20&cursor=opaque%2B%2F%3Dcursor`,
    );
    expect(init?.method).toBe("GET");
    expect(init).not.toHaveProperty("body");
    expect(new Headers(init?.headers).has("X-CSRF-Token")).toBe(false);
    expect(new Headers(init?.headers).has("If-Match")).toBe(false);
  });

  it("safely normalizes a rejected list request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockRejectedValue(new Error("offline")),
    );
    await expect(
      characterRevisionHistoryApiClient.listCharacterRevisions({
        characterId,
        expectedProjectId: characterProjectId,
        limit: 20,
      }),
    ).rejects.toMatchObject({ kind: "unknown" });
  });

  it.each([
    { characterId: "bad", expectedProjectId: characterProjectId, limit: 20 },
    { characterId, expectedProjectId: "bad", limit: 20 },
    { characterId, expectedProjectId: characterProjectId, limit: 0 },
    { characterId, expectedProjectId: characterProjectId, limit: 101 },
    {
      characterId,
      expectedProjectId: characterProjectId,
      limit: 20,
      cursor: "",
    },
  ])("rejects malformed list input before fetch %#", async (options) => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      characterRevisionHistoryApiClient.listCharacterRevisions(options),
    ).rejects.toMatchObject({ kind: "validation" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uses the exact revision GET path and safely normalizes a revision 404", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(characterJsonResponse(revision(1)))
      .mockResolvedValueOnce(
        characterJsonResponse(
          characterErrorEnvelope("CHARACTER_REVISION_NOT_FOUND"),
          { status: 404 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      characterRevisionHistoryApiClient.getCharacterRevision({
        characterId,
        expectedProjectId: characterProjectId,
        revisionNumber: 1,
      }),
    ).resolves.toEqual(revision(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/v1/characters/${characterId}/revisions/1`,
    );
    await expect(
      characterRevisionHistoryApiClient.getCharacterRevision({
        characterId,
        expectedProjectId: characterProjectId,
        revisionNumber: 99,
      }),
    ).rejects.toMatchObject({ kind: "character_revision_not_found" });
    await expect(
      characterRevisionHistoryApiClient.getCharacterRevision({
        characterId,
        expectedProjectId: characterProjectId,
        revisionNumber: 0,
      }),
    ).rejects.toMatchObject({ kind: "validation" });
    expect(JSON.stringify(fetchMock.mock.results)).not.toContain(
      "CHARACTER_FRONTEND_SECRET_CANARY",
    );
  });

  it.each([
    page([item(3, true), { ...item(2), revision_id: revisionIds[0] }]),
    page([item(3, true), { ...item(2), revision_number: 3 }]),
    page([], { has_more: true, next_cursor: "opaque" }),
    page(undefined, { has_more: false, next_cursor: "opaque" }),
    page(undefined, { character_id: "chr_01ARZ3NDEKTSV4RRFFQ69G5FAW" }),
    page(undefined, { project_id: "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW" }),
  ])("rejects malformed list ownership, identity, or paging %#", (value) => {
    expect(() =>
      parseCharacterRevisionHistoryPageResponse(
        value,
        characterId,
        characterProjectId,
      ),
    ).toThrow(CharacterContractError);
  });

  it("represents all status, list, and viewer accessibility states", async () => {
    const user = userEvent.setup();
    const retryHistory = vi.fn();
    const retryViewer = vi.fn();
    const select = vi.fn();
    const loadMore = vi.fn();
    const safeError = new CharacterApiError({
      kind: "unknown",
      code: "SAFE",
      message: "safe message",
      requestId: "req-safe",
    });
    const { rerender } = render(
      <CharacterRevisionHistoryStatus kind="loading_history" />,
    );
    expect(screen.getByRole("status")).toBeVisible();
    rerender(<CharacterRevisionHistoryStatus kind="invalid_route" />);
    expect(screen.getByRole("alert")).toBeVisible();
    rerender(<CharacterRevisionHistoryStatus kind="project_mismatch" />);
    expect(screen.getByText(/不属于/u)).toBeVisible();
    rerender(<CharacterRevisionHistoryStatus kind="empty" />);
    expect(screen.getByText(/没有返回/u)).toBeVisible();
    rerender(
      <CharacterRevisionHistoryStatus
        kind="character_not_found"
        error={safeError}
      />,
    );
    expect(screen.getByText(/req-safe/u)).toBeVisible();
    rerender(
      <CharacterRevisionHistoryStatus
        kind="error"
        error={safeError}
        onRetry={retryHistory}
      />,
    );
    await user.click(screen.getByRole("button"));
    expect(retryHistory).toHaveBeenCalledOnce();

    rerender(
      <CharacterRevisionHistoryList
        items={[item(3, true)]}
        selectedRevisionNumber={3}
        hasMore={false}
        loadMoreStatus="idle"
        loadMoreError={null}
        onSelect={select}
        onLoadMore={loadMore}
        onReload={retryHistory}
      />,
    );
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button"));
    expect(select).toHaveBeenCalledWith(3);
    rerender(
      <CharacterRevisionHistoryList
        items={[item(3, true)]}
        selectedRevisionNumber={null}
        hasMore
        loadMoreStatus="load_more_error"
        loadMoreError={safeError}
        onSelect={select}
        onLoadMore={loadMore}
        onReload={retryHistory}
      />,
    );
    await user.click(screen.getByRole("button", { name: /重试|閲嶈瘯/u }));
    expect(loadMore).toHaveBeenCalledOnce();
    const invalidCursorError = new CharacterApiError({
      kind: "invalid_cursor",
      code: "INVALID_CHARACTER_REVISION_CURSOR",
      message: "safe cursor message",
    });
    rerender(
      <CharacterRevisionHistoryList
        items={[{ ...item(2), role: "" }]}
        selectedRevisionNumber={null}
        hasMore
        loadMoreStatus="load_more_error"
        loadMoreError={invalidCursorError}
        onSelect={select}
        onLoadMore={loadMore}
        onReload={retryHistory}
      />,
    );
    expect(screen.getByText("未设置角色定位")).toBeVisible();
    expect(screen.getByText("历史版本")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "重新加载第一页" }));
    expect(retryHistory).toHaveBeenCalledTimes(2);
    rerender(
      <CharacterRevisionHistoryList
        items={[item(3, true)]}
        selectedRevisionNumber={null}
        hasMore
        loadMoreStatus="loading_more"
        loadMoreError={null}
        onSelect={select}
        onLoadMore={loadMore}
        onReload={retryHistory}
      />,
    );
    expect(screen.getAllByRole("button")[1]).toBeDisabled();

    rerender(
      <CharacterRevisionViewer
        state={{ status: "loading_revision", revisionNumber: 2 }}
        onRetry={retryViewer}
      />,
    );
    expect(screen.getByRole("status")).toBeVisible();
    rerender(
      <CharacterRevisionViewer
        state={{
          status: "revision_error",
          revisionNumber: 2,
          error: safeError,
        }}
        onRetry={retryViewer}
      />,
    );
    await user.click(screen.getByRole("button"));
    expect(retryViewer).toHaveBeenCalledOnce();
    rerender(
      <CharacterRevisionViewer
        state={{
          status: "ready",
          revisionNumber: 2,
          revision: { ...revision(2), role: "" },
        }}
        onRetry={retryViewer}
      />,
    );
    expect(screen.getByText("未设置角色定位")).toBeVisible();
    expect(screen.getByText(/历史版本/u)).toBeVisible();
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 3 })).toHaveFocus(),
    );
  });

  it("distinguishes invalid, not-found, and retryable initial failures", async () => {
    const invalidHistory = historyClient();
    const invalid = renderHook(() =>
      useCharacterRevisionHistory("bad", characterId, invalidHistory),
    );
    expect(invalid.result.current.history.status).toBe("invalid_route");
    await act(async () => {
      expect(await invalid.result.current.reload()).toBe(false);
    });
    expect(invalidHistory.listCharacterRevisions).not.toHaveBeenCalled();
    invalid.unmount();

    const missingHistory = historyClient(
      vi.fn().mockRejectedValue(characterError("character_not_found")),
    );
    const missing = renderHook(() =>
      useCharacterRevisionHistory(
        characterProjectId,
        characterId,
        missingHistory,
      ),
    );
    await waitFor(() =>
      expect(missing.result.current.history.status).toBe("character_not_found"),
    );
    missing.unmount();

    const list = vi
      .fn()
      .mockRejectedValueOnce(characterError("unknown"))
      .mockResolvedValueOnce(page());
    const retryHistory = historyClient(list);
    const failure = renderHook(() =>
      useCharacterRevisionHistory(
        characterProjectId,
        characterId,
        retryHistory,
      ),
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
      .mockRejectedValueOnce(characterError("network"))
      .mockResolvedValueOnce(
        page([item(1)], { has_more: false, next_cursor: null }),
      );
    const history = historyClient(list);
    const hook = renderHook(() =>
      useCharacterRevisionHistory(characterProjectId, characterId, history),
    );
    await waitFor(() =>
      expect(hook.result.current.history.status).toBe("ready"),
    );
    await act(async () => {
      await hook.result.current.loadMore();
    });
    expect(hook.result.current.history.items).toHaveLength(2);
    expect(hook.result.current.history.loadMoreStatus).toBe("load_more_error");
    await act(async () => {
      await hook.result.current.loadMore();
    });
    expect(hook.result.current.history.items).toHaveLength(3);
    expect(
      (list.mock.calls[1]?.[0] as ListCharacterRevisionsOptions | undefined)
        ?.cursor,
    ).toBe("opaque-next");
    expect(
      (list.mock.calls[2]?.[0] as ListCharacterRevisionsOptions | undefined)
        ?.cursor,
    ).toBe("opaque-next");
    await act(async () => {
      await hook.result.current.loadMore();
      await hook.result.current.selectRevision(0);
    });
    expect(list).toHaveBeenCalledTimes(3);
    hook.unmount();
  });

  it("reloads the first page after an invalid cursor response", async () => {
    const user = userEvent.setup();
    const list = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockRejectedValueOnce(characterError("invalid_cursor"))
      .mockResolvedValueOnce(page());
    renderHistory(historyClient(list));
    await screen.findByText("设定修订 3");
    await user.click(screen.getByRole("button", { name: "加载更多" }));
    await user.click(
      await screen.findByRole("button", { name: "重新加载第一页" }),
    );
    await waitFor(() => expect(list).toHaveBeenCalledTimes(3));
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
      .mockRejectedValueOnce(characterError("unknown"))
      .mockResolvedValueOnce(revision(2));
    const history = historyClient(list, get);
    const hook = renderHook(() =>
      useCharacterRevisionHistory(characterProjectId, characterId, history),
    );
    await waitFor(() =>
      expect(hook.result.current.history.status).toBe("ready"),
    );
    await act(async () => {
      await hook.result.current.loadMore();
    });
    expect(hook.result.current.history.loadMoreStatus).toBe("load_more_error");
    await act(async () => {
      await hook.result.current.selectRevision(2);
    });
    expect(hook.result.current.viewer.status).toBe("revision_error");
    await act(async () => {
      await hook.result.current.retrySelectedRevision();
    });
    expect(hook.result.current.viewer.status).toBe("ready");
    hook.unmount();
  });

  it("aborts initial history work when unmounted", async () => {
    let capturedSignal: AbortSignal | undefined;
    const pending = new Promise<never>(() => undefined);
    const client = historyClient(
      vi.fn(({ signal }: ListCharacterRevisionsOptions) => {
        capturedSignal = signal;
        return pending;
      }),
    );
    const hook = renderHook(() =>
      useCharacterRevisionHistory(characterProjectId, characterId, client),
    );
    await waitFor(() => expect(capturedSignal).toBeDefined());
    hook.unmount();
    expect(capturedSignal?.aborted).toBe(true);
  });

  it("retries initial and selected failures through page controls", async () => {
    const user = userEvent.setup();
    const list = vi
      .fn()
      .mockRejectedValueOnce(characterError("unknown"))
      .mockResolvedValueOnce(page());
    const get = vi
      .fn()
      .mockRejectedValueOnce(characterError("unknown"))
      .mockResolvedValueOnce(revision(2));
    renderHistory(historyClient(list, get));
    expect(await screen.findByRole("alert")).toBeVisible();
    await user.click(screen.getByRole("button"));
    expect(await screen.findByRole("list")).toBeVisible();
    await user.click(screen.getAllByRole("button", { name: "查看此修订" })[1]);
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
            element={<CharacterRevisionHistoryPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/projects");
  });
});
