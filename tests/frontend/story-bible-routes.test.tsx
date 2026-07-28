import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";
import { projectStoryBiblePath } from "../../frontend/src/features/projects/routing";
import { jsonResponse, projectResponse } from "./project-detail-support";
import {
  storyBibleJsonResponse,
  storyBibleResponse,
  storyProjectId,
} from "./story-bible-support";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="story-location">{location.pathname}</output>;
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

describe("Story Bible route and navigation", () => {
  it("builds only a canonical Project-scoped Story Bible path", () => {
    expect(projectStoryBiblePath(storyProjectId)).toBe(
      `/projects/${storyProjectId}/story-bible`,
    );
    expect(() => projectStoryBiblePath("not-a-project-id")).toThrow(
      "A canonical Project ID is required for navigation.",
    );
  });

  it("supports direct route loading with exactly one Story Bible GET", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        storyBibleJsonResponse(storyBibleResponse(), { etag: '"1"' }),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderAt(`/projects/${storyProjectId}/story-bible`);

    expect(
      await screen.findByRole("heading", { name: "设定集版本1" }),
    ).toBeVisible();
    expect(screen.getByTestId("story-location")).toHaveTextContent(
      `/projects/${storyProjectId}/story-bible`,
    );
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/v1/projects/${storyProjectId}/story-bible`,
    );
  });

  it("navigates from Project detail through the semantic Story Bible link", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      if (url.endsWith(`/projects/${storyProjectId}`)) {
        return Promise.resolve(
          jsonResponse(
            projectResponse(1, {
              project_id: storyProjectId,
              title: "含设定入口的Project",
            }),
            { etag: '"1"' },
          ),
        );
      }
      return Promise.resolve(
        storyBibleJsonResponse(storyBibleResponse(), { etag: '"1"' }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    renderAt(`/projects/${storyProjectId}`);

    const link = await screen.findByRole("link", {
      name: "查看 Story Bible",
    });
    expect(link).toHaveAttribute(
      "href",
      `/projects/${storyProjectId}/story-bible`,
    );
    await user.click(link);

    expect(
      await screen.findByRole("heading", { name: "设定集版本1" }),
    ).toBeVisible();
    expect(screen.getByTestId("story-location")).toHaveTextContent(
      `/projects/${storyProjectId}/story-bible`,
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each([
    `/story-bibles/sbl_01ARZ3NDEKTSV4RRFFQ69G5FAV`,
    `/projects/${storyProjectId}/story-bible/edit`,
    `/projects/${storyProjectId}/story-bible/settings`,
  ])("keeps unsupported Story Bible route %s on the React 404", (path) => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    renderAt(path);
    expect(screen.getByRole("heading", { name: "页面不存在" })).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
