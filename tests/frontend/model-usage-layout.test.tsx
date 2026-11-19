import { readFileSync } from "node:fs";
import path from "node:path";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  UsageClient,
  UsagePage,
  UsageTotals,
} from "../../frontend/src/features/usage/api/usage";
import { ModelUsagePanel } from "../../frontend/src/features/usage/components/ModelUsagePanel";

/*
 * 写作台右栏只有 20–23.5rem。旧的“名称 max-content + 数值 1fr”两列让最长的名称占满整栏，
 * 数值列被挤到接近 0 宽，再配合 overflow-wrap: anywhere 就成了每字一行。
 * jsdom 不做布局，所以这里同时检查样式表规则本身和渲染出的键值结构。
 */
const css = readFileSync(
  path.resolve(process.cwd(), "src/styles/global.css"),
  "utf8",
);

/** All declaration blocks (also inside @media/@container) whose selector list names `selector`. */
function blocks(selector: string): string[] {
  const found: string[] = [];
  const pattern = /([^{}]+)\{([^{}]*)\}/gu;
  for (const match of css.matchAll(pattern)) {
    const selectors = match[1]
      .replace(/\/\*[\s\S]*?\*\//gu, "")
      .split(",")
      .map((item) => item.trim());
    if (selectors.includes(selector)) found.push(match[2]);
  }
  return found;
}

function declarations(selector: string, property: string): string[] {
  return blocks(selector).flatMap((body) =>
    [
      ...body.matchAll(
        new RegExp(`(?:^|;|\\s)${property}\\s*:\\s*([^;]+)`, "gu"),
      ),
    ].map((match) => match[1].trim()),
  );
}

const zero: UsageTotals = {
  attempts: 0,
  completed: 0,
  failed: 0,
  timeout: 0,
  interrupted: 0,
  running: 0,
  reported_attempts: 0,
  incomplete_reports: 0,
  unknown_attempts: 0,
  reported_input_tokens: 0,
  reported_output_tokens: 0,
  reported_total_tokens: 0,
  input_characters: 0,
  output_characters: 0,
};

function page(): UsagePage {
  const totals: UsageTotals = {
    ...zero,
    attempts: 12,
    completed: 11,
    timeout: 1,
    reported_attempts: 11,
    unknown_attempts: 1,
    reported_input_tokens: 123_456,
    reported_output_tokens: 7_890,
    reported_total_tokens: 131_346,
    input_characters: 456_789,
    output_characters: 3_210,
  };
  return {
    project_id: "project-one",
    chapter_id: "chapter-one",
    task_id: null,
    estimate_method: "local_characters_v1",
    totals,
    by_operation: [],
    by_model: [],
    items: [],
    total: 0,
    next_offset: null,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("本章模型用量 in a narrow writing-desk column", () => {
  it("never lays the totals out as a max-content label column beside a squeezed value column", () => {
    const columns = declarations(
      ".model-usage__totals",
      "grid-template-columns",
    );
    expect(columns.length).toBeGreaterThan(0);
    // Every rule (including any media query) keeps a single, shrinkable column.
    expect(columns.every((value) => value === "minmax(0, 1fr)")).toBe(true);
    expect(blocks(".model-usage__totals").join("\n")).not.toMatch(
      /max-content/u,
    );
    // Values wrap at word boundaries instead of breaking after every character.
    const wraps = declarations(".model-usage__totals dd", "overflow-wrap");
    expect(wraps).toEqual(["break-word"]);
    expect(
      declarations(".model-usage__items li", "overflow-wrap"),
    ).not.toContain("anywhere");
  });

  it("renders the summary as label/value pairs, each value whole in its own entry", async () => {
    const client: UsageClient = { page: vi.fn().mockResolvedValue(page()) };
    const style = document.createElement("style");
    style.textContent = css;
    document.head.append(style);
    try {
      render(
        <div style={{ width: "20rem" }}>
          <ModelUsagePanel
            projectId="project-one"
            chapterId="chapter-one"
            title="本章模型用量"
            client={client}
          />
        </div>,
      );
      const details = screen.getByText("本章模型用量").closest("details")!;
      act(() => {
        details.open = true;
        fireEvent(details, new Event("toggle"));
      });
      await screen.findByText("已发出的模型请求");
      const list = details.querySelector("dl.model-usage__totals")!;
      expect(getComputedStyle(list).gridTemplateColumns).toBe("minmax(0, 1fr)");
      const children = [...list.children];
      expect(children.map((item) => item.tagName)).toEqual([
        "DT",
        "DD",
        "DT",
        "DD",
        "DT",
        "DD",
        "DT",
        "DD",
      ]);
      const pairs = Object.fromEntries(
        [0, 2, 4, 6].map((index) => [
          children[index].textContent,
          children[index + 1].textContent,
        ]),
      );
      expect(pairs["已发出的模型请求"]).toBe("12 次（已返回 11 · 超时 1）");
      expect(pairs["服务商报告的 token"]).toBe(
        "输入 123,456 · 输出 7,890（来自 11 次报告）",
      );
      expect(pairs["本机字符计数（估算依据，不是 token）"]).toBe(
        "发送 456,789 字符 · 返回 3,210 字符",
      );
    } finally {
      style.remove();
    }
  });
});
