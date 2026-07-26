import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type {
  ProjectDetailApiClient,
  ProjectRevisionApiClient,
} from "../../frontend/src/features/projects/api/client";
import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import { ProjectDetailsPage } from "../../frontend/src/features/projects/pages/ProjectDetailsPage";
import {
  detailClient,
  projectId,
  secondProjectId,
  versionedResource,
} from "./project-detail-support";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function renderDetails(
  client: ProjectDetailApiClient & ProjectRevisionApiClient,
  path = `/projects/${projectId}`,
  withNavigation = false,
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      {withNavigation ? (
        <Link to={`/projects/${secondProjectId}`}>打开第二个项目</Link>
      ) : null}
      <Routes>
        <Route
          path="/projects/:projectId"
          element={<ProjectDetailsPage client={client} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Project details page", () => {
  it("shows loading then every current snapshot field and GET-based form values", async () => {
    const pending = deferred<ReturnType<typeof versionedResource>>();
    const getProject = vi.fn().mockReturnValue(pending.promise);
    renderDetails(detailClient(getProject));

    expect(screen.getByRole("status")).toHaveTextContent("正在读取项目详情");
    pending.resolve(
      versionedResource(1, {
        title: "真实详情标题",
        description: "第一行\n第二行",
      }),
    );

    expect(
      await screen.findByRole("heading", { level: 2, name: "真实详情标题" }),
    ).toBeVisible();
    expect(
      document.querySelector(".project-details__description"),
    ).toHaveTextContent("第一行 第二行");
    expect(screen.getByText(projectId)).toBeVisible();
    expect(screen.getByText("prv_01ARZ3NDEKTSV4RRFFQ69G5FAV")).toBeVisible();
    expect(screen.getByText("当前修订号").nextElementSibling).toHaveTextContent(
      "1",
    );
    expect(screen.getByText("并发版本").nextElementSibling).toHaveTextContent(
      "1",
    );
    expect(screen.getAllByRole("time")).toHaveLength(4);
    expect(screen.getByRole("textbox", { name: "项目标题" })).toHaveValue(
      "真实详情标题",
    );
    expect(screen.getByRole("textbox", { name: "项目简介" })).toHaveValue(
      "第一行\n第二行",
    );
    expect(getProject).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "返回项目列表" })).toHaveAttribute(
      "href",
      "/projects",
    );
    expect(screen.getByRole("link", { name: "查看修订历史" })).toHaveAttribute(
      "href",
      `/projects/${projectId}/history`,
    );
    expect(
      document.querySelector("main") ?? document.body,
    ).not.toHaveTextContent(/删除|Character|Chapter/u);
  });

  it("renders the explicit empty-description fallback", async () => {
    renderDetails(
      detailClient(
        vi.fn().mockResolvedValue(versionedResource(1, { description: "" })),
      ),
    );

    expect(await screen.findByText("暂无项目简介。")).toBeVisible();
  });

  it("does not request an invalid Project route parameter or echo it", async () => {
    const getProject = vi.fn();
    renderDetails(detailClient(getProject), "/projects/not-valid%0Acanary");
    expect(
      await screen.findByRole("heading", { name: "项目地址无效" }),
    ).toBeVisible();
    expect(getProject).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent("not-valid");
    expect(document.body).not.toHaveTextContent("canary");
  });

  it.each([
    ["not_found", "项目不存在", false],
    ["unavailable", "项目服务暂时不可用", true],
    ["contract", "项目服务返回了无法安全读取的数据", true],
  ] as const)("renders a safe %s state", async (kind, message, retryable) => {
    const error = new ProjectApiError({
      kind,
      code: kind === "not_found" ? "PROJECT_NOT_FOUND" : "SAFE_ERROR",
      message,
      requestId: "req_page",
    });
    const getProject = vi.fn().mockRejectedValue(error);
    renderDetails(detailClient(getProject));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("alert")).toHaveTextContent("req_page");
    expect(
      screen.queryByRole("button", { name: "重新加载项目" }) !== null,
    ).toBe(retryable);
  });

  it("retries an explicit load failure once", async () => {
    const user = userEvent.setup();
    const getProject = vi
      .fn()
      .mockRejectedValueOnce(
        new ProjectApiError({
          kind: "unavailable",
          code: "PROJECT_PERSISTENCE_UNAVAILABLE",
          message: "项目服务暂时不可用，请稍后手动重试。",
        }),
      )
      .mockResolvedValueOnce(versionedResource());
    renderDetails(detailClient(getProject));
    await user.click(
      await screen.findByRole("button", { name: "重新加载项目" }),
    );
    expect(await screen.findByText("当前项目快照")).toBeVisible();
    expect(getProject).toHaveBeenCalledTimes(2);
  });

  it("aborts the old Project request and ignores its late response", async () => {
    const user = userEvent.setup();
    const first = deferred<ReturnType<typeof versionedResource>>();
    const second = deferred<ReturnType<typeof versionedResource>>();
    const signals: AbortSignal[] = [];
    const getProject = vi.fn(
      (id: string, options?: { signal?: AbortSignal }) => {
        if (options?.signal !== undefined) {
          signals.push(options.signal);
        }
        return id === projectId ? first.promise : second.promise;
      },
    );
    renderDetails(detailClient(getProject), `/projects/${projectId}`, true);
    await waitFor(() => expect(getProject).toHaveBeenCalledOnce());
    await user.click(screen.getByRole("link", { name: "打开第二个项目" }));
    await waitFor(() => expect(getProject).toHaveBeenCalledTimes(2));
    expect(signals[0]?.aborted).toBe(true);

    second.resolve(
      versionedResource(1, {
        project_id: secondProjectId,
        title: "第二个项目",
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "第二个项目" }),
    ).toBeVisible();
    first.resolve(versionedResource(1, { title: "过期第一个项目" }));
    await waitFor(() =>
      expect(screen.queryByText("过期第一个项目")).not.toBeInTheDocument(),
    );
  });
});
