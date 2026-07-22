import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function renderEditor(
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

async function inputs() {
  return {
    title: await screen.findByRole("textbox", { name: "项目标题" }),
    description: screen.getByRole("textbox", { name: "项目简介" }),
    save: screen.getByRole("button", { name: "保存完整修订" }),
  };
}

describe("Project revision edit form", () => {
  it("starts clean, tracks exact draft differences, and becomes clean when restored", async () => {
    const user = userEvent.setup();
    renderEditor(detailClient());
    const controls = await inputs();
    expect(controls.title).toHaveValue("项目版本1");
    expect(controls.description).toHaveValue("简介版本1");
    expect(controls.save).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("没有未保存更改");

    await user.type(controls.title, "补充");
    expect(controls.save).toBeEnabled();
    expect(screen.getByText("有未保存更改")).toBeVisible();
    await user.clear(controls.title);
    await user.type(controls.title, "项目版本1");
    expect(controls.save).toBeDisabled();

    await user.type(controls.description, "补充");
    expect(controls.save).toBeEnabled();
  });

  it("rejects invalid Unicode fields without calling the revision client", async () => {
    const user = userEvent.setup();
    const reviseProject = vi.fn();
    renderEditor(detailClient(undefined, reviseProject));
    const controls = await inputs();
    await user.clear(controls.title);
    await user.click(controls.save);
    expect(await screen.findByText("请输入项目标题。")).toBeVisible();
    expect(controls.title).toHaveFocus();
    expect(reviseProject).not.toHaveBeenCalled();

    fireEvent.change(controls.title, { target: { value: "😀".repeat(121) } });
    await user.click(controls.save);
    expect(
      await screen.findByText("项目标题不能超过120个字符。"),
    ).toBeVisible();
    expect(reviseProject).not.toHaveBeenCalled();

    fireEvent.change(controls.title, { target: { value: "有效标题" } });
    fireEvent.change(controls.description, {
      target: { value: "界".repeat(2_001) },
    });
    await user.click(controls.save);
    expect(
      await screen.findByText("项目简介不能超过2000个字符。"),
    ).toBeVisible();
    expect(controls.description).toHaveFocus();
    expect(reviseProject).not.toHaveBeenCalled();
  });

  it("locks a double submit to one PUT and adopts canonical success fields", async () => {
    const user = userEvent.setup();
    const pending = deferred<ReturnType<typeof versionedResource>>();
    const reviseProject = vi
      .fn<ProjectRevisionApiClient["reviseProject"]>()
      .mockReturnValue(pending.promise);
    renderEditor(detailClient(undefined, reviseProject));
    const controls = await inputs();
    await user.clear(controls.title);
    await user.type(controls.title, "本地草稿标题");
    await user.clear(controls.description);
    await user.type(controls.description, "本地草稿简介");
    await user.dblClick(controls.save);

    expect(reviseProject).toHaveBeenCalledOnce();
    const [submitted, options] = reviseProject.mock.calls[0] ?? [];
    expect(submitted).toEqual({
      projectId,
      etag: '"1"',
      title: "本地草稿标题",
      description: "本地草稿简介",
    });
    expect(options?.signal).toBeInstanceOf(AbortSignal);
    expect(
      screen.getByRole("button", { name: "正在保存修订…" }),
    ).toBeDisabled();
    pending.resolve(
      versionedResource(2, {
        title: "服务端规范标题",
        description: "服务端规范简介",
      }),
    );

    expect(await screen.findByText("项目修订已保存。")).toBeVisible();
    expect(controls.title).toHaveValue("服务端规范标题");
    expect(controls.description).toHaveValue("服务端规范简介");
    expect(screen.getByText("并发版本").nextElementSibling).toHaveTextContent(
      "2",
    );
    expect(screen.getByText("当前修订号").nextElementSibling).toHaveTextContent(
      "2",
    );
    expect(screen.getByRole("button", { name: "保存完整修订" })).toBeDisabled();
  });

  it("retains the draft and safely shows a service or field failure", async () => {
    const user = userEvent.setup();
    const reviseProject = vi.fn().mockRejectedValue(
      new ProjectApiError({
        kind: "validation",
        code: "INVALID_PROJECT_TITLE",
        message: "提交内容未通过服务端验证。",
        requestId: "req_revision",
        fieldErrors: [
          { field: "title", message: "项目标题未通过服务端验证。" },
        ],
      }),
    );
    renderEditor(detailClient(undefined, reviseProject));
    const controls = await inputs();
    await user.clear(controls.title);
    await user.type(controls.title, "保留草稿");
    await user.click(controls.save);

    expect(await screen.findByText("项目标题未通过服务端验证。")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("req_revision");
    expect(controls.title).toHaveValue("保留草稿");
    expect(controls.title).toHaveFocus();
  });

  it("focuses a description field rejected by the service", async () => {
    const user = userEvent.setup();
    const reviseProject = vi.fn().mockRejectedValue(
      new ProjectApiError({
        kind: "validation",
        code: "INVALID_PROJECT_REVISION",
        message: "提交内容未通过服务端验证。",
        fieldErrors: [
          { field: "description", message: "项目简介未通过服务端验证。" },
        ],
      }),
    );
    renderEditor(detailClient(undefined, reviseProject));
    const controls = await inputs();
    await user.type(controls.title, "修订");
    await user.click(controls.save);

    expect(
      await screen.findByRole("textbox", { name: "项目简介" }),
    ).toHaveFocus();
  });

  it("focuses generic feedback when the service names no field", async () => {
    const user = userEvent.setup();
    const reviseProject = vi.fn().mockRejectedValue(
      new ProjectApiError({
        kind: "validation",
        code: "INVALID_PROJECT_REVISION",
        message: "提交内容未通过服务端验证。",
      }),
    );
    renderEditor(detailClient(undefined, reviseProject));
    const controls = await inputs();
    await user.type(controls.title, "修订");
    await user.click(controls.save);

    expect(await screen.findByRole("alert")).toHaveFocus();
  });

  it("treats a lost PUT response as unknown, preserves the draft, and requires reload", async () => {
    const user = userEvent.setup();
    const getProject = vi
      .fn()
      .mockResolvedValueOnce(versionedResource())
      .mockResolvedValueOnce(
        versionedResource(2, {
          title: "服务端实际状态",
          description: "服务端已提交的简介",
        }),
      );
    const reviseProject = vi.fn().mockRejectedValue(
      new ProjectApiError({
        kind: "outcome_unknown",
        code: "PROJECT_REVISION_NETWORK_INTERRUPTED",
        message: "保存结果未确认，请重新加载项目核实。",
      }),
    );
    renderEditor(detailClient(getProject, reviseProject));
    const controls = await inputs();
    await user.clear(controls.title);
    await user.type(controls.title, "未确认草稿");
    await user.click(controls.save);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("保存结果未确认");
    expect(alert).not.toHaveTextContent(/保存成功|确定未保存/u);
    expect(controls.title).toHaveValue("未确认草稿");
    expect(screen.getByRole("button", { name: "保存完整修订" })).toBeDisabled();
    expect(reviseProject).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "重新加载项目" }));
    expect(
      await screen.findByRole("heading", { name: "服务端实际状态" }),
    ).toBeVisible();
    expect(screen.getByRole("textbox", { name: "项目标题" })).toHaveValue(
      "服务端实际状态",
    );
    expect(getProject).toHaveBeenCalledTimes(2);
    expect(reviseProject).toHaveBeenCalledOnce();
    await waitFor(() =>
      expect(screen.queryByText("保存结果未确认")).not.toBeInTheDocument(),
    );
  });
});
