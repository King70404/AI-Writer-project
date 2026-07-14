import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { JSX } from "react";
import { describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "../../frontend/src/components/AppErrorBoundary";

const testModuleUrl = import.meta.url;

function BrokenComponent(): JSX.Element {
  throw new Error(`Sensitive component detail from ${testModuleUrl}`);
}

describe("AppErrorBoundary", () => {
  it("shows a safe fallback and offers a current-page reload", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const reload = vi.fn();
    const user = userEvent.setup();

    render(
      <AppErrorBoundary onReload={reload}>
        <BrokenComponent />
      </AppErrorBoundary>,
    );

    expect(
      screen.getByRole("heading", { name: "页面暂时无法显示" }),
    ).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("Sensitive component detail");
    expect(document.body).not.toHaveTextContent(testModuleUrl);
    expect(document.body).not.toHaveTextContent("file:///");

    await user.click(
      screen.getByRole("button", { name: "重新加载当前页面" }),
    );
    expect(reload).toHaveBeenCalledOnce();
  });
});
