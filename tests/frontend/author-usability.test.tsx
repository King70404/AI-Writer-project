import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CharacterEditorPage } from "../../frontend/src/features/character/pages/CharacterEditorPage";
import { CharacterListPage } from "../../frontend/src/features/character/pages/CharacterListPage";
import { ProjectApiError } from "../../frontend/src/features/projects/api/errors";
import { ProjectDetailsPage } from "../../frontend/src/features/projects/pages/ProjectDetailsPage";
import {
  characterClient,
  characterListItem,
  characterPage,
  characterProjectId,
  secondCharacterId,
  versionedCharacter,
} from "./character-support";
import {
  detailClient,
  projectId,
  versionedResource,
} from "./project-detail-support";

afterEach(() => vi.restoreAllMocks());

describe("Author usability regressions", () => {
  it.each(["not_found", "unavailable"] as const)(
    "hides all creation and history links when the novel is %s",
    async (kind) => {
      const client = detailClient(
        vi.fn().mockRejectedValue(
          new ProjectApiError({
            kind,
            code:
              kind === "not_found"
                ? "PROJECT_NOT_FOUND"
                : "SERVICE_UNAVAILABLE",
            message: "小说不可用。",
          }),
        ),
      );
      render(
        <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
          <Routes>
            <Route
              path="/projects/:projectId"
              element={<ProjectDetailsPage client={client} />}
            />
          </Routes>
        </MemoryRouter>,
      );
      await screen.findByRole("alert");
      for (const name of ["历史版本", "人物", "小说设定", "大纲与章节"]) {
        expect(screen.queryByRole("link", { name })).not.toBeInTheDocument();
      }
      expect(
        screen.queryByRole("button", { name: "导出小说" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "删除小说" }),
      ).not.toBeInTheDocument();
      expect(client.getProject).toHaveBeenCalledOnce();
    },
  );

  it("requires the exact title, sends one deletion, and hides history after revisiting the deleted novel", async () => {
    const user = userEvent.setup();
    let deleted = false;
    const baseClient = detailClient(
      vi.fn().mockImplementation(() => {
        if (deleted)
          return Promise.reject(
            new ProjectApiError({
              kind: "not_found",
              code: "PROJECT_NOT_FOUND",
              message: "小说已删除。",
            }),
          );
        return Promise.resolve(versionedResource());
      }),
    );
    let finishDelete!: () => void;
    const deleteProject = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finishDelete = () => {
            deleted = true;
            resolve();
          };
        }),
    );
    const client = { ...baseClient, deleteProject };
    render(
      <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
        <Routes>
          <Route
            path="/projects/:projectId"
            element={<ProjectDetailsPage client={client} />}
          />
          <Route
            path="/projects"
            element={
              <>
                <h2>我的小说列表</h2>
                <Link to={`/projects/${projectId}`}>重新访问旧地址</Link>
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("link", { name: "历史版本" }),
    ).toHaveAttribute("href", `/projects/${projectId}/history`);
    const confirmation = screen.getByRole("textbox", { name: "确认书名" });
    await user.type(confirmation, "项目版本1 ");
    expect(screen.getByRole("button", { name: "删除小说" })).toBeDisabled();
    expect(client.deleteProject).not.toHaveBeenCalled();
    await user.clear(confirmation);
    await user.type(confirmation, "项目版本1");
    await user.dblClick(screen.getByRole("button", { name: "删除小说" }));
    expect(client.deleteProject).toHaveBeenCalledExactlyOnceWith({
      projectId,
      etag: '"1"',
    });
    expect(screen.getByRole("button", { name: "正在删除…" })).toBeDisabled();
    finishDelete();
    await screen.findByRole("heading", { name: "我的小说列表" });
    expect(
      screen.queryByRole("link", { name: "历史版本" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "重新访问旧地址" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("小说已删除。");
    expect(
      screen.queryByRole("link", { name: "历史版本" }),
    ).not.toBeInTheDocument();
    expect(client.getProject).toHaveBeenCalledTimes(2);
    expect(client.deleteProject).toHaveBeenCalledOnce();
  });

  it("starts character creation empty with autocomplete disabled on the form and every input", async () => {
    const client = characterClient();
    render(
      <MemoryRouter
        initialEntries={[`/projects/${characterProjectId}/characters`]}
      >
        <Routes>
          <Route
            path="/projects/:projectId/characters"
            element={<CharacterListPage client={client} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText("林砚");
    const fields = [
      ["角色名称", "new-character-name"],
      ["角色定位", "new-character-role"],
      ["角色档案（纯文本）", "new-character-profile"],
    ];
    for (const [label, name] of fields) {
      const field = screen.getByLabelText(label);
      expect(field).toHaveValue("");
      expect(field).toHaveAttribute("autocomplete", "off");
      expect(field).toHaveAttribute("name", name);
      expect(field.closest("form")).toHaveAttribute("autocomplete", "off");
    }
    expect(client.createCharacter).not.toHaveBeenCalled();
  });

  it("keeps a renamed character separate from a fresh create draft without reading browser storage", async () => {
    const readStorage = vi.spyOn(Storage.prototype, "getItem");
    const writeStorage = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    const client = characterClient({
      listCharacters: vi
        .fn()
        .mockResolvedValueOnce(characterPage({ items: [] }))
        .mockResolvedValueOnce(
          characterPage({
            items: [
              characterListItem({
                name: "改名后的角色",
                revision_number: 2,
                concurrency_version: 2,
              }),
            ],
          }),
        ),
      createCharacter: vi
        .fn()
        .mockResolvedValueOnce(
          versionedCharacter(1, { name: "最初角色", role: "", profile: "" }),
        )
        .mockResolvedValueOnce(
          versionedCharacter(1, {
            character_id: secondCharacterId,
            name: "独立新角色",
            role: "",
            profile: "",
          }),
        ),
      getCharacter: vi
        .fn()
        .mockResolvedValue(
          versionedCharacter(1, { name: "最初角色", role: "", profile: "" }),
        ),
      reviseCharacter: vi.fn().mockResolvedValue(
        versionedCharacter(2, {
          name: "改名后的角色",
          role: "",
          profile: "",
        }),
      ),
    });
    render(
      <MemoryRouter
        initialEntries={[`/projects/${characterProjectId}/characters`]}
      >
        <Routes>
          <Route
            path="/projects/:projectId/characters"
            element={<CharacterListPage client={client} />}
          />
          <Route
            path="/projects/:projectId/characters/:characterId"
            element={<CharacterEditorPage client={client} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await user.type(await screen.findByLabelText("角色名称"), "最初角色");
    await user.click(screen.getByRole("button", { name: "创建角色" }));
    await user.click(await screen.findByRole("link", { name: "查看新角色" }));
    await screen.findByRole("heading", { name: "最初角色" });
    await user.clear(screen.getByLabelText("角色名称"));
    await user.type(screen.getByLabelText("角色名称"), "改名后的角色");
    await user.click(screen.getByRole("button", { name: "保存" }));
    await screen.findByText("角色修订已保存。");
    expect(client.reviseCharacter).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ name: "改名后的角色", etag: '"1"' }),
    );
    await user.click(screen.getByRole("link", { name: "返回角色列表" }));
    await screen.findByText("改名后的角色");
    for (const label of ["角色名称", "角色定位", "角色档案（纯文本）"])
      expect(screen.getByLabelText(label)).toHaveValue("");
    expect(screen.queryByText("最初角色")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("角色名称"), "独立新角色");
    await user.click(screen.getByRole("button", { name: "创建角色" }));
    await waitFor(() =>
      expect(client.createCharacter).toHaveBeenCalledTimes(2),
    );
    expect(client.createCharacter).toHaveBeenLastCalledWith({
      projectId: characterProjectId,
      name: "独立新角色",
      role: "",
      profile: "",
    });
    expect(readStorage).not.toHaveBeenCalled();
    expect(writeStorage).not.toHaveBeenCalled();
  });
});
