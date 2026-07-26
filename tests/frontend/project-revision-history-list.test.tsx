import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ProjectRevisionHistoryItemResponse } from "../../frontend/src/features/projects/api/contracts";
import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import { ProjectRevisionHistoryList } from "../../frontend/src/features/projects/components/ProjectRevisionHistoryList";
import { timestamp } from "./project-detail-support";

const items: readonly ProjectRevisionHistoryItemResponse[] = [
  {
    revision_id: "prv_01ARZ3NDEKTSV4RRFFQ69G5FAX",
    revision_number: 3,
    title: "第三版标题",
    created_at: timestamp,
    is_current: true,
  },
  {
    revision_id: "prv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
    revision_number: 2,
    title: "第二版标题",
    created_at: timestamp,
    is_current: false,
  },
];

function renderList(
  overrides: Partial<Parameters<typeof ProjectRevisionHistoryList>[0]> = {},
) {
  const props: Parameters<typeof ProjectRevisionHistoryList>[0] = {
    items,
    selectedRevisionNumber: null,
    hasMore: true,
    loadMoreStatus: "idle",
    loadMoreError: null,
    onSelect: vi.fn(),
    onLoadMore: vi.fn(),
    ...overrides,
  };
  return { ...render(<ProjectRevisionHistoryList {...props} />), props };
}

describe("Project revision history list", () => {
  it("renders a semantic descending summary list without revision descriptions", () => {
    renderList();
    const entries = screen.getAllByRole("listitem");
    expect(entries).toHaveLength(2);
    expect(entries[0]).toHaveTextContent("修订 3");
    expect(entries[0]).toHaveTextContent("当前修订");
    expect(entries[1]).toHaveTextContent("修订 2");
    expect(entries[1]).toHaveTextContent("历史修订");
    expect(document.body).not.toHaveTextContent("修订正文");
  });

  it("selects only the explicit revision button", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderList({ onSelect, selectedRevisionNumber: 2 });
    await user.click(screen.getByRole("button", { name: "查看内容" }));
    expect(onSelect).toHaveBeenCalledWith(3);
    expect(
      screen.getByRole("button", { name: "重新查看内容" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("disables load-more while a request is in flight", () => {
    renderList({ loadMoreStatus: "loading" });
    expect(screen.getByRole("button", { name: "正在加载…" })).toBeDisabled();
  });

  it("preserves the list and offers an explicit retry after page failure", async () => {
    const user = userEvent.setup();
    const onLoadMore = vi.fn();
    renderList({
      onLoadMore,
      loadMoreStatus: "error",
      loadMoreError: new ProjectApiError({
        kind: "unavailable",
        code: "PROJECT_PERSISTENCE_UNAVAILABLE",
        message: "项目服务暂时不可用，请稍后手动重试。",
        requestId: "req_more",
      }),
    });
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("alert")).toHaveTextContent("req_more");
    await user.click(screen.getByRole("button", { name: "重试加载更多" }));
    expect(onLoadMore).toHaveBeenCalledOnce();
  });

  it("announces the finite end without inventing an action", () => {
    renderList({ hasMore: false });
    expect(screen.getByText("已显示当前可读取的全部修订。")).toBeVisible();
    expect(screen.queryByRole("button", { name: /加载更多/u })).toBeNull();
  });
});
