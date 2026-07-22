import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
  versionedResource,
} from "./project-detail-support";

function conflictError(requestId: string | null = "req_conflict_safe") {
  return new ProjectApiError({
    kind: "conflict",
    code: "PROJECT_VERSION_CONFLICT",
    message: "项目已被其他操作修订。草稿已保留，请读取最新版本后选择处理方式。",
    requestId,
    conflict: { expectedVersion: 1, actualVersion: 2 },
  });
}

function renderConflict(
  client: ProjectDetailApiClient & ProjectRevisionApiClient,
) {
  return render(
    <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
      <Routes>
        <Route
          path="/projects/:projectId"
          element={<ProjectDetailsPage client={client} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

async function makeDraftAndSave(user: ReturnType<typeof userEvent.setup>) {
  const title = await screen.findByRole("textbox", { name: "项目标题" });
  const description = screen.getByRole("textbox", { name: "项目简介" });
  await user.clear(title);
  await user.type(title, "我的冲突草稿");
  await user.clear(description);
  await user.type(description, "我的草稿简介\n第二行");
  await user.click(screen.getByRole("button", { name: "保存完整修订" }));
  return { title, description };
}

describe("Project explicit conflict workflow", () => {
  it("enters conflict without automatic GET or PUT retry and preserves the draft", async () => {
    const user = userEvent.setup();
    const getProject = vi.fn().mockResolvedValue(versionedResource());
    const reviseProject = vi.fn().mockRejectedValue(conflictError());
    renderConflict(detailClient(getProject, reviseProject));
    const controls = await makeDraftAndSave(user);

    const conflict = await screen.findByRole("alert");
    expect(
      within(conflict).getByRole("heading", { name: "检测到版本冲突" }),
    ).toHaveFocus();
    expect(conflict).toHaveTextContent("版本 1");
    expect(conflict).toHaveTextContent("版本 2");
    expect(conflict).toHaveTextContent("req_conflict_safe");
    expect(controls.title).toHaveValue("我的冲突草稿");
    expect(controls.description).toHaveValue("我的草稿简介\n第二行");
    expect(screen.getByRole("button", { name: "保存完整修订" })).toBeDisabled();
    expect(getProject).toHaveBeenCalledOnce();
    expect(reviseProject).toHaveBeenCalledOnce();
    await Promise.resolve();
    expect(getProject).toHaveBeenCalledOnce();
    expect(reviseProject).toHaveBeenCalledOnce();
  });

  it("loads latest only on demand and never overwrites the draft automatically", async () => {
    const user = userEvent.setup();
    const getProject = vi
      .fn()
      .mockResolvedValueOnce(versionedResource())
      .mockResolvedValueOnce(
        versionedResource(2, {
          title: "另一方最新标题",
          description: "另一方最新简介",
        }),
      );
    const reviseProject = vi.fn().mockRejectedValue(conflictError());
    renderConflict(detailClient(getProject, reviseProject));
    const controls = await makeDraftAndSave(user);

    await user.click(
      await screen.findByRole("button", { name: "读取最新版本" }),
    );
    expect(await screen.findByText("另一方最新标题")).toBeVisible();
    expect(screen.getByText("我的冲突草稿")).toBeVisible();
    expect(controls.title).toHaveValue("我的冲突草稿");
    expect(controls.description).toHaveValue("我的草稿简介\n第二行");
    expect(getProject).toHaveBeenCalledTimes(2);
    expect(reviseProject).toHaveBeenCalledOnce();
  });

  it("explicitly abandons the draft and adopts latest without sending PUT", async () => {
    const user = userEvent.setup();
    const getProject = vi
      .fn()
      .mockResolvedValueOnce(versionedResource())
      .mockResolvedValueOnce(
        versionedResource(2, {
          title: "采用的最新标题",
          description: "采用的最新简介",
        }),
      );
    const reviseProject = vi.fn().mockRejectedValue(conflictError());
    renderConflict(detailClient(getProject, reviseProject));
    await makeDraftAndSave(user);
    await user.click(
      await screen.findByRole("button", { name: "读取最新版本" }),
    );
    await user.click(
      await screen.findByRole("button", {
        name: "放弃当前草稿并采用最新版本",
      }),
    );

    expect(screen.getByRole("textbox", { name: "项目标题" })).toHaveValue(
      "采用的最新标题",
    );
    expect(screen.getByRole("textbox", { name: "项目简介" })).toHaveValue(
      "采用的最新简介",
    );
    expect(
      screen.getByText("已放弃当前草稿并采用服务端最新版本。").parentElement,
    ).toHaveFocus();
    expect(screen.getByRole("button", { name: "保存完整修订" })).toBeDisabled();
    expect(reviseProject).toHaveBeenCalledOnce();
  });

  it("rebases while retaining the draft and requires a second manual save with the latest ETag", async () => {
    const user = userEvent.setup();
    const getProject = vi
      .fn()
      .mockResolvedValueOnce(versionedResource())
      .mockResolvedValueOnce(
        versionedResource(2, {
          title: "服务端版本2",
          description: "服务端简介2",
        }),
      );
    const reviseProject = vi
      .fn()
      .mockRejectedValueOnce(conflictError())
      .mockResolvedValueOnce(
        versionedResource(3, {
          title: "我的冲突草稿",
          description: "我的草稿简介\n第二行",
        }),
      );
    renderConflict(detailClient(getProject, reviseProject));
    const controls = await makeDraftAndSave(user);
    await user.click(
      await screen.findByRole("button", { name: "读取最新版本" }),
    );
    await user.click(
      await screen.findByRole("button", {
        name: "保留草稿并以最新版本建立基线",
      }),
    );

    expect(controls.title).toHaveValue("我的冲突草稿");
    expect(controls.description).toHaveValue("我的草稿简介\n第二行");
    expect(
      screen.getByText("当前草稿将在下次手动保存时完整替换最新标题和简介。")
        .parentElement,
    ).toHaveFocus();
    expect(reviseProject).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "保存完整修订" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "保存完整修订" }));
    await waitFor(() => expect(reviseProject).toHaveBeenCalledTimes(2));
    expect(reviseProject.mock.calls[1]?.[0]).toMatchObject({
      etag: '"2"',
      title: "我的冲突草稿",
      description: "我的草稿简介\n第二行",
    });
    expect(await screen.findByText("项目修订已保存。")).toBeVisible();
    expect(screen.getByText("并发版本").nextElementSibling).toHaveTextContent(
      "3",
    );
  });

  it("keeps conflict and draft when latest GET fails or is older than actual", async () => {
    const user = userEvent.setup();
    const getProject = vi
      .fn()
      .mockResolvedValueOnce(versionedResource())
      .mockRejectedValueOnce(
        new ProjectApiError({
          kind: "unavailable",
          code: "PROJECT_PERSISTENCE_UNAVAILABLE",
          message: "项目服务暂时不可用，请稍后手动重试。",
        }),
      )
      .mockResolvedValueOnce(versionedResource());
    const reviseProject = vi.fn().mockRejectedValue(conflictError());
    renderConflict(detailClient(getProject, reviseProject));
    const controls = await makeDraftAndSave(user);
    await user.click(
      await screen.findByRole("button", { name: "读取最新版本" }),
    );
    expect(
      await screen.findByText("项目服务暂时不可用，请稍后手动重试。"),
    ).toBeVisible();
    expect(controls.title).toHaveValue("我的冲突草稿");
    await user.click(screen.getByRole("button", { name: "重试读取最新版本" }));
    expect(
      await screen.findByText("项目服务返回了无法安全读取的数据。"),
    ).toBeVisible();
    expect(controls.title).toHaveValue("我的冲突草稿");
    expect(reviseProject).toHaveBeenCalledOnce();
  });

  it("handles absent conflict diagnostics, safe retry diagnostics, and empty previews", async () => {
    const user = userEvent.setup();
    const getProject = vi
      .fn()
      .mockResolvedValueOnce(versionedResource())
      .mockRejectedValueOnce(
        new ProjectApiError({
          kind: "unavailable",
          code: "PROJECT_PERSISTENCE_UNAVAILABLE",
          message: "项目服务暂时不可用，请稍后手动重试。",
          requestId: "req_latest_safe",
        }),
      )
      .mockResolvedValueOnce(
        versionedResource(2, {
          title: "空简介最新版本",
          description: "",
        }),
      );
    const reviseProject = vi.fn().mockRejectedValue(conflictError(null));
    renderConflict(detailClient(getProject, reviseProject));
    const title = await screen.findByRole("textbox", { name: "项目标题" });
    const description = screen.getByRole("textbox", { name: "项目简介" });
    await user.clear(title);
    await user.type(title, "空简介本地草稿");
    await user.clear(description);
    await user.click(screen.getByRole("button", { name: "保存完整修订" }));

    const conflict = await screen.findByRole("alert");
    expect(conflict.querySelector(".request-id")).toBeNull();
    await user.click(
      within(conflict).getByRole("button", { name: "读取最新版本" }),
    );
    expect(
      await screen.findByText("项目服务暂时不可用，请稍后手动重试。"),
    ).toBeVisible();
    expect(conflict).toHaveTextContent("req_latest_safe");
    await user.click(screen.getByRole("button", { name: "重试读取最新版本" }));
    expect(await screen.findAllByText("暂无项目简介。")).toHaveLength(2);

    await user.click(
      screen.getByRole("button", {
        name: "放弃当前草稿并采用最新版本",
      }),
    );
    expect(screen.getByText("当前项目快照").parentElement).toHaveTextContent(
      "暂无项目简介。",
    );
  });
});
