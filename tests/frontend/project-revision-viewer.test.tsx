import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import { ProjectRevisionViewer } from "../../frontend/src/features/projects/components/ProjectRevisionViewer";
import { projectId, timestamp } from "./project-detail-support";

const readyState = {
  status: "ready" as const,
  revisionNumber: 2,
  revision: {
    project_id: projectId,
    revision_id: "prv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
    revision_number: 2,
    title: "第二版标题",
    description: "第一行\n第二行",
    created_at: timestamp,
    is_current: false,
    current_revision_number: 3,
  },
};

describe("Project revision viewer", () => {
  it("starts idle and does not fetch or imply mutation controls", () => {
    render(
      <ProjectRevisionViewer state={{ status: "idle" }} onRetry={vi.fn()} />,
    );
    expect(screen.getByText(/尚未选择修订/u)).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("announces the selected revision while loading", () => {
    render(
      <ProjectRevisionViewer
        state={{ status: "loading", revisionNumber: 2 }}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("正在读取修订 2");
  });

  it("renders a selected snapshot preserving line breaks and focuses its heading", async () => {
    render(<ProjectRevisionViewer state={readyState} onRetry={vi.fn()} />);
    const heading = screen.getByRole("heading", {
      level: 3,
      name: "修订 2：第二版标题",
    });
    await waitFor(() => expect(heading).toHaveFocus());
    const description = document.querySelector(
      ".project-revision-viewer__description",
    );
    expect(description?.textContent).toBe("第一行\n第二行");
    expect(screen.getByText("历史修订")).toBeVisible();
    expect(document.body).not.toHaveTextContent(
      readyState.revision.revision_id,
    );
    expect(screen.getByRole("time")).toHaveAttribute(
      "datetime",
      readyState.revision.created_at,
    );
  });

  it("shows the explicit empty-description fallback", () => {
    render(
      <ProjectRevisionViewer
        state={{
          ...readyState,
          revision: { ...readyState.revision, description: "" },
        }}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByText("该修订没有项目简介。")).toBeVisible();
  });

  it("offers one explicit retry after a viewer failure", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <ProjectRevisionViewer
        state={{
          status: "error",
          revisionNumber: 2,
          error: new ProjectApiError({
            kind: "not_found",
            code: "PROJECT_REVISION_NOT_FOUND",
            message: "指定修订不存在。",
            requestId: "req_revision",
          }),
        }}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("req_revision");
    await user.click(screen.getByRole("button", { name: "重试读取该修订" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
