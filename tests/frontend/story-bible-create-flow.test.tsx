import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { StoryBibleApiClient } from "../../frontend/src/features/story-bible/api/client";
import { StoryBiblePage } from "../../frontend/src/features/story-bible/pages/StoryBiblePage";
import {
  storyBibleClient,
  storyBibleError,
  storyProjectId,
  versionedStoryBible,
} from "./story-bible-support";

function renderStoryBible(
  client: StoryBibleApiClient,
  path = `/projects/${storyProjectId}/story-bible`,
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/projects/:projectId/story-bible"
          element={<StoryBiblePage client={client} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

function missingStoryBible() {
  return storyBibleError("story_bible_for_project_not_found", {
    code: "STORY_BIBLE_FOR_PROJECT_NOT_FOUND",
    message: "该项目尚未创建小说设定。",
  });
}

describe("小说设定 initial and create flow", () => {
  it("distinguishes loading, not-created, and Project-not-found states", async () => {
    const getStoryBibleForProject = vi
      .fn()
      .mockRejectedValue(missingStoryBible());
    const client = storyBibleClient({ getStoryBibleForProject });
    const first = renderStoryBible(client);
    expect(screen.getByRole("status")).toHaveTextContent("正在读取小说设定");
    expect(
      await screen.findByRole("heading", {
        name: "创建小说设定",
      }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "创建小说设定" })).toBeEnabled();
    expect(client.createStoryBible).not.toHaveBeenCalled();
    first.unmount();

    const notFoundClient = storyBibleClient({
      getStoryBibleForProject: vi.fn().mockRejectedValue(
        storyBibleError("project_not_found", {
          code: "PROJECT_NOT_FOUND",
          message: "指定项目不存在。",
          requestId: "req_project_missing",
        }),
      ),
    });
    const second = renderStoryBible(notFoundClient);
    expect(
      await screen.findByRole("heading", { name: "项目不存在" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "创建小说设定" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("请求编号：req_project_missing")).toBeVisible();
    second.unmount();
  });

  it("shows a safe load error and retries only after an explicit click", async () => {
    const user = userEvent.setup();
    const getStoryBibleForProject = vi
      .fn()
      .mockRejectedValueOnce(
        storyBibleError("unavailable", {
          message: "小说设定服务暂时不可用，请稍后手动重试。",
          requestId: "req_load_safe",
        }),
      )
      .mockRejectedValueOnce(missingStoryBible());
    renderStoryBible(storyBibleClient({ getStoryBibleForProject }));

    expect(
      await screen.findByRole("heading", {
        name: "无法读取小说设定",
      }),
    ).toBeVisible();
    expect(screen.getByText("请求编号：req_load_safe")).toBeVisible();
    expect(getStoryBibleForProject).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "重新加载" }));
    expect(
      await screen.findByRole("heading", {
        name: "创建小说设定",
      }),
    ).toBeVisible();
    expect(getStoryBibleForProject).toHaveBeenCalledTimes(2);
  });

  it("rejects an invalid route without any API call or hostile echo", async () => {
    const client = storyBibleClient();
    renderStoryBible(client, "/projects/bad%0Acanary/story-bible");
    expect(
      await screen.findByRole("heading", { name: "项目地址无效" }),
    ).toBeVisible();
    expect(client.getStoryBibleForProject).not.toHaveBeenCalled();
    expect(document.body).not.toHaveTextContent("canary");
  });

  it("validates fields before create and focuses the first invalid control", async () => {
    const user = userEvent.setup();
    const client = storyBibleClient({
      getStoryBibleForProject: vi.fn().mockRejectedValue(missingStoryBible()),
    });
    renderStoryBible(client);
    await user.click(
      await screen.findByRole("button", { name: "创建小说设定" }),
    );
    expect(screen.getByRole("textbox", { name: "设定标题" })).toHaveFocus();
    expect(screen.getByText("请输入小说设定标题。")).toBeVisible();
    expect(client.createStoryBible).not.toHaveBeenCalled();
  });

  it("creates once, adopts the POST resource directly, and becomes clean", async () => {
    const user = userEvent.setup();
    const createStoryBible = vi.fn().mockResolvedValue(
      versionedStoryBible(1, {
        title: "服务端规范标题",
        content: "服务端规范正文\n第二行",
      }),
    );
    const client = storyBibleClient({
      getStoryBibleForProject: vi.fn().mockRejectedValue(missingStoryBible()),
      createStoryBible,
    });
    renderStoryBible(client);
    const title = await screen.findByRole("textbox", {
      name: "设定标题",
    });
    const content = screen.getByRole("textbox", {
      name: "设定正文",
    });
    await user.type(title, "创建草稿");
    await user.type(content, "草稿正文");
    await user.click(screen.getByRole("button", { name: "创建小说设定" }));

    expect(
      await screen.findByRole("heading", { name: "服务端规范标题" }),
    ).toBeVisible();
    expect(createStoryBible).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        projectId: storyProjectId,
        title: "创建草稿",
        content: "草稿正文",
      }),
    );
    expect(client.getStoryBibleForProject).toHaveBeenCalledOnce();
    expect(screen.getByRole("textbox", { name: "小说设定标题" })).toHaveValue(
      "服务端规范标题",
    );
    expect(screen.getByText("当前没有未保存更改")).toBeVisible();
  });

  it.each([
    ["outcome_unknown", "创建结果未确认，请重新读取小说设定 核实。"],
    ["already_exists", "该项目已经存在小说设定，请重新读取。"],
  ] as const)(
    "preserves the draft and requires explicit verification for %s",
    async (kind, message) => {
      const user = userEvent.setup();
      const getStoryBibleForProject = vi
        .fn()
        .mockRejectedValueOnce(missingStoryBible())
        .mockResolvedValueOnce(
          versionedStoryBible(1, { title: "已核实服务端设定" }),
        );
      const createStoryBible = vi.fn().mockRejectedValue(
        storyBibleError(kind, {
          code:
            kind === "already_exists"
              ? "STORY_BIBLE_ALREADY_EXISTS_FOR_PROJECT"
              : "STORY_BIBLE_CREATE_OUTCOME_UNKNOWN",
          message,
        }),
      );
      const client = storyBibleClient({
        getStoryBibleForProject,
        createStoryBible,
      });
      renderStoryBible(client);
      const title = await screen.findByRole("textbox", {
        name: "设定标题",
      });
      await user.type(title, "必须保留的创建草稿");
      await user.click(screen.getByRole("button", { name: "创建小说设定" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(title).toHaveValue("必须保留的创建草稿");
      expect(createStoryBible).toHaveBeenCalledOnce();
      expect(getStoryBibleForProject).toHaveBeenCalledOnce();
      await Promise.resolve();
      expect(getStoryBibleForProject).toHaveBeenCalledOnce();

      await user.click(
        screen.getByRole("button", { name: "重新读取小说设定" }),
      );
      expect(
        await screen.findByRole("heading", { name: "已核实服务端设定" }),
      ).toBeVisible();
      expect(getStoryBibleForProject).toHaveBeenCalledTimes(2);
      expect(createStoryBible).toHaveBeenCalledOnce();
    },
  );

  it("restores create-ready with the same draft when verification still finds none", async () => {
    const user = userEvent.setup();
    const getStoryBibleForProject = vi
      .fn()
      .mockRejectedValueOnce(missingStoryBible())
      .mockRejectedValueOnce(missingStoryBible());
    const client = storyBibleClient({
      getStoryBibleForProject,
      createStoryBible: vi.fn().mockRejectedValue(
        storyBibleError("outcome_unknown", {
          message: "创建结果未确认，请重新读取小说设定 核实。",
        }),
      ),
    });
    renderStoryBible(client);
    const title = await screen.findByRole("textbox", {
      name: "设定标题",
    });
    await user.type(title, "核实后仍保留");
    await user.click(screen.getByRole("button", { name: "创建小说设定" }));
    await user.click(
      await screen.findByRole("button", { name: "重新读取小说设定" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "创建小说设定" }),
      ).toBeEnabled(),
    );
    expect(screen.getByRole("textbox", { name: "设定标题" })).toHaveValue(
      "核实后仍保留",
    );
  });

  it("keeps the draft and exposes a safe verification error for manual retry", async () => {
    const user = userEvent.setup();
    const getStoryBibleForProject = vi
      .fn()
      .mockRejectedValueOnce(missingStoryBible())
      .mockRejectedValueOnce(
        storyBibleError("unavailable", {
          message: "小说设定服务暂时不可用，请稍后手动重试。",
          requestId: "req_verify_safe",
        }),
      );
    const client = storyBibleClient({
      getStoryBibleForProject,
      createStoryBible: vi.fn().mockRejectedValue(
        storyBibleError("outcome_unknown", {
          message: "创建结果未确认，请重新读取小说设定 核实。",
        }),
      ),
    });
    renderStoryBible(client);
    const title = await screen.findByRole("textbox", {
      name: "设定标题",
    });
    await user.type(title, "核实失败仍保留");
    await user.click(screen.getByRole("button", { name: "创建小说设定" }));
    await user.click(
      await screen.findByRole("button", { name: "重新读取小说设定" }),
    );

    expect(
      await screen.findByText("小说设定服务暂时不可用，请稍后手动重试。"),
    ).toBeVisible();
    expect(screen.getByText("请求编号：req_verify_safe")).toBeVisible();
    expect(title).toHaveValue("核实失败仍保留");
    expect(getStoryBibleForProject).toHaveBeenCalledTimes(2);
  });
});
