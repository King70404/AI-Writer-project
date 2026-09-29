import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { ProjectApiClient } from "../../frontend/src/features/projects/api/client";
import type {
  ProjectListItemResponse,
  ProjectListResponse,
} from "../../frontend/src/features/projects/api/contracts";
import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import { ProjectList } from "../../frontend/src/features/projects/components/ProjectList";
import { formatProjectTimestamp } from "../../frontend/src/features/projects/formatting";
import { useProjectList } from "../../frontend/src/features/projects/hooks/useProjectList";

const timestamp = "2026-07-22T08:30:00Z";

function item(suffix: "V" | "W" = "V"): ProjectListItemResponse {
  return {
    project_id: `prj_01ARZ3NDEKTSV4RRFFQ69G5FA${suffix}`,
    current_revision_id: `prv_01ARZ3NDEKTSV4RRFFQ69G5FA${suffix}`,
    revision_number: suffix === "V" ? 1 : 2,
    concurrency_version: suffix === "V" ? 1 : 2,
    title: suffix === "V" ? "第一项目" : "第二项目",
    created_at: timestamp,
    updated_at: timestamp,
    revision_created_at: timestamp,
  };
}

function page(
  items: readonly ProjectListItemResponse[],
  nextCursor: string | null = null,
): ProjectListResponse {
  return {
    items,
    next_cursor: nextCursor,
    has_more: nextCursor !== null,
  };
}

function client(listProjects: ReturnType<typeof vi.fn>): ProjectApiClient {
  return {
    listProjects,
    createProject: vi.fn(),
  } as ProjectApiClient;
}

function Harness({ apiClient }: { readonly apiClient: ProjectApiClient }) {
  const controller = useProjectList(apiClient);
  return (
    <MemoryRouter>
      <ProjectList controller={controller} />
    </MemoryRouter>
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("Project list", () => {
  it("formats invalid timestamps with a safe fallback", () => {
    expect(formatProjectTimestamp("not-a-timestamp")).toBe("时间不可用");
  });
  it("renders loading, then a semantic truthful list without unsupported fields", async () => {
    const pending = deferred<ProjectListResponse>();
    render(
      <Harness apiClient={client(vi.fn().mockReturnValue(pending.promise))} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("正在读取项目列表");

    pending.resolve(page([item()]));
    expect(
      await screen.findByRole("heading", { name: "第一项目" }),
    ).toBeVisible();
    expect(screen.getByRole("list", { name: "项目列表" })).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(document.body).not.toHaveTextContent(item().project_id);
    expect(document.body).not.toHaveTextContent(item().current_revision_id);
    expect(document.body).not.toHaveTextContent(/当前修订|并发版本/u);
    expect(screen.getByRole("link", { name: "打开小说" })).toHaveAttribute(
      "href",
      `/projects/${item().project_id}`,
    );
    expect(screen.getByRole("listitem")).toHaveAttribute(
      "data-project-id",
      item().project_id,
    );
    expect(screen.getAllByRole("time")).toHaveLength(2);
    expect(
      screen.queryByText(/description|简介|total|总数/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/筛选|排序/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "加载更多" }),
    ).not.toBeInTheDocument();
  });

  it("shows empty only after a successful empty response", async () => {
    render(<Harness apiClient={client(vi.fn().mockResolvedValue(page([])))} />);
    expect(await screen.findByText("还没有项目")).toBeVisible();
    expect(screen.queryByText("项目列表暂时无法读取")).not.toBeInTheDocument();
  });

  it("distinguishes initial failure and retries successfully", async () => {
    const user = userEvent.setup();
    const listProjects = vi
      .fn()
      .mockRejectedValueOnce(
        new ProjectApiError({
          kind: "unavailable",
          code: "SERVICE_UNAVAILABLE",
          message: "项目服务暂时不可用，请稍后手动重试。",
          requestId: "req_list",
        }),
      )
      .mockResolvedValueOnce(page([item()]));
    render(<Harness apiClient={client(listProjects)} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("req_list");
    expect(screen.queryByText("还没有项目")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重新加载列表" }));
    expect(
      await screen.findByRole("heading", { name: "第一项目" }),
    ).toBeVisible();
    expect(listProjects).toHaveBeenCalledTimes(2);
  });

  it("disables load more, appends without replacing, and forwards the opaque cursor", async () => {
    const user = userEvent.setup();
    const pending = deferred<ProjectListResponse>();
    const listProjects = vi
      .fn()
      .mockResolvedValueOnce(page([item()], "opaque+/cursor"))
      .mockReturnValueOnce(pending.promise);
    render(<Harness apiClient={client(listProjects)} />);

    const more = await screen.findByRole("button", { name: "加载更多" });
    await user.click(more);
    expect(screen.getByRole("button", { name: /正在加载更多/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /正在加载更多/ }));
    expect(listProjects).toHaveBeenCalledTimes(2);
    expect(listProjects).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: "opaque+/cursor", limit: 20 }),
    );

    pending.resolve(page([item("W")]));
    expect(
      await screen.findByRole("heading", { name: "第二项目" }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "第一项目" })).toBeVisible();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(
      screen.queryByRole("button", { name: "加载更多" }),
    ).not.toBeInTheDocument();
  });

  it("retains items and cursor after load-more failure, then retries", async () => {
    const user = userEvent.setup();
    const listProjects = vi
      .fn()
      .mockResolvedValueOnce(page([item()], "keep-this-cursor"))
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(page([item("W")]));
    render(<Harness apiClient={client(listProjects)} />);

    await user.click(await screen.findByRole("button", { name: "加载更多" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "无法连接本地项目服务",
    );
    expect(screen.getByRole("heading", { name: "第一项目" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "重试加载更多" }));
    expect(
      await screen.findByRole("heading", { name: "第二项目" }),
    ).toBeVisible();
    expect(listProjects.mock.calls[1]?.[0]).toMatchObject({
      cursor: "keep-this-cursor",
    });
    expect(listProjects.mock.calls[2]?.[0]).toMatchObject({
      cursor: "keep-this-cursor",
    });
  });

  it("turns a duplicate cross-page ID into a visible contract error", async () => {
    const user = userEvent.setup();
    const listProjects = vi
      .fn()
      .mockResolvedValueOnce(page([item()], "cursor"))
      .mockResolvedValueOnce(page([item()]));
    render(<Harness apiClient={client(listProjects)} />);

    await user.click(await screen.findByRole("button", { name: "加载更多" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("重复项目");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("aborts the active GET on unmount without rendering an error", async () => {
    const listProjects = vi.fn(
      ({ signal }: { readonly signal?: AbortSignal }) =>
        new Promise<ProjectListResponse>((_resolve, reject) => {
          signal?.addEventListener(
            "abort",
            () => reject(new DOMException("aborted", "AbortError")),
            { once: true },
          );
        }),
    );
    const view = render(<Harness apiClient={client(listProjects)} />);
    await waitFor(() => expect(listProjects).toHaveBeenCalledOnce());
    const signal = listProjects.mock.calls[0]?.[0].signal as AbortSignal;

    view.unmount();

    expect(signal.aborted).toBe(true);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
