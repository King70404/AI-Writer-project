import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";
import { projectStructurePath } from "../../frontend/src/features/projects/routing";
import { jsonResponse, projectResponse } from "./project-detail-support";
import {
  structureErrorEnvelope,
  structureJsonResponse,
  structureProjectId,
} from "./novel-structure-support";

afterEach(() => vi.unstubAllGlobals());

describe("Novel Structure route", () => {
  it("builds only the canonical unified workspace path", () => {
    expect(projectStructurePath(structureProjectId)).toBe(
      `/projects/${structureProjectId}/structure`,
    );
    expect(() => projectStructurePath("bad")).toThrow();
  });

  it("navigates from Project details and directly renders the unified route", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation((input) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        if (url.endsWith(`/projects/${structureProjectId}`)) {
          return Promise.resolve(
            jsonResponse(
              projectResponse(1, {
                project_id: structureProjectId,
                title: "结构项目",
              }),
              { etag: '"1"' },
            ),
          );
        }
        if (url.endsWith("/outline")) {
          return Promise.resolve(
            structureJsonResponse(structureErrorEnvelope("OUTLINE_NOT_FOUND"), {
              status: 404,
            }),
          );
        }
        return Promise.resolve(structureJsonResponse([]));
      }),
    );
    render(
      <MemoryRouter initialEntries={[`/projects/${structureProjectId}`]}>
        <AppRouter />
      </MemoryRouter>,
    );
    const link = await screen.findByRole("link", { name: "小说结构" });
    expect(link).toHaveAttribute(
      "href",
      `/projects/${structureProjectId}/structure`,
    );
    await user.click(link);
    expect(
      await screen.findByRole("heading", { name: "小说结构" }),
    ).toBeVisible();
    expect(screen.getByText("请先创建卷")).toBeVisible();
  });

  it.each([
    "/structure",
    `/projects/${structureProjectId}/outline`,
    `/projects/${structureProjectId}/volumes`,
    `/projects/${structureProjectId}/chapters`,
  ])("keeps unsupported route %s on the React 404", (path) => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MemoryRouter initialEntries={[path]}>
        <AppRouter />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "页面不存在" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
