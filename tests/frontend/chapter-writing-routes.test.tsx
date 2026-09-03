import {
  createRoutesFromChildren,
  MemoryRouter,
  Route,
  Routes,
} from "react-router";
import type { ReactElement, ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";
import { NovelStructurePage } from "../../frontend/src/features/novel-structure/pages/NovelStructurePage";
import { chapterWritingPath } from "../../frontend/src/features/novel-structure/routing";
import {
  chapterId,
  structureProjectId,
  structureClient,
  chapterResponse,
  volumeResponse,
  structureJsonResponse,
} from "./novel-structure-support";
import { flushReact, contentResponse } from "./chapter-writing-support";
import { jsonResponse, projectResponse } from "./project-detail-support";

describe("Chapter writing route inventory", () => {
  it("has exactly twelve routes with one writing route and no other writing endpoints", () => {
    const root = AppRouter() as ReactElement<{ readonly children: ReactNode }>;
    const children = createRoutesFromChildren(root.props.children)[0].children!;
    expect(
      children.map((route) =>
        route.index ? "/" : route.path === "*" ? "*" : `/${route.path}`,
      ),
    ).toEqual([
      "/",
      "/projects",
      "/projects/:projectId",
      "/projects/:projectId/history",
      "/projects/:projectId/story-bible",
      "/projects/:projectId/story-bible/history",
      "/projects/:projectId/characters",
      "/projects/:projectId/characters/:characterId",
      "/projects/:projectId/characters/:characterId/history",
      "/projects/:projectId/structure",
      "/projects/:projectId/chapters/:chapterId/write",
      "*",
    ]);
    expect(chapterWritingPath(structureProjectId, chapterId)).toBe(
      `/projects/${structureProjectId}/chapters/${chapterId}/write`,
    );
    expect(() => chapterWritingPath("bad", chapterId)).toThrow();
    expect(() => chapterWritingPath(structureProjectId, "bad")).toThrow();
  });

  it("adds an explicit writing link without adding manuscript to the structure form", async () => {
    await flushReact(() => {
      render(
        <MemoryRouter
          initialEntries={[`/projects/${structureProjectId}/structure`]}
        >
          <Routes>
            <Route
              path="/projects/:projectId/structure"
              element={<NovelStructurePage client={structureClient()} />}
            />
          </Routes>
        </MemoryRouter>,
      );
    });
    expect(screen.getByRole("link", { name: "写正文" })).toHaveAttribute(
      "href",
      chapterWritingPath(structureProjectId, chapterId),
    );
    expect(screen.queryByLabelText("章节正文")).not.toBeInTheDocument();
  });

  it("directly loads the production route using the real typed clients", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation((input) => {
        const path =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        if (path.endsWith(`/projects/${structureProjectId}`))
          return Promise.resolve(
            jsonResponse(projectResponse(), { etag: '"1"' }),
          );
        const body = path.endsWith("/content")
          ? contentResponse("真实客户端正文")
          : path.includes("/volumes/")
            ? volumeResponse()
            : chapterResponse();
        return Promise.resolve(structureJsonResponse(body, { etag: '"1"' }));
      }),
    );
    await flushReact(() => {
      render(
        <MemoryRouter
          initialEntries={[chapterWritingPath(structureProjectId, chapterId)]}
        >
          <AppRouter />
        </MemoryRouter>,
      );
    });
    expect(screen.getByLabelText("章节正文")).toHaveValue("真实客户端正文");
  });
});
