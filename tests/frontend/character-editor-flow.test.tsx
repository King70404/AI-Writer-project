import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { CharacterApiClient } from "../../frontend/src/features/character/api/client";
import { CharacterEditorPage } from "../../frontend/src/features/character/pages/CharacterEditorPage";
import {
  characterClient,
  characterError,
  characterId,
  characterProjectId,
  secondCharacterProjectId,
  versionedCharacter,
} from "./character-support";

function renderEditor(
  client: CharacterApiClient,
  projectId = characterProjectId,
  id = characterId,
) {
  return render(
    <MemoryRouter initialEntries={[`/projects/${projectId}/characters/${id}`]}>
      <Routes>
        <Route
          path="/projects/:projectId/characters/:characterId"
          element={<CharacterEditorPage client={client} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

async function changeProfile(user: ReturnType<typeof userEvent.setup>) {
  const profile = await screen.findByLabelText("角色档案（纯文本）");
  await user.clear(profile);
  await user.type(profile, "本地完整新草稿");
}

describe("Character current editor", () => {
  it("loads one trusted baseline, displays all metadata, and starts clean", async () => {
    const client = characterClient();
    renderEditor(client);
    expect(await screen.findByRole("heading", { name: "林砚" })).toBeVisible();
    expect(screen.getByText(characterId)).toBeVisible();
    expect(screen.getByText("crv_01ARZ3NDEKTSV4RRFFQ69G5FAV")).toBeVisible();
    expect(screen.getByText("当前没有未保存更改")).toBeVisible();
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
    expect(client.getCharacter).toHaveBeenCalledOnce();
    expect(client.listCharacters).not.toHaveBeenCalled();
  });

  it("saves one complete replacement without a pre-GET, then adopts PUT response and ETag", async () => {
    const revise = vi.fn().mockResolvedValue(
      versionedCharacter(2, {
        name: "林砚二版",
        role: "",
        profile: "本地完整新草稿",
      }),
    );
    const client = characterClient({ reviseCharacter: revise });
    const user = userEvent.setup();
    renderEditor(client);
    await changeProfile(user);
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByText("角色修订已保存。")).toBeVisible();
    expect(revise).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        etag: '"1"',
        profile: "本地完整新草稿",
      }),
    );
    expect(client.getCharacter).toHaveBeenCalledOnce();
    expect(screen.getByText("当前没有未保存更改")).toBeVisible();
    expect(screen.getAllByText("2")).toHaveLength(2);
  });

  it("discards only in memory without a request", async () => {
    const client = characterClient();
    const user = userEvent.setup();
    renderEditor(client);
    await changeProfile(user);
    await user.click(screen.getByRole("button", { name: "放弃未保存更改" }));
    expect(screen.getByLabelText("角色档案（纯文本）")).toHaveValue(
      "秘密档案\n第二行",
    );
    expect(client.reviseCharacter).not.toHaveBeenCalled();
  });

  it("validates editor fields, focuses the first error, and clears feedback on edits", async () => {
    const client = characterClient();
    const user = userEvent.setup();
    renderEditor(client);
    const name = await screen.findByLabelText("角色名称");
    await user.clear(name);
    const role = screen.getByLabelText("角色定位");
    await user.clear(role);
    await user.type(role, "新定位");
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(name).toHaveFocus();
    expect(screen.getByText(/角色名称必填/u)).toBeVisible();
    expect(client.reviseCharacter).not.toHaveBeenCalled();
    await user.type(name, "新名称");
    expect(screen.queryByText(/角色名称必填/u)).not.toBeInTheDocument();
  });

  it("preserves draft, baseline, and dirty state after a deterministic failure", async () => {
    const revise = vi.fn().mockRejectedValue(characterError("validation"));
    const user = userEvent.setup();
    renderEditor(characterClient({ reviseCharacter: revise }));
    await changeProfile(user);
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("角色安全错误");
    expect(screen.getByLabelText("角色档案（纯文本）")).toHaveValue(
      "本地完整新草稿",
    );
    expect(screen.getByText("有未保存更改")).toBeVisible();
  });

  it("focuses a 412 conflict and waits for explicit latest GET and resolution", async () => {
    const conflict = characterError("version_conflict", {
      conflict: {
        expectedVersion: 1,
        actualVersion: 2,
        requestId: "req_conflict",
      },
    });
    const get = vi
      .fn()
      .mockResolvedValueOnce(versionedCharacter())
      .mockResolvedValueOnce(
        versionedCharacter(2, {
          name: "服务器角色",
          profile: "服务器最新秘密",
        }),
      );
    const client = characterClient({
      getCharacter: get,
      reviseCharacter: vi.fn().mockRejectedValue(conflict),
    });
    const user = userEvent.setup();
    renderEditor(client);
    await changeProfile(user);
    await user.click(screen.getByRole("button", { name: "保存" }));
    const heading = await screen.findByRole("heading", {
      name: "检测到版本冲突",
    });
    expect(heading).toHaveFocus();
    expect(screen.getByText(/提交版本 1，服务器当前版本 2/u)).toBeVisible();
    expect(get).toHaveBeenCalledOnce();
    expect(screen.queryByText("服务器最新秘密")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "读取服务器最新版本" }),
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/已读取服务器版本 2/u)).toBeVisible();
    expect(screen.queryByText("服务器最新秘密")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "保留草稿并重建基线" }),
    );
    expect(screen.getByLabelText("角色档案（纯文本）")).toHaveValue(
      "本地完整新草稿",
    );
    expect(screen.getByText(/下次手动保存会完整替换/u)).toBeVisible();
    expect(client.reviseCharacter).toHaveBeenCalledOnce();
  });

  it("can explicitly adopt the latest server version without a PUT", async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(versionedCharacter())
      .mockResolvedValueOnce(
        versionedCharacter(2, {
          name: "服务器角色",
          profile: "服务器最新秘密",
        }),
      );
    const revise = vi
      .fn()
      .mockRejectedValue(characterError("write_outcome_unknown"));
    const user = userEvent.setup();
    renderEditor(
      characterClient({ getCharacter: get, reviseCharacter: revise }),
    );
    await changeProfile(user);
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(
      await screen.findByRole("heading", { name: "保存结果无法确认" }),
    ).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "读取服务器最新版本" }),
    );
    await screen.findByText(/已读取服务器版本 2/u);
    await user.click(screen.getByRole("button", { name: "采用服务器版本" }));
    expect(screen.getByLabelText("角色档案（纯文本）")).toHaveValue(
      "服务器最新秘密",
    );
    expect(screen.getByText("已采用服务器版本，未执行保存。")).toBeVisible();
    expect(revise).toHaveBeenCalledOnce();
  });

  it("shows an explicit latest-read error and permits a manual retry", async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(versionedCharacter())
      .mockRejectedValueOnce(characterError("network"))
      .mockResolvedValueOnce(versionedCharacter(2));
    const user = userEvent.setup();
    renderEditor(
      characterClient({
        getCharacter: get,
        reviseCharacter: vi
          .fn()
          .mockRejectedValue(characterError("write_outcome_unknown")),
      }),
    );
    await changeProfile(user);
    await user.click(screen.getByRole("button", { name: "保存" }));
    await user.click(
      await screen.findByRole("button", { name: "读取服务器最新版本" }),
    );
    expect(await screen.findByText("角色安全错误。")).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "读取服务器最新版本" }),
    );
    expect(await screen.findByText(/已读取服务器版本 2/u)).toBeVisible();
  });

  it("uses the latest ETag only after rebase and a second manual save", async () => {
    const get = vi
      .fn()
      .mockResolvedValueOnce(versionedCharacter())
      .mockResolvedValueOnce(versionedCharacter(2));
    const revise = vi
      .fn()
      .mockRejectedValueOnce(
        characterError("version_conflict", {
          conflict: {
            expectedVersion: 1,
            actualVersion: 2,
            requestId: null,
          },
        }),
      )
      .mockResolvedValueOnce(
        versionedCharacter(3, { profile: "本地完整新草稿" }),
      );
    const user = userEvent.setup();
    renderEditor(
      characterClient({ getCharacter: get, reviseCharacter: revise }),
    );
    await changeProfile(user);
    await user.click(screen.getByRole("button", { name: "保存" }));
    await user.click(
      await screen.findByRole("button", { name: "读取服务器最新版本" }),
    );
    await screen.findByText(/已读取服务器版本 2/u);
    await user.click(
      screen.getByRole("button", { name: "保留草稿并重建基线" }),
    );
    await user.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(revise).toHaveBeenCalledTimes(2));
    expect(revise).toHaveBeenLastCalledWith(
      expect.objectContaining({ etag: '"2"' }),
    );
  });

  it("rejects invalid routes, missing characters, and Project ownership mismatch", async () => {
    const invalidClient = characterClient();
    const invalid = renderEditor(invalidClient, "bad", "also-bad");
    expect(screen.getByText("角色地址无效")).toBeVisible();
    expect(invalidClient.getCharacter).not.toHaveBeenCalled();
    invalid.unmount();

    const missing = renderEditor(
      characterClient({
        getCharacter: vi
          .fn()
          .mockRejectedValue(characterError("character_not_found")),
      }),
    );
    expect(await screen.findByText("角色不存在")).toBeVisible();
    missing.unmount();

    renderEditor(
      characterClient({
        getCharacter: vi.fn().mockResolvedValue(
          versionedCharacter(1, {
            project_id: secondCharacterProjectId,
          }),
        ),
      }),
    );
    expect(await screen.findByText("Project归属不匹配")).toBeVisible();
    expect(screen.queryByText("秘密档案")).not.toBeInTheDocument();
  });
});
