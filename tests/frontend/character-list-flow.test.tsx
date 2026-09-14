import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { CharacterApiClient } from "../../frontend/src/features/character/api/client";
import { CharacterListPage } from "../../frontend/src/features/character/pages/CharacterListPage";
import {
  characterClient,
  characterError,
  characterId,
  characterListItem,
  characterPage,
  characterProjectId,
  olderCharacterTimestamp,
  secondCharacterId,
  versionedCharacter,
} from "./character-support";

function renderList(
  client: CharacterApiClient,
  projectId = characterProjectId,
) {
  return render(
    <MemoryRouter initialEntries={[`/projects/${projectId}/characters`]}>
      <Routes>
        <Route
          path="/projects/:projectId/characters"
          element={<CharacterListPage client={client} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Character list and create flow", () => {
  it("keeps explicit create and pagination operations disabled while in flight", async () => {
    let resolveCreate:
      ((value: ReturnType<typeof versionedCharacter>) => void) | undefined;
    let resolveMore:
      ((value: ReturnType<typeof characterPage>) => void) | undefined;
    const create = vi.fn(
      () =>
        new Promise<ReturnType<typeof versionedCharacter>>((resolve) => {
          resolveCreate = resolve;
        }),
    );
    const list = vi
      .fn<CharacterApiClient["listCharacters"]>()
      .mockResolvedValueOnce(
        characterPage({ next_cursor: "pending", has_more: true }),
      )
      .mockImplementationOnce(
        () =>
          new Promise<ReturnType<typeof characterPage>>((resolve) => {
            resolveMore = resolve;
          }),
      );
    const user = userEvent.setup();
    renderList(
      characterClient({ createCharacter: create, listCharacters: list }),
    );
    await screen.findByText("林砚");
    await user.type(screen.getByLabelText("角色名称"), "待定角色");
    await user.click(screen.getByRole("button", { name: "创建角色" }));
    expect(screen.getByRole("button", { name: "正在创建…" })).toBeDisabled();
    resolveCreate?.(
      versionedCharacter(1, {
        character_id: secondCharacterId,
        current_revision_id: "crv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
        name: "待定角色",
        created_at: "2026-07-31T08:30:00Z",
        updated_at: "2026-07-31T08:30:00Z",
        revision_created_at: "2026-07-31T08:30:00Z",
        head_updated_at: "2026-07-31T08:30:00Z",
      }),
    );
    await screen.findByText("角色创建成功。");
    await user.click(screen.getByRole("button", { name: "加载更多" }));
    expect(
      screen.getByRole("button", { name: "正在加载更多…" }),
    ).toBeDisabled();
    resolveMore?.(characterPage());
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("shows initial loading, an empty Project, and an accessible create form", async () => {
    const client = characterClient({
      listCharacters: vi.fn().mockResolvedValue(characterPage({ items: [] })),
    });
    renderList(client);
    expect(screen.getByRole("status")).toHaveTextContent("正在读取角色");
    expect(await screen.findByText("这部小说尚未创建角色。")).toBeVisible();
    expect(screen.getByLabelText("角色名称")).toBeVisible();
    expect(client.listCharacters).toHaveBeenCalledOnce();
  });

  it("preserves service order, same names, empty role, and never renders profiles", async () => {
    const items = [
      characterListItem({ name: "同名角色" }),
      characterListItem({
        character_id: secondCharacterId,
        current_revision_id: "crv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
        name: "同名角色",
        role: "",
        created_at: olderCharacterTimestamp,
        updated_at: olderCharacterTimestamp,
      }),
    ];
    renderList(
      characterClient({
        listCharacters: vi.fn().mockResolvedValue(characterPage({ items })),
      }),
    );
    expect(await screen.findAllByText("同名角色")).toHaveLength(2);
    expect(screen.getByText("未填写角色定位")).toBeVisible();
    expect(screen.queryByText("秘密档案")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/修订号|并发版本/u);
    for (const entry of items) {
      expect(document.body).not.toHaveTextContent(entry.character_id);
      expect(document.body).not.toHaveTextContent(entry.current_revision_id);
    }
    const links = screen.getAllByRole("link", { name: /查看角色：同名角色/u });
    expect(links[0]).toHaveAttribute(
      "href",
      `/projects/${characterProjectId}/characters/${characterId}`,
    );
    expect(links[1]).toHaveAttribute(
      "href",
      `/projects/${characterProjectId}/characters/${secondCharacterId}`,
    );
  });

  it("loads one next page on explicit click and appends it", async () => {
    const list = vi
      .fn()
      .mockResolvedValueOnce(
        characterPage({ next_cursor: "opaque-one", has_more: true }),
      )
      .mockResolvedValueOnce(
        characterPage({
          items: [
            characterListItem({
              character_id: secondCharacterId,
              current_revision_id: "crv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
              name: "第二页角色",
              created_at: olderCharacterTimestamp,
              updated_at: olderCharacterTimestamp,
            }),
          ],
        }),
      );
    const user = userEvent.setup();
    renderList(characterClient({ listCharacters: list }));
    await user.click(await screen.findByRole("button", { name: "加载更多" }));
    expect(await screen.findByText("第二页角色")).toBeVisible();
    expect(list).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ cursor: "opaque-one" }),
    );
    expect(
      screen.queryByRole("button", { name: "加载更多" }),
    ).not.toBeInTheDocument();
  });

  it("retains the first page and cursor after a pagination failure", async () => {
    const list = vi
      .fn()
      .mockResolvedValueOnce(
        characterPage({ next_cursor: "same-cursor", has_more: true }),
      )
      .mockRejectedValueOnce(characterError("network"))
      .mockResolvedValueOnce(characterPage());
    const user = userEvent.setup();
    renderList(characterClient({ listCharacters: list }));
    await user.click(await screen.findByRole("button", { name: "加载更多" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("角色安全错误");
    expect(screen.getByText("林砚")).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "使用同一分页位置重试" }),
    );
    await waitFor(() => expect(list).toHaveBeenCalledTimes(3));
    expect(list).toHaveBeenLastCalledWith(
      expect.objectContaining({ cursor: "same-cursor" }),
    );
  });

  it("clears an invalid cursor only through explicit first-page reload", async () => {
    const list = vi
      .fn()
      .mockResolvedValueOnce(
        characterPage({ next_cursor: "invalid-cursor", has_more: true }),
      )
      .mockRejectedValueOnce(characterError("invalid_cursor"))
      .mockResolvedValueOnce(characterPage());
    const user = userEvent.setup();
    renderList(characterClient({ listCharacters: list }));
    await user.click(await screen.findByRole("button", { name: "加载更多" }));
    await user.click(
      await screen.findByRole("button", { name: "重新加载第一页" }),
    );
    await waitFor(() => expect(list).toHaveBeenCalledTimes(3));
    expect(list.mock.lastCall?.[0]).not.toHaveProperty("cursor");
  });

  it("creates once, normalizes input, inserts a profile-free summary, and links without navigation", async () => {
    const create = vi.fn().mockResolvedValue(
      versionedCharacter(1, {
        character_id: secondCharacterId,
        current_revision_id: "crv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
        name: "新角色",
        role: "",
        profile: "不应出现在列表DOM",
        created_at: "2026-07-31T08:30:00Z",
        updated_at: "2026-07-31T08:30:00Z",
        revision_created_at: "2026-07-31T08:30:00Z",
        head_updated_at: "2026-07-31T08:30:00Z",
      }),
    );
    const user = userEvent.setup();
    renderList(characterClient({ createCharacter: create }));
    await screen.findByText("林砚");
    await user.type(screen.getByLabelText("角色名称"), " 新角色 ");
    await user.type(screen.getByLabelText("角色定位"), " 新定位 ");
    await user.type(
      screen.getByLabelText("角色档案（纯文本）"),
      "第一行{enter}第二行",
    );
    await user.click(screen.getByRole("button", { name: "创建角色" }));
    expect(await screen.findByText("角色创建成功。")).toBeVisible();
    expect(create).toHaveBeenCalledOnce();
    expect(screen.queryByText("不应出现在列表DOM")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看新角色" })).toHaveAttribute(
      "href",
      `/projects/${characterProjectId}/characters/${secondCharacterId}`,
    );
    expect(screen.getByLabelText("角色名称")).toHaveValue("");
  });

  it("focuses the first invalid field and never invokes create", async () => {
    const create = vi.fn();
    const user = userEvent.setup();
    renderList(characterClient({ createCharacter: create }));
    await screen.findByText("林砚");
    await user.click(screen.getByRole("button", { name: "创建角色" }));
    expect(screen.getByLabelText("角色名称")).toHaveFocus();
    expect(create).not.toHaveBeenCalled();
  });

  it("keeps draft and list on 409 and allows a new explicit user attempt", async () => {
    const create = vi
      .fn()
      .mockRejectedValueOnce(characterError("character_id_conflict"))
      .mockResolvedValueOnce(
        versionedCharacter(1, {
          name: "重试角色",
          created_at: "2026-07-31T08:30:00Z",
          updated_at: "2026-07-31T08:30:00Z",
          revision_created_at: "2026-07-31T08:30:00Z",
          head_updated_at: "2026-07-31T08:30:00Z",
        }),
      );
    const user = userEvent.setup();
    renderList(characterClient({ createCharacter: create }));
    await screen.findByText("林砚");
    await user.type(screen.getByLabelText("角色名称"), "重试角色");
    await user.type(screen.getByLabelText("角色档案（纯文本）"), "保留草稿");
    await user.click(screen.getByRole("button", { name: "创建角色" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("角色安全错误");
    expect(screen.getByLabelText("角色档案（纯文本）")).toHaveValue("保留草稿");
    await user.click(screen.getByRole("button", { name: "创建角色" }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
  });

  it("requires list verification and explicit acknowledgement before resubmitting an unknown outcome", async () => {
    const create = vi
      .fn()
      .mockRejectedValueOnce(characterError("write_outcome_unknown"))
      .mockResolvedValueOnce(
        versionedCharacter(1, {
          name: "未知结果角色",
          created_at: "2026-07-31T08:30:00Z",
          updated_at: "2026-07-31T08:30:00Z",
          revision_created_at: "2026-07-31T08:30:00Z",
          head_updated_at: "2026-07-31T08:30:00Z",
        }),
      );
    const list = vi.fn().mockResolvedValue(characterPage());
    const user = userEvent.setup();
    renderList(
      characterClient({ createCharacter: create, listCharacters: list }),
    );
    await screen.findByText("林砚");
    await user.type(screen.getByLabelText("角色名称"), "未知结果角色");
    await user.click(screen.getByRole("button", { name: "创建角色" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("角色安全错误");
    expect(screen.getByRole("button", { name: "创建角色" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "重新读取角色列表" }));
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    await user.click(
      screen.getByRole("button", { name: "我已确认需要再次提交" }),
    );
    expect(screen.getByRole("button", { name: "创建角色" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "创建角色" }));
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
  });

  it("distinguishes invalid Project, missing Project, and generic errors", async () => {
    const invalid = characterClient();
    const first = renderList(invalid, "bad");
    expect(screen.getByText("Project编号无效")).toBeVisible();
    expect(invalid.listCharacters).not.toHaveBeenCalled();
    first.unmount();

    const missing = characterClient({
      listCharacters: vi
        .fn()
        .mockRejectedValue(characterError("project_not_found")),
    });
    const second = renderList(missing);
    expect(await screen.findByText("Project不存在")).toBeVisible();
    second.unmount();

    const generic = characterClient({
      listCharacters: vi.fn().mockRejectedValue(characterError("network")),
    });
    renderList(generic);
    expect(await screen.findByText("角色请求未完成")).toBeVisible();
  });
});
