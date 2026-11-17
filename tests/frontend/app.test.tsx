import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { AppRouter } from "../../frontend/src/app/AppRouter";
import { LoadingState } from "../../frontend/src/components/LoadingState";

describe("AIWebNovel frontend foundation", () => {
  it("renders the truthful author home without business placeholders", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "AI 网文助手" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "写作首页",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("V1", { selector: ".phase-label" })).toBeVisible();
    expect(screen.getByLabelText("当前版本：V1")).toBeVisible();
    expect(screen.getByRole("link", { name: "打开书架" })).toHaveAttribute(
      "href",
      "/projects",
    );
    expect(screen.getByRole("link", { name: "新建小说" })).toHaveAttribute(
      "href",
      "/projects",
    );
    expect(screen.getByText(/本机还没有最近写作的章节/u)).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "继续写作" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "主要导航" }),
    ).toHaveTextContent("首页书架数据备份");
    expect(screen.queryByText("工程基础")).not.toBeInTheDocument();
    expect(screen.getByText(/手动写作、自动保存与导出仍可使用/)).toBeVisible();
    expect(
      screen.queryByText(/章节写作与AI功能尚未实现/),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "跳至主要内容" })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(screen.getByText("本地系统状态")).toBeInTheDocument();
    expect(
      screen.getByText("正在检查本地后端状态。").closest('[role="status"]'),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新检查" })).toBeDisabled();
    expect(
      document.querySelector('[data-feature-id="FND-002"]'),
    ).toHaveAttribute("data-state", "checking");

    expect(
      screen.queryByRole("button", { name: "开始创作" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        /项目数量|任务数量|Codex 在线|模型状态|总字数|待办|项目总数|章节总数|今日字数|创作进度/,
      ),
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
