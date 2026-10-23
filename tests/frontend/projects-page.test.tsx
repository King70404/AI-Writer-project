import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { ProjectApiClient } from "../../frontend/src/features/projects/api/client";
import type {
  ProjectListItemResponse,
  ProjectResponse,
} from "../../frontend/src/features/projects/api/contracts";
import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import { ProjectsPage } from "../../frontend/src/features/projects/pages/ProjectsPage";

const timestamp = "2026-07-22T08:30:00Z";

function item(title: string, suffix: "V" | "W"): ProjectListItemResponse {
  return {
    project_id: `prj_01ARZ3NDEKTSV4RRFFQ69G5FA${suffix}`,
    current_revision_id: `prv_01ARZ3NDEKTSV4RRFFQ69G5FA${suffix}`,
    revision_number: 1,
    concurrency_version: 1,
    title,
    created_at: timestamp,
    updated_at: timestamp,
    revision_created_at: timestamp,
  };
}

function project(title = "新项目"): ProjectResponse {
  return {
    ...item(title, "W"),
    description: "真实简介",
    head_updated_at: timestamp,
  };
}

function page(
  items: readonly ProjectListItemResponse[],
  cursor: string | null = null,
) {
  return { items, next_cursor: cursor, has_more: cursor !== null };
}

function client(
  listProjects: ReturnType<typeof vi.fn>,
  createProject = vi.fn().mockResolvedValue(project()),
): ProjectApiClient {
  return { listProjects, createProject } as ProjectApiClient;
}

async function fillAndCreate(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("textbox", { name: "书名" }), "新项目");
  await user.type(
    screen.getByRole("textbox", { name: "一句话简介（可选）" }),
    "真实简介",
  );
  await user.click(screen.getByRole("button", { name: "创建小说" }));
}

function renderProjectsPage(clientValue: ProjectApiClient) {
  return render(
    <MemoryRouter>
      <ProjectsPage client={clientValue} />
    </MemoryRouter>,
  );
}

describe("Projects page composition", () => {
  it("loads the initial list and exposes only current list/create actions", async () => {
    const user = userEvent.setup();
    const listProjects = vi
      .fn()
      .mockResolvedValue(page([item("已有项目", "V")]));
    renderProjectsPage(client(listProjects));

    expect(
      screen.getByRole("heading", { level: 2, name: "书架" }),
    ).toBeVisible();
    expect(
      await screen.findByRole("heading", { name: "已有项目" }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "新建小说" })).toBeVisible();
    expect(
      screen.queryByRole("button", {
        name: /详情|编辑|删除|历史|搜索|筛选|排序/,
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/总数|total/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "刷新" }));
    expect(listProjects).toHaveBeenCalledTimes(2);
  });

  it("creates once and refreshes a fresh first page without the old cursor", async () => {
    const user = userEvent.setup();
    const listProjects = vi
      .fn()
      .mockResolvedValueOnce(page([item("已有项目", "V")], "old-opaque-cursor"))
      .mockResolvedValueOnce(
        page([item("新项目", "W"), item("已有项目", "V")]),
      );
    const createProject = vi.fn().mockResolvedValue(project());
    renderProjectsPage(client(listProjects, createProject));
    await screen.findByRole("heading", { name: "已有项目" });

    await fillAndCreate(user);

    expect(await screen.findByText("小说《新项目》已创建。")).toBeVisible();
    expect(screen.getByRole("heading", { name: "新项目" })).toBeVisible();
    expect(createProject).toHaveBeenCalledOnce();
    expect(listProjects).toHaveBeenCalledTimes(2);
    expect(listProjects.mock.calls[1]?.[0]).toMatchObject({ limit: 20 });
    expect(listProjects.mock.calls[1]?.[0]).not.toHaveProperty("cursor");
  });

  it("reports partial success, never re-POSTs, and allows manual list recovery", async () => {
    const user = userEvent.setup();
    const listProjects = vi
      .fn()
      .mockResolvedValueOnce(page([]))
      .mockRejectedValueOnce(new TypeError("refresh offline"))
      .mockResolvedValueOnce(page([item("新项目", "W")]));
    const createProject = vi.fn().mockResolvedValue(project());
    renderProjectsPage(client(listProjects, createProject));
    await screen.findByText("还没有项目");

    await fillAndCreate(user);

    const partial = await screen.findByRole("status");
    expect(partial).toHaveTextContent("小说《新项目》已创建，但列表刷新失败");
    expect(partial).not.toHaveTextContent("创建失败");
    expect(createProject).toHaveBeenCalledOnce();
    await user.click(
      within(partial).getByRole("button", { name: "重新加载列表" }),
    );
    expect(
      await screen.findByRole("heading", { name: "新项目" }),
    ).toBeVisible();
    expect(createProject).toHaveBeenCalledOnce();
    expect(listProjects).toHaveBeenCalledTimes(3);
  });

  it("does not refresh the list after create failure", async () => {
    const user = userEvent.setup();
    const listProjects = vi.fn().mockResolvedValue(page([]));
    const createProject = vi.fn().mockRejectedValue(
      new ProjectApiError({
        kind: "unavailable",
        code: "SERVICE_UNAVAILABLE",
        message: "项目服务暂时不可用，请稍后手动重试。",
      }),
    );
    renderProjectsPage(client(listProjects, createProject));
    await screen.findByText("还没有项目");

    await fillAndCreate(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "项目服务暂时不可用",
    );
    expect(listProjects).toHaveBeenCalledOnce();
  });
});
