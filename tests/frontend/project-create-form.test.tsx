import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, type Mock } from "vitest";

import type { ProjectApiClient } from "../../frontend/src/features/projects/api/client";
import type { ProjectResponse } from "../../frontend/src/features/projects/api/contracts";
import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import { CreateProjectForm } from "../../frontend/src/features/projects/components/CreateProjectForm";

const projectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV";

function createdProject(): ProjectResponse {
  return {
    project_id: projectId,
    current_revision_id: "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV",
    revision_number: 1,
    concurrency_version: 1,
    title: "新项目",
    description: "",
    created_at: "2026-07-22T08:30:00Z",
    updated_at: "2026-07-22T08:30:00Z",
    revision_created_at: "2026-07-22T08:30:00Z",
    head_updated_at: "2026-07-22T08:30:00Z",
  };
}

function apiClient(createProject = vi.fn()): ProjectApiClient {
  return {
    listProjects: vi.fn(),
    createProject,
  };
}

function renderForm(
  createProject: Mock<ProjectApiClient["createProject"]> = vi
    .fn<ProjectApiClient["createProject"]>()
    .mockResolvedValue(createdProject()),
  reloadProjects: Mock<() => Promise<boolean>> = vi
    .fn<() => Promise<boolean>>()
    .mockResolvedValue(true),
) {
  const client = apiClient(createProject);
  render(<CreateProjectForm client={client} reloadProjects={reloadProjects} />);
  return { createProject, reloadProjects };
}

describe("Create Project form", () => {
  it("associates labels and validates required title without side effects", async () => {
    const user = userEvent.setup();
    const { createProject, reloadProjects } = renderForm();
    const title = screen.getByRole("textbox", { name: "项目标题" });
    const description = screen.getByRole("textbox", { name: "项目简介" });

    expect(title).toHaveAttribute("id", "project-title");
    expect(description).toHaveAttribute("id", "project-description");
    await user.click(screen.getByRole("button", { name: "创建项目" }));

    expect(await screen.findByText("请输入项目标题。")).toBeVisible();
    expect(title).toHaveFocus();
    expect(createProject).not.toHaveBeenCalled();
    expect(reloadProjects).not.toHaveBeenCalled();
  });

  it("counts Unicode code points, including one per emoji", async () => {
    const user = userEvent.setup();
    renderForm();
    const title = screen.getByRole("textbox", { name: "项目标题" });
    await user.type(title, "甲😀乙");
    expect(screen.getByText("3 / 120 字符")).toBeVisible();

    const description = screen.getByRole("textbox", { name: "项目简介" });
    await user.type(description, "😀😀");
    expect(screen.getByText("2 / 2000 字符")).toBeVisible();
  });

  it("rejects overlong title and description before calling the client", async () => {
    const user = userEvent.setup();
    const { createProject } = renderForm();
    const title = screen.getByRole("textbox", { name: "项目标题" });
    const description = screen.getByRole("textbox", { name: "项目简介" });
    fireEvent.change(title, { target: { value: "😀".repeat(121) } });
    fireEvent.change(description, { target: { value: "文".repeat(2_001) } });
    await user.click(screen.getByRole("button", { name: "创建项目" }));

    expect(screen.getByText("项目标题不能超过120个字符。")).toBeVisible();
    expect(screen.getByText("项目简介不能超过2000个字符。")).toBeVisible();
    expect(createProject).not.toHaveBeenCalled();
  });

  it("allows an empty description, prevents duplicates, clears on success and refreshes", async () => {
    const user = userEvent.setup();
    let resolveCreate!: (value: ProjectResponse) => void;
    const createProject = vi.fn<ProjectApiClient["createProject"]>(
      () =>
        new Promise<ProjectResponse>((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const reloadProjects = vi.fn().mockResolvedValue(true);
    renderForm(createProject, reloadProjects);
    const title = screen.getByRole("textbox", { name: "项目标题" });
    await user.type(title, "新项目");

    await user.click(screen.getByRole("button", { name: "创建项目" }));
    const submitting = screen.getByRole("button", { name: /正在创建项目/ });
    expect(submitting).toBeDisabled();
    await user.click(submitting);
    expect(createProject).toHaveBeenCalledOnce();
    const [submitted, options] = createProject.mock.calls[0] ?? [];
    expect(submitted).toEqual({ title: "新项目", description: "" });
    expect(options?.signal).toBeInstanceOf(AbortSignal);

    resolveCreate(createdProject());
    expect(await screen.findByRole("status")).toHaveTextContent(projectId);
    expect(title).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "项目简介" })).toHaveValue("");
    expect(reloadProjects).toHaveBeenCalledOnce();
    expect(screen.getByRole("status")).toHaveFocus();
    expect(
      screen.queryByRole("button", { name: /编辑|删除/ }),
    ).not.toBeInTheDocument();
  });

  it("retains input and maps a server field error with request ID", async () => {
    const user = userEvent.setup();
    const createProject = vi.fn().mockRejectedValue(
      new ProjectApiError({
        kind: "validation",
        code: "VALIDATION_ERROR",
        message: "提交内容未通过服务端验证。",
        requestId: "req_validation",
        fieldErrors: [
          { field: "title", message: "项目标题未通过服务端验证。" },
        ],
      }),
    );
    const { reloadProjects } = renderForm(createProject);
    const title = screen.getByRole("textbox", { name: "项目标题" });
    const description = screen.getByRole("textbox", { name: "项目简介" });
    await user.type(title, "保留标题");
    await user.type(description, "保留简介");
    await user.click(screen.getByRole("button", { name: "创建项目" }));

    expect(await screen.findByText("项目标题未通过服务端验证。")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("req_validation");
    expect(title).toHaveValue("保留标题");
    expect(description).toHaveValue("保留简介");
    expect(title).toHaveFocus();
    expect(reloadProjects).not.toHaveBeenCalled();

    await user.type(title, "补充");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("focuses a server-rejected description", async () => {
    const user = userEvent.setup();
    renderForm(
      vi.fn<ProjectApiClient["createProject"]>().mockRejectedValue(
        new ProjectApiError({
          kind: "validation",
          code: "VALIDATION_ERROR",
          message: "提交内容未通过服务端验证。",
          fieldErrors: [
            { field: "description", message: "项目简介未通过服务端验证。" },
          ],
        }),
      ),
    );
    await user.type(screen.getByRole("textbox", { name: "项目标题" }), "项目");
    await user.type(screen.getByRole("textbox", { name: "项目简介" }), "简介");
    await user.click(screen.getByRole("button", { name: "创建项目" }));

    expect(await screen.findByText("项目简介未通过服务端验证。")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "项目简介" })).toHaveFocus();
  });

  it.each([
    ["unavailable", "项目服务暂时不可用，请稍后手动重试。"],
    ["security", "安全会话无效，请检查后手动重新提交。"],
  ] as const)(
    "shows a safe %s form error without exposing tokens",
    async (kind, message) => {
      const user = userEvent.setup();
      const privateToken = "csrf-private-never-render";
      renderForm(
        vi.fn().mockRejectedValue(
          new ProjectApiError({
            kind,
            code:
              kind === "security"
                ? "CSRF_TOKEN_INVALID"
                : "SERVICE_UNAVAILABLE",
            message,
            requestId: "req_form",
          }),
        ),
      );
      await user.type(
        screen.getByRole("textbox", { name: "项目标题" }),
        "项目",
      );
      await user.click(screen.getByRole("button", { name: "创建项目" }));

      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(screen.getByRole("alert")).toHaveTextContent("req_form");
      expect(document.body).not.toHaveTextContent(privateToken);
      expect(screen.getByRole("alert")).toHaveFocus();
    },
  );

  it("clears stale field feedback when the user edits the field", async () => {
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByRole("button", { name: "创建项目" }));
    expect(await screen.findByText("请输入项目标题。")).toBeVisible();
    await user.type(screen.getByRole("textbox", { name: "项目标题" }), "有效");
    await waitFor(() =>
      expect(screen.queryByText("请输入项目标题。")).not.toBeInTheDocument(),
    );
  });
});
