import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRouter />
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe("Project routes", () => {
  it("renders /projects and supplies a client-side navigation entry", async () => {
    const user = userEvent.setup();
    renderAt("/");
    const projectsLink = screen.getByRole("link", { name: "书架" });
    expect(projectsLink).toHaveAttribute("href", "/projects");

    await user.click(projectsLink);

    expect(screen.getByTestId("location")).toHaveTextContent("/projects");
    expect(
      screen.getByRole("heading", { level: 2, name: "书架" }),
    ).toBeVisible();
    expect(projectsLink).toHaveAttribute("aria-current", "page");
  });

  it("keeps the root author home route", () => {
    renderAt("/");
    expect(screen.getByRole("heading", { name: "写作首页" })).toBeVisible();
  });

  it.each([
    "/not-a-real-route",
    "/projects/prj_01ARZ3NDEKTSV4RRFFQ69G5FAV/edit",
  ])("keeps unsupported route %s on the React 404", (path) => {
    renderAt(path);
    expect(screen.getByRole("heading", { name: "页面不存在" })).toBeVisible();
  });
});
