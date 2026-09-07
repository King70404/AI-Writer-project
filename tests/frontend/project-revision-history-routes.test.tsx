import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";
import { projectRevisionHistoryPath } from "../../frontend/src/features/projects/routing";
import {
  jsonResponse,
  projectId,
  projectResponse,
  timestamp,
} from "./project-detail-support";

function LocationProbe() {
  return (
    <output data-testid="history-location">{useLocation().pathname}</output>
  );
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRouter />
      <LocationProbe />
    </MemoryRouter>,
  );
}

function historyPage() {
  return {
    project_id: projectId,
    current_revision_number: 1,
    items: [
      {
        revision_id: "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        revision_number: 1,
        title: "可导航的修订",
        created_at: timestamp,
        is_current: true,
      },
    ],
    next_cursor: null,
    has_more: false,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("Project revision history route", () => {
  it("builds only a canonical encoded Project history path", () => {
    expect(projectRevisionHistoryPath(projectId)).toBe(
      `/projects/${projectId}/history`,
    );
    expect(() => projectRevisionHistoryPath("not-a-project-id")).toThrow(
      "A canonical Project ID is required for navigation.",
    );
  });

  it("supports a direct history route load", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(historyPage()));
    vi.stubGlobal("fetch", fetchMock);
    renderAt(`/projects/${projectId}/history`);

    expect(await screen.findByText("可导航的修订")).toBeVisible();
    expect(screen.getByTestId("history-location")).toHaveTextContent(
      `/projects/${projectId}/history`,
    );
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("navigates from Project details through the explicit history link", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      return Promise.resolve(
        url.includes("/revisions?")
          ? jsonResponse(historyPage())
          : jsonResponse(projectResponse(), { etag: '"1"' }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAt(`/projects/${projectId}`);
    const link = await screen.findByRole("link", { name: "历史版本" });
    expect(link).toHaveAttribute("href", `/projects/${projectId}/history`);
    await user.click(link);
    expect(await screen.findByText("可导航的修订")).toBeVisible();
    expect(screen.getByTestId("history-location")).toHaveTextContent(
      `/projects/${projectId}/history`,
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps an unauthorized neighboring route on client 404 without fetch", () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    renderAt(`/projects/${projectId}/history/restore`);
    expect(screen.getByRole("heading", { name: "页面不存在" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
