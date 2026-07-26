import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";
import { LoadingState } from "../../frontend/src/components/LoadingState";

describe("AIWebNovel frontend foundation", () => {
  it("renders the truthful phase 1 foundation without business placeholders", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "AIWebNovel" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "AIWebNovel 前端基础已启动",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("阶段 1", { selector: ".phase-label" }),
    ).toBeVisible();
    expect(screen.getAllByText(/小说业务功能尚未实现/).length).toBeGreaterThan(
      0,
    );
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "跳至主要内容" })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(screen.getByText("本地系统状态")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "正在检查本地后端状态。",
    );
    expect(screen.getByRole("button", { name: "重新检查" })).toBeDisabled();
    expect(
      document.querySelector('[data-feature-id="FND-002"]'),
    ).toHaveAttribute("data-state", "checking");

    expect(
      screen.queryByRole("button", { name: "开始创作" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/项目数量|任务数量|Codex 在线|模型状态/),
    ).not.toBeInTheDocument();

    for (const button of screen.queryAllByRole("button")) {
      expect(button).not.toHaveAccessibleName("");
    }
  });

  it("provides an accessible loading state without a fabricated percentage", () => {
    render(<LoadingState message="正在准备页面。" />);

    expect(screen.getByRole("status")).toHaveTextContent("正在准备页面。");
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });
});
