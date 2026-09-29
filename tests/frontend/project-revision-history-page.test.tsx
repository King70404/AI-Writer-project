import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { ProjectRevisionHistoryApiClient } from "../../frontend/src/features/projects/api/client";
import type {
  ProjectRevisionHistoryResponse,
  ProjectRevisionResponse,
} from "../../frontend/src/features/projects/api/contracts";
import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import { useProjectRevisionHistory } from "../../frontend/src/features/projects/hooks/useProjectRevisionHistory";
import { ProjectRevisionHistoryPage } from "../../frontend/src/features/projects/pages/ProjectRevisionHistoryPage";
import { projectId, timestamp } from "./project-detail-support";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function item(number: number, current = false) {
  const suffix = number === 3 ? "X" : number === 2 ? "W" : "V";
  return {
    revision_id: `prv_01ARZ3NDEKTSV4RRFFQ69G5FA${suffix}`,
    revision_number: number,
    title: `修订标题 ${number}`,
    created_at: timestamp,
    is_current: current,
  };
}

function page(
  items: ReturnType<typeof item>[] = [item(3, true), item(2)],
  overrides: Partial<ProjectRevisionHistoryResponse> = {},
): ProjectRevisionHistoryResponse {
  return {
    project_id: projectId,
    current_revision_number: 3,
    items,
    next_cursor: "next-page",
    has_more: true,
    ...overrides,
  };
}

function snapshot(number: number): ProjectRevisionResponse {
  return {
    project_id: projectId,
    revision_id: item(number).revision_id,
    revision_number: number,
    title: `修订标题 ${number}`,
    description: `修订 ${number} 的只读内容`,
    created_at: timestamp,
    is_current: number === 3,
    current_revision_number: 3,
  };
}

function historyClient(
  listProjectRevisions = vi.fn().mockResolvedValue(page()),
  getProjectRevision = vi
    .fn()
    .mockImplementation(
      ({ revisionNumber }: { readonly revisionNumber: number }) =>
        Promise.resolve(snapshot(revisionNumber)),
    ),
): ProjectRevisionHistoryApiClient {
  return { listProjectRevisions, getProjectRevision };
}

function renderHistory(
  client: ProjectRevisionHistoryApiClient,
  path = `/projects/${projectId}/history`,
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/projects/:projectId/history"
          element={<ProjectRevisionHistoryPage client={client} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

function HistoryHookHarness({
  client,
}: {
  readonly client: ProjectRevisionHistoryApiClient;
}) {
  const controller = useProjectRevisionHistory(projectId, client);
  return (
    <div>
      <output data-testid="history-status">{controller.history.status}</output>
      <output data-testid="viewer-status">{controller.viewer.status}</output>
      <button type="button" onClick={() => void controller.loadMore()}>
        hook-load-more
      </button>
      <button type="button" onClick={() => void controller.selectRevision(0)}>
        hook-select-invalid
      </button>
      <button type="button" onClick={() => void controller.selectRevision(2)}>
        hook-select-valid
      </button>
      <button
        type="button"
        onClick={() => void controller.retrySelectedRevision()}
      >
        hook-retry-viewer
      </button>
    </div>
  );
}

describe("Project revision history page", () => {
  it("loads summaries only, links back, then fetches content on explicit selection", async () => {
    const user = userEvent.setup();
    const listProjectRevisions = vi.fn().mockResolvedValue(page());
    const getProjectRevision = vi.fn().mockResolvedValue(snapshot(2));
    renderHistory(historyClient(listProjectRevisions, getProjectRevision));

    expect(screen.getByRole("status")).toHaveTextContent("正在读取修订历史");
    expect(await screen.findByText("修订标题 3")).toBeVisible();
    expect(screen.getByRole("heading", { name: "小说修订历史" })).toBeVisible();
    expect(document.body).not.toHaveTextContent(projectId);
    expect(getProjectRevision).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "返回小说详情" })).toHaveAttribute(
      "href",
      `/projects/${projectId}`,
    );

    await user.click(screen.getAllByRole("button", { name: "查看内容" })[1]);
    expect(await screen.findByText("修订 2 的只读内容")).toBeVisible();
    for (const id of [projectId, item(2).revision_id, item(3).revision_id])
      expect(document.body).not.toHaveTextContent(id);
    expect(getProjectRevision).toHaveBeenCalledWith(
      expect.objectContaining({ projectId, revisionNumber: 2 }),
    );
    expect(document.body).not.toHaveTextContent(/回滚|恢复|采用|删除/u);
  });

  it("appends a cursor page and keeps prior rows when a duplicate page is rejected", async () => {
    const user = userEvent.setup();
    const listProjectRevisions = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(
        page([item(1)], { next_cursor: "last", has_more: true }),
      )
      .mockResolvedValueOnce(
        page([item(1)], { next_cursor: null, has_more: false }),
      );
    renderHistory(historyClient(listProjectRevisions));
    await screen.findByText("修订标题 3");

    await user.click(screen.getByRole("button", { name: "加载更多" }));
    expect(await screen.findByText("修订标题 1")).toBeVisible();
    expect(listProjectRevisions).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: "next-page" }),
    );

    await user.click(screen.getByRole("button", { name: "加载更多" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "修订历史分页响应包含重复修订",
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("rejects an invalid route before API access and does not echo it", async () => {
    const client = historyClient(vi.fn(), vi.fn());
    renderHistory(client, "/projects/not-valid%0Aprivate-canary/history");
    expect(
      await screen.findByRole("heading", { name: "项目地址无效" }),
    ).toBeVisible();
    expect(client.listProjectRevisions).not.toHaveBeenCalled();
    expect(client.getProjectRevision).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent("not-valid");
    expect(document.body).not.toHaveTextContent("private-canary");
  });

  it("renders safe not-found and retryable load states", async () => {
    const user = userEvent.setup();
    const listProjectRevisions = vi
      .fn()
      .mockRejectedValueOnce(
        new ProjectApiError({
          kind: "unavailable",
          code: "PROJECT_PERSISTENCE_UNAVAILABLE",
          message: "项目服务暂时不可用，请稍后手动重试。",
          requestId: "req_history",
        }),
      )
      .mockResolvedValueOnce(page([], { next_cursor: null, has_more: false }));
    renderHistory(historyClient(listProjectRevisions));
    expect(await screen.findByRole("alert")).toHaveTextContent("req_history");
    await user.click(screen.getByRole("button", { name: "重新读取历史" }));
    expect(
      await screen.findByText("已显示当前可读取的全部修订。"),
    ).toBeVisible();
    expect(listProjectRevisions).toHaveBeenCalledTimes(2);
  });

  it("aborts an old viewer request and ignores its late result", async () => {
    const user = userEvent.setup();
    const older = deferred<ProjectRevisionResponse>();
    const newer = deferred<ProjectRevisionResponse>();
    const signals: AbortSignal[] = [];
    const getProjectRevision = vi.fn(
      ({
        revisionNumber,
        signal,
      }: {
        revisionNumber: number;
        signal?: AbortSignal;
      }) => {
        if (signal !== undefined) signals.push(signal);
        return revisionNumber === 2 ? older.promise : newer.promise;
      },
    );
    renderHistory(
      historyClient(vi.fn().mockResolvedValue(page()), getProjectRevision),
    );
    await screen.findByText("修订标题 3");
    const buttons = screen.getAllByRole("button", { name: "查看内容" });
    await user.click(buttons[1]);
    await user.click(buttons[0]);
    expect(signals[0]?.aborted).toBe(true);

    newer.resolve(snapshot(3));
    expect(await screen.findByText("修订 3 的只读内容")).toBeVisible();
    older.resolve(snapshot(2));
    await waitFor(() =>
      expect(screen.queryByText("修订 2 的只读内容")).not.toBeInTheDocument(),
    );
  });

  it("renders a terminal not-found state without offering a retry", async () => {
    const listProjectRevisions = vi.fn().mockRejectedValue(
      new ProjectApiError({
        kind: "not_found",
        code: "PROJECT_NOT_FOUND",
        message: "项目不存在。",
        requestId: null,
      }),
    );
    renderHistory(historyClient(listProjectRevisions));

    expect(
      await screen.findByRole("heading", { name: "项目不存在" }),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: "重新读取历史" })).toBeNull();
  });

  it("preserves rows after a load-more failure and retries the same cursor", async () => {
    const user = userEvent.setup();
    const listProjectRevisions = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockRejectedValueOnce(
        new ProjectApiError({
          kind: "unavailable",
          code: "PROJECT_PERSISTENCE_UNAVAILABLE",
          message: "历史服务暂时不可用。",
          requestId: "req_more",
        }),
      )
      .mockResolvedValueOnce(
        page([item(1)], { next_cursor: null, has_more: false }),
      );
    renderHistory(historyClient(listProjectRevisions));
    await screen.findByText("修订标题 3");

    await user.click(screen.getByRole("button", { name: "加载更多" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("req_more");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "重试加载更多" }));
    expect(await screen.findByText("修订标题 1")).toBeVisible();
    expect(listProjectRevisions).toHaveBeenNthCalledWith(
      3,
      expect.objectContaining({ cursor: "next-page" }),
    );
  });

  it("retries an explicitly selected revision after a safe viewer failure", async () => {
    const user = userEvent.setup();
    const getProjectRevision = vi
      .fn()
      .mockRejectedValueOnce(
        new ProjectApiError({
          kind: "not_found",
          code: "PROJECT_REVISION_NOT_FOUND",
          message: "指定修订不存在。",
          requestId: "req_viewer",
        }),
      )
      .mockResolvedValueOnce(snapshot(2));
    renderHistory(
      historyClient(vi.fn().mockResolvedValue(page()), getProjectRevision),
    );
    await screen.findByText("修订标题 3");

    await user.click(screen.getAllByRole("button", { name: "查看内容" })[1]);
    expect(await screen.findByRole("alert")).toHaveTextContent("req_viewer");
    await user.click(screen.getByRole("button", { name: "重试读取该修订" }));
    expect(await screen.findByText("修订 2 的只读内容")).toBeVisible();
    expect(getProjectRevision).toHaveBeenCalledTimes(2);
  });

  it("aborts the initial history request when the route unmounts", async () => {
    const pending = deferred<ProjectRevisionHistoryResponse>();
    let signal: AbortSignal | undefined;
    const listProjectRevisions = vi.fn(
      ({ signal: requestSignal }: { signal?: AbortSignal }) => {
        signal = requestSignal;
        return pending.promise;
      },
    );
    const rendered = renderHistory(historyClient(listProjectRevisions));
    await waitFor(() => expect(listProjectRevisions).toHaveBeenCalledOnce());

    rendered.unmount();
    expect(signal?.aborted).toBe(true);
    pending.resolve(page());
  });

  it("guards duplicate page loads, invalid selection, and retry while loading", async () => {
    const user = userEvent.setup();
    const pendingPage = deferred<ProjectRevisionHistoryResponse>();
    const pendingRevision = deferred<ProjectRevisionResponse>();
    const listProjectRevisions = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockReturnValueOnce(pendingPage.promise);
    const getProjectRevision = vi.fn().mockReturnValue(pendingRevision.promise);
    const rendered = render(
      <HistoryHookHarness
        client={historyClient(listProjectRevisions, getProjectRevision)}
      />,
    );
    expect(await screen.findByTestId("history-status")).toHaveTextContent(
      "ready",
    );

    await user.click(
      screen.getByRole("button", { name: "hook-select-invalid" }),
    );
    expect(getProjectRevision).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "hook-retry-viewer" }));
    expect(getProjectRevision).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "hook-load-more" }));
    await user.click(screen.getByRole("button", { name: "hook-load-more" }));
    expect(listProjectRevisions).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole("button", { name: "hook-select-valid" }));
    expect(screen.getByTestId("viewer-status")).toHaveTextContent("loading");
    await user.click(screen.getByRole("button", { name: "hook-retry-viewer" }));
    expect(getProjectRevision).toHaveBeenCalledOnce();

    rendered.unmount();
    pendingPage.resolve(
      page([item(1)], { next_cursor: null, has_more: false }),
    );
    pendingRevision.resolve(snapshot(2));
  });
});
