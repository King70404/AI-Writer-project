import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { StoryBibleApiClient } from "../../frontend/src/features/story-bible/api/client";
import { StoryBiblePage } from "../../frontend/src/features/story-bible/pages/StoryBiblePage";
import {
  storyBibleClient,
  storyBibleError,
  storyBibleResponse,
  storyProjectId,
  versionedStoryBible,
} from "./story-bible-support";

function renderEditor(client: StoryBibleApiClient) {
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

describe("小说设定 ready editor", () => {
  it("shows saved times and editing controls without internal identifiers", async () => {
    const client = storyBibleClient();
    renderEditor(client);
    expect(
      await screen.findByRole("heading", { name: "设定集版本1" }),
    ).toBeVisible();
    const baseline = storyBibleResponse();
    expect(screen.getAllByRole("time")).toHaveLength(2);
    expect(
      screen.getByText("最近保存").nextElementSibling?.querySelector("time"),
    ).toHaveAttribute("datetime", baseline.updated_at);
    for (const id of [
      baseline.story_bible_id,
      baseline.project_id,
      baseline.current_revision_id,
    ])
      expect(document.body).not.toHaveTextContent(id);
    expect(document.body).not.toHaveTextContent(
      /Project编号|当前修订号|并发版本|Head更新时间/u,
    );
    expect(screen.getByRole("textbox", { name: "小说设定标题" })).toHaveValue(
      "设定集版本1",
    );
    expect(screen.getByRole("textbox", { name: "小说设定正文" })).toHaveValue(
      "设定正文版本1\n第二行",
    );
    expect(document.body).not.toHaveTextContent(
      /Character|World|PowerSystem|AI生成/u,
    );
  });

  it("saves one complete replacement and adopts the returned resource", async () => {
    const user = userEvent.setup();
    const reviseStoryBible = vi.fn().mockResolvedValue(
      versionedStoryBible(2, {
        title: "服务端保存标题",
        content: "服务端保存正文",
      }),
    );
    const client = storyBibleClient({ reviseStoryBible });
    renderEditor(client);
    const title = await screen.findByRole("textbox", {
      name: "小说设定标题",
    });
    const content = screen.getByRole("textbox", {
      name: "小说设定正文",
    });
    await user.clear(title);
    await user.type(title, "本地新标题");
    await user.clear(content);
    await user.type(content, "本地新正文\n下一行");
    expect(screen.getByText("有未保存更改")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "保存完整修订" }));

    expect(await screen.findByText("小说设定修订已保存。")).toBeVisible();
    expect(reviseStoryBible).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        etag: '"1"',
        title: "本地新标题",
        content: "本地新正文\n下一行",
      }),
    );
    expect(title).toHaveValue("服务端保存标题");
    expect(content).toHaveValue("服务端保存正文");
    expect(document.body).not.toHaveTextContent(/当前修订号|并发版本/u);
    await user.type(title, "再次保存");
    await user.click(screen.getByRole("button", { name: "保存完整修订" }));
    await waitFor(() => expect(reviseStoryBible).toHaveBeenCalledTimes(2));
    expect(reviseStoryBible).toHaveBeenLastCalledWith(
      expect.objectContaining({
        etag: '"2"',
        title: "服务端保存标题再次保存",
        content: "服务端保存正文",
      }),
    );
  });

  it("discards dirty text locally without any request", async () => {
    const user = userEvent.setup();
    const client = storyBibleClient();
    renderEditor(client);
    const content = await screen.findByRole("textbox", {
      name: "小说设定正文",
    });
    await user.clear(content);
    await user.type(content, "应放弃的草稿");
    await user.click(screen.getByRole("button", { name: "放弃未保存更改" }));
    expect(content).toHaveValue("设定正文版本1\n第二行");
    expect(
      await screen.findByText("已放弃未保存更改，并恢复当前基线内容。"),
    ).toBeVisible();
    expect(client.reviseStoryBible).not.toHaveBeenCalled();
  });

  it("keeps draft and baseline after a deterministic save error", async () => {
    const user = userEvent.setup();
    const reviseStoryBible = vi.fn().mockRejectedValue(
      storyBibleError("unavailable", {
        message: "小说设定服务暂时不可用，请稍后手动重试。",
        requestId: "req_save_safe",
      }),
    );
    renderEditor(storyBibleClient({ reviseStoryBible }));
    const title = await screen.findByRole("textbox", {
      name: "小说设定标题",
    });
    await user.clear(title);
    await user.type(title, "保留的失败草稿");
    await user.click(screen.getByRole("button", { name: "保存完整修订" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "小说设定服务暂时不可用",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("req_save_safe");
    expect(title).toHaveValue("保留的失败草稿");
    expect(document.body).not.toHaveTextContent(/当前修订号|并发版本/u);
    await user.click(screen.getByRole("button", { name: "放弃未保存更改" }));
    expect(title).toHaveValue("设定集版本1");
    expect(reviseStoryBible).toHaveBeenCalledOnce();
  });

  it("validates before save and prevents synchronous double submission", async () => {
    const user = userEvent.setup();
    let resolveSave!: (value: ReturnType<typeof versionedStoryBible>) => void;
    const pending = new Promise<ReturnType<typeof versionedStoryBible>>(
      (resolve) => {
        resolveSave = resolve;
      },
    );
    const reviseStoryBible = vi.fn().mockReturnValue(pending);
    renderEditor(storyBibleClient({ reviseStoryBible }));
    const title = await screen.findByRole("textbox", {
      name: "小说设定标题",
    });
    await user.clear(title);
    await user.click(screen.getByRole("button", { name: "保存完整修订" }));
    expect(screen.getByText("请输入小说设定标题。")).toBeVisible();
    expect(reviseStoryBible).not.toHaveBeenCalled();

    await user.type(title, "有效标题");
    const save = screen.getByRole("button", { name: "保存完整修订" });
    await user.click(save);
    expect(
      screen.getByRole("button", { name: "正在保存修订…" }),
    ).toBeDisabled();
    expect(reviseStoryBible).toHaveBeenCalledOnce();
    resolveSave(versionedStoryBible(2));
    await waitFor(() => expect(save).toBeDisabled());
  });
});
