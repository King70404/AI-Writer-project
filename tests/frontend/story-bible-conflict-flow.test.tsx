import { render, screen, waitFor, within } from "@testing-library/react";
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

function renderFlow(client: StoryBibleApiClient) {
  return render(
    <MemoryRouter initialEntries={[`/projects/${storyProjectId}/story-bible`]}>
      <Routes>
        <Route
          path="/projects/:projectId/story-bible"
          element={<StoryBiblePage client={client} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

function conflictError() {
  return storyBibleError("conflict", {
    code: "STORY_BIBLE_VERSION_CONFLICT",
    message:
      "小说设定已被其他操作修订。草稿已保留，请读取最新版本后选择处理方式。",
    requestId: "req_conflict_safe",
    conflict: { expectedVersion: 1, actualVersion: 2 },
  });
}

async function makeDraftAndSave(user: ReturnType<typeof userEvent.setup>) {
  const title = await screen.findByRole("textbox", {
    name: "小说设定标题",
  });
  const content = screen.getByRole("textbox", {
    name: "小说设定正文",
  });
  await user.clear(title);
  await user.type(title, "我的冲突草稿");
  await user.clear(content);
  await user.type(content, "我的草稿正文\n第二行");
  await user.click(screen.getByRole("button", { name: "保存完整修订" }));
  return { title, content };
}

describe("小说设定 explicit conflict and unknown-outcome flow", () => {
  it("enters 412 conflict, focuses the heading, and does not auto-GET or replay", async () => {
    const user = userEvent.setup();
    const getStoryBible = vi.fn().mockResolvedValue(versionedStoryBible(2));
    const reviseStoryBible = vi.fn().mockRejectedValue(conflictError());
    renderFlow(storyBibleClient({ getStoryBible, reviseStoryBible }));
    const controls = await makeDraftAndSave(user);
    const alert = await screen.findByRole("alert");
    expect(
      within(alert).getByRole("heading", {
        name: "检测到小说设定版本冲突",
      }),
    ).toHaveFocus();
    expect(alert).toHaveTextContent("版本 1");
    expect(alert).toHaveTextContent("版本 2");
    expect(alert).toHaveTextContent("req_conflict_safe");
    expect(controls.title).toHaveValue("我的冲突草稿");
    expect(controls.content).toHaveValue("我的草稿正文\n第二行");
    expect(screen.getByRole("button", { name: "保存完整修订" })).toBeDisabled();
    expect(getStoryBible).not.toHaveBeenCalled();
    expect(reviseStoryBible).toHaveBeenCalledOnce();
    await Promise.resolve();
    expect(getStoryBible).not.toHaveBeenCalled();
  });

  it("loads latest only on demand and adopts it without a PUT", async () => {
    const user = userEvent.setup();
    const getStoryBible = vi.fn().mockResolvedValue(
      versionedStoryBible(2, {
        title: "服务器版本2",
        content: "服务器正文2",
      }),
    );
    const reviseStoryBible = vi.fn().mockRejectedValue(conflictError());
    renderFlow(storyBibleClient({ getStoryBible, reviseStoryBible }));
    await makeDraftAndSave(user);
    await user.click(
      await screen.findByRole("button", { name: "读取最新版本" }),
    );
    expect(await screen.findByText("服务器版本2")).toBeVisible();
    expect(screen.getByText("我的冲突草稿")).toBeVisible();
    expect(getStoryBible).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        expectedProjectId: storyProjectId,
      }),
    );
    await user.click(screen.getByRole("button", { name: "采用服务器版本" }));
    expect(screen.getByRole("textbox", { name: "小说设定标题" })).toHaveValue(
      "服务器版本2",
    );
    expect(
      await screen.findByText("已放弃当前草稿并采用服务器最新版本。"),
    ).toBeVisible();
    expect(reviseStoryBible).toHaveBeenCalledOnce();
  });

  it("rebases the local draft and requires a second manual save with ETag 2", async () => {
    const user = userEvent.setup();
    const getStoryBible = vi.fn().mockResolvedValue(
      versionedStoryBible(2, {
        title: "服务器版本2",
        content: "服务器正文2",
      }),
    );
    const reviseStoryBible = vi
      .fn()
      .mockRejectedValueOnce(conflictError())
      .mockResolvedValueOnce(
        versionedStoryBible(3, {
          title: "我的冲突草稿",
          content: "我的草稿正文\n第二行",
        }),
      );
    renderFlow(storyBibleClient({ getStoryBible, reviseStoryBible }));
    const controls = await makeDraftAndSave(user);
    await user.click(
      await screen.findByRole("button", { name: "读取最新版本" }),
    );
    await user.click(
      screen.getByRole("button", {
        name: "保留草稿并以服务器版本建立基线",
      }),
    );
    expect(controls.title).toHaveValue("我的冲突草稿");
    expect(controls.content).toHaveValue("我的草稿正文\n第二行");
    expect(
      await screen.findByText(
        "当前草稿将在下次手动保存时完整替换服务器上的标题和正文。",
      ),
    ).toBeVisible();
    expect(reviseStoryBible).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "保存完整修订" }));
    await waitFor(() => expect(reviseStoryBible).toHaveBeenCalledTimes(2));
    expect(reviseStoryBible.mock.calls[1]?.[0]).toMatchObject({
      etag: '"2"',
      title: "我的冲突草稿",
      content: "我的草稿正文\n第二行",
    });
    expect(await screen.findByText("小说设定修订已保存。")).toBeVisible();
  });

  it("keeps the conflict and draft when explicit latest GET fails", async () => {
    const user = userEvent.setup();
    const getStoryBible = vi
      .fn()
      .mockRejectedValueOnce(
        storyBibleError("unavailable", {
          message: "小说设定服务暂时不可用，请稍后手动重试。",
        }),
      )
      .mockResolvedValueOnce(versionedStoryBible(1));
    renderFlow(
      storyBibleClient({
        getStoryBible,
        reviseStoryBible: vi.fn().mockRejectedValue(conflictError()),
      }),
    );
    const controls = await makeDraftAndSave(user);
    await user.click(
      await screen.findByRole("button", { name: "读取最新版本" }),
    );
    expect(
      await screen.findByText("小说设定服务暂时不可用，请稍后手动重试。"),
    ).toBeVisible();
    expect(controls.title).toHaveValue("我的冲突草稿");
    await user.click(screen.getByRole("button", { name: "重试读取最新版本" }));
    expect(
      await screen.findByText("小说设定服务返回了无法安全读取的数据。"),
    ).toBeVisible();
    expect(controls.title).toHaveValue("我的冲突草稿");
  });

  it("uses the same explicit resolution flow for save outcome unknown", async () => {
    const user = userEvent.setup();
    const getStoryBible = vi.fn().mockResolvedValue(
      versionedStoryBible(2, {
        title: "实际服务器版本",
        content: "实际服务器正文",
      }),
    );
    const reviseStoryBible = vi.fn().mockRejectedValue(
      storyBibleError("outcome_unknown", {
        code: "STORY_BIBLE_SAVE_OUTCOME_UNKNOWN",
        message: "保存结果未确认，请重新读取小说设定 核实。",
      }),
    );
    renderFlow(storyBibleClient({ getStoryBible, reviseStoryBible }));
    const controls = await makeDraftAndSave(user);
    const alert = await screen.findByRole("alert");
    expect(
      within(alert).getByRole("heading", {
        name: "小说设定保存结果未确认",
      }),
    ).toHaveFocus();
    expect(controls.title).toHaveValue("我的冲突草稿");
    expect(getStoryBible).not.toHaveBeenCalled();
    await user.click(
      within(alert).getByRole("button", { name: "读取最新版本" }),
    );
    expect(await screen.findByText("实际服务器版本")).toBeVisible();
    expect(controls.title).toHaveValue("我的冲突草稿");
    expect(reviseStoryBible).toHaveBeenCalledOnce();
  });
});
