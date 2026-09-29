import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";
import { CharacterEditorPage } from "../../frontend/src/features/character/pages/CharacterEditorPage";
import { CharacterListPage } from "../../frontend/src/features/character/pages/CharacterListPage";
import {
  characterEditorPath,
  characterRevisionHistoryPath,
  projectCharactersPath,
} from "../../frontend/src/features/character/routing";
import { jsonResponse, projectResponse } from "./project-detail-support";
import {
  characterId,
  characterJsonResponse,
  characterPage,
  characterProjectId,
  characterResponse,
} from "./character-support";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="character-location">{location.pathname}</output>;
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRouter />
      <LocationProbe />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Character routes and navigation", () => {
  it("renders safe invalid states when route parameters are absent", () => {
    const first = render(
      <MemoryRouter>
        <CharacterListPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("Project编号无效")).toBeVisible();
    first.unmount();
    render(
      <MemoryRouter>
        <CharacterEditorPage />
      </MemoryRouter>,
    );
    expect(screen.getByText("角色地址无效")).toBeVisible();
  });

  it("builds only canonical Project-scoped paths", () => {
    expect(projectCharactersPath(characterProjectId)).toBe(
      `/projects/${characterProjectId}/characters`,
    );
    expect(characterEditorPath(characterProjectId, characterId)).toBe(
      `/projects/${characterProjectId}/characters/${characterId}`,
    );
    expect(characterRevisionHistoryPath(characterProjectId, characterId)).toBe(
      `/projects/${characterProjectId}/characters/${characterId}/history`,
    );
    expect(() => projectCharactersPath("bad")).toThrow();
    expect(() => characterEditorPath(characterProjectId, "bad")).toThrow();
    expect(() => characterRevisionHistoryPath("bad", characterId)).toThrow();
  });

  it("directly loads the list and editor routes", async () => {
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url = requestUrl(input);
      return Promise.resolve(
        url.includes(`/characters/${characterId}`)
          ? characterJsonResponse(characterResponse(), { etag: '"1"' })
          : characterJsonResponse(characterPage()),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const list = renderAt(`/projects/${characterProjectId}/characters`);
    expect(await screen.findByText("林砚")).toBeVisible();
    expect(screen.getByTestId("character-location")).toHaveTextContent(
      `/projects/${characterProjectId}/characters`,
    );
    list.unmount();

    renderAt(`/projects/${characterProjectId}/characters/${characterId}`);
    expect(await screen.findByRole("heading", { name: "林砚" })).toBeVisible();
    expect(screen.getByTestId("character-location")).toHaveTextContent(
      `/projects/${characterProjectId}/characters/${characterId}`,
    );
  });

  it("navigates from Project details through the real Character link", async () => {
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url = requestUrl(input);
      if (url.endsWith(`/projects/${characterProjectId}`)) {
        return Promise.resolve(
          jsonResponse(
            projectResponse(1, {
              project_id: characterProjectId,
              title: "含角色入口的Project",
            }),
            { etag: '"1"' },
          ),
        );
      }
      return Promise.resolve(characterJsonResponse(characterPage()));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt(`/projects/${characterProjectId}`);
    const link = await screen.findByRole("link", { name: "人物" });
    expect(link).toHaveAttribute(
      "href",
      `/projects/${characterProjectId}/characters`,
    );
    await user.click(link);
    expect(await screen.findByText("林砚")).toBeVisible();
  });

  it.each([
    "/characters",
    `/characters/${characterId}`,
    `/projects/${characterProjectId}/characters/history`,
  ])("keeps unsupported Character route %s on the React 404", (path) => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    renderAt(path);
    expect(screen.getByRole("heading", { name: "页面不存在" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
