import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";
import { projectDetailsPath } from "../../frontend/src/features/projects/routing";
import {
  jsonResponse,
  projectId,
  projectResponse,
} from "./project-detail-support";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="detail-location">{location.pathname}</output>;
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

describe("Project detail routes and navigation", () => {
  it("rejects a non-canonical Project ID before creating a navigation path", () => {
    expect(() => projectDetailsPath("not-a-project-id")).toThrow(
      "A canonical Project ID is required for navigation.",
    );
  });

  it("renders the exact parameter route and supports direct refresh semantics", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(projectResponse(), { etag: '"1"' }));
    vi.stubGlobal("fetch", fetchMock);
    renderAt(`/projects/${projectId}`);

    expect(
      await screen.findByRole("heading", { name: "项目版本1" }),
    ).toBeVisible();
    expect(screen.getByTestId("detail-location")).toHaveTextContent(
      `/projects/${projectId}`,
    );
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("navigates from a semantic list link and performs a fresh details GET", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      if (url.includes("?limit=20")) {
        return Promise.resolve(
          jsonResponse({
            items: [
              {
                project_id: projectId,
                current_revision_id: "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                revision_number: 1,
                concurrency_version: 1,
                title: "列表摘要标题",
                created_at: "2026-07-22T08:30:00Z",
                updated_at: "2026-07-22T08:30:00Z",
                revision_created_at: "2026-07-22T08:30:00Z",
              },
            ],
            next_cursor: null,
            has_more: false,
          }),
        );
      }
      return Promise.resolve(
        jsonResponse(projectResponse(1, { title: "详情GET标题" }), {
          etag: '"1"',
        }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAt("/projects");

    const link = await screen.findByRole("link", { name: "打开小说" });
    expect(link).toHaveAttribute("href", `/projects/${projectId}`);
    await user.click(link);
    expect(
      await screen.findByRole("heading", { name: "详情GET标题" }),
    ).toBeVisible();
    expect(screen.getByTestId("detail-location")).toHaveTextContent(
      `/projects/${projectId}`,
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each([
    `/projects/${projectId}/edit`,
    `/projects/${projectId}/revisions`,
    `/projects/${projectId}/settings`,
    "/not-a-real-route",
  ])("keeps unauthorized or unknown route %s on client 404", (path) => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    renderAt(path);
    expect(screen.getByRole("heading", { name: "页面不存在" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the root and projects routes alongside only one detail parameter route", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          jsonResponse({ items: [], next_cursor: null, has_more: false }),
        ),
    );
    const { unmount } = renderAt("/projects");
    expect(await screen.findByText("还没有项目")).toBeVisible();
    unmount();

    renderAt("/");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "写作首页" })).toBeVisible(),
    );
  });
});
