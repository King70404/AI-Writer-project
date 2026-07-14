import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location-path">{location.pathname}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRouter />
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe("application routes", () => {
  it("renders the foundation page at the root route", () => {
    renderAt("/");

    expect(
      screen.getByRole("heading", { name: "AIWebNovel 前端基础已启动" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("location-path")).toHaveTextContent("/");
  });

  it("uses client-side routing to leave the not-found page", async () => {
    const user = userEvent.setup();
    renderAt("/missing-page");

    expect(
      screen.getByRole("heading", { name: "页面不存在" }),
    ).toBeInTheDocument();
    const returnLink = screen.getByRole("link", { name: "返回基础页" });
    expect(returnLink).toHaveAttribute("href", "/");

    await user.click(returnLink);

    expect(screen.getByTestId("location-path")).toHaveTextContent("/");
    expect(
      screen.getByRole("heading", { name: "AIWebNovel 前端基础已启动" }),
    ).toBeInTheDocument();
  });
});
