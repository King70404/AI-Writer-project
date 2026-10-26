import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../frontend/src/api/errors";
import { securitySession } from "../../frontend/src/api/security-session";
import {
  MAX_DIFF_EDITS,
  diffText,
  tokenize,
} from "../../frontend/src/features/novel-structure/candidate-diff";
import { CandidateComparison } from "../../frontend/src/features/novel-structure/components/CandidateComparison";
import { AIWorkflowAssistant } from "../../frontend/src/features/novel-structure/components/AIWorkflowAssistant";
import { useChapterWriting } from "../../frontend/src/features/novel-structure/hooks/useChapterWriting";
import type {
  AIWorkflowClient,
  ModelProfile,
  WorkflowRun,
} from "../../frontend/src/features/novel-structure/api/ai-workflow";
import {
  UsageError,
  parseUsageAttempt,
  parseUsagePage,
  usageClient,
  usageError,
  type UsageAttempt,
  type UsageClient,
  type UsagePage,
  type UsageTotals,
} from "../../frontend/src/features/usage/api/usage";
import { ModelUsagePanel } from "../../frontend/src/features/usage/components/ModelUsagePanel";
import { chapterId } from "./novel-structure-support";
import { deferred, written, writingClient } from "./chapter-writing-support";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
});

const projectId = "project-one";

const zeroTotals: UsageTotals = {
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

const reportedAttempt: UsageAttempt = {
  id: "attempt-one",
  chapter_id: chapterId,
  operation: "generation",
  task_id: "run-one",
  profile_id: "default-local",
  model_kind: "local",
  model_name: "test-model",
  status: "completed",
  error_code: null,
  usage_source: "provider_reported",
  reported_input_tokens: 120,
  reported_output_tokens: 80,
  reported_total_tokens: 200,
  input_characters: 300,
  output_characters: 240,
  started_at: "2026-10-24T01:00:00Z",
  finished_at: "2026-10-24T01:00:02Z",
  duration_ms: 2100,
};

const unknownAttempt: UsageAttempt = {
  ...reportedAttempt,
  id: "attempt-two",
  operation: "story_review",
  model_kind: "cloud",
  model_name: "cloud-model",
  status: "timeout",
  error_code: "AIProviderTimeout",
  usage_source: "unknown",
  reported_input_tokens: null,
  reported_output_tokens: null,
  reported_total_tokens: null,
  output_characters: null,
  started_at: "not-a-date",
  finished_at: null,
  duration_ms: null,
};

const mixedTotals: UsageTotals = {
  ...zeroTotals,
  attempts: 2,
  completed: 1,
  timeout: 1,
  failed: 0,
  reported_attempts: 1,
  unknown_attempts: 1,
  reported_input_tokens: 120,
  reported_output_tokens: 80,
  reported_total_tokens: 200,
  input_characters: 600,
  output_characters: 240,
};

function usagePage(overrides: Partial<UsagePage> = {}): UsagePage {
  return {
    project_id: projectId,
    chapter_id: chapterId,
    task_id: null,
    estimate_method: "local_characters_v1",
    totals: mixedTotals,
    by_operation: [
      {
        operation: "generation",
        totals: {
          ...zeroTotals,
          attempts: 1,
          completed: 1,
          reported_attempts: 1,
          reported_input_tokens: 120,
          reported_output_tokens: 80,
          reported_total_tokens: 200,
        },
      },
      {
        operation: "story_review",
        totals: {
          ...zeroTotals,
          attempts: 1,
          timeout: 1,
          unknown_attempts: 1,
        },
      },
    ],
    by_model: [
      {
        model_kind: "local",
        model_name: "test-model",
        totals: mixedTotals,
      },
    ],
    items: [reportedAttempt, unknownAttempt],
    total: 2,
    next_offset: null,
    ...overrides,
  };
}

function fakeUsage(...pages: (UsagePage | Error)[]): UsageClient {
  const page = vi.fn();
  for (const item of pages) {
    if (item instanceof Error) page.mockRejectedValueOnce(item);
    else page.mockResolvedValueOnce(item);
  }
  return { page };
}

function apiError(init: {
  status: number;
  code: string;
  message: string;
}): ApiError {
  return new ApiError({
    ...init,
    details: {},
    retryable: false,
    suggestedAction: null,
    requestId: null,
  });
}

describe("candidate diff", () => {
  it("tokenizes CJK per code point, ASCII words and whitespace runs", () => {
    expect(tokenize("他说 hello  world，𠮷好")).toEqual([
      "他",
      "说",
      " ",
      "hello",
      "  ",
      "world",
      "，",
      "𠮷",
      "好",
    ]);
    expect(tokenize("")).toEqual([]);
  });

  it("marks deletions and insertions and counts non-whitespace characters", () => {
    const diff = diffText("他慢慢走进房间。", "他快步走进 大厅。");
    expect(diff.approximate).toBe(false);
    const original = diff.segments
      .filter((segment) => segment.type !== "insert")
      .map((segment) => segment.text)
      .join("");
    const candidate = diff.segments
      .filter((segment) => segment.type !== "delete")
      .map((segment) => segment.text)
      .join("");
    expect(original).toBe("他慢慢走进房间。");
    expect(candidate).toBe("他快步走进 大厅。");
    expect(diff.segments[0]).toEqual({ type: "equal", text: "他" });
    expect(diff.segments.at(-1)).toEqual({ type: "equal", text: "。" });
    expect(diff.deletedCharacters).toBe(4);
    expect(diff.insertedCharacters).toBe(4);
  });

  it("handles identical, empty and purely inserted or deleted text", () => {
    expect(diffText("相同", "相同")).toEqual({
      segments: [{ type: "equal", text: "相同" }],
      deletedCharacters: 0,
      insertedCharacters: 0,
      approximate: false,
    });
    expect(diffText("", "新增内容").segments).toEqual([
      { type: "insert", text: "新增内容" },
    ]);
    expect(diffText("删除内容", "").segments).toEqual([
      { type: "delete", text: "删除内容" },
    ]);
    expect(diffText("甲乙", "甲丙乙").segments).toEqual([
      { type: "equal", text: "甲" },
      { type: "insert", text: "丙" },
      { type: "equal", text: "乙" },
    ]);
    expect(diffText("甲丙乙", "甲乙").segments).toEqual([
      { type: "equal", text: "甲" },
      { type: "delete", text: "丙" },
      { type: "equal", text: "乙" },
    ]);
  });

  it("falls back to a whole-block comparison beyond the token or edit limits", () => {
    const tooLong = diffText("前甲乙丙后", "前丁戊己后", { maxTokens: 4 });
    expect(tooLong.approximate).toBe(true);
    expect(tooLong.segments).toEqual([
      { type: "equal", text: "前" },
      { type: "delete", text: "甲乙丙" },
      { type: "insert", text: "丁戊己" },
      { type: "equal", text: "后" },
    ]);
    const tooManyEdits = diffText("abcdef", "uvwxyz".split("").join(" "), {
      maxEdits: 2,
    });
    expect(tooManyEdits.approximate).toBe(true);
    expect(tooManyEdits.deletedCharacters).toBe(6);
    expect(tooManyEdits.insertedCharacters).toBe(6);
    expect(MAX_DIFF_EDITS).toBeGreaterThan(0);
    expect(diffText("abc", "abd x").approximate).toBe(false);
  });
});

describe("CandidateComparison", () => {
  it("shows rewrite differences with switchable views and does not call anything", () => {
    render(
      <CandidateComparison
        operation="rewrite"
        original="他慢慢走进房间。"
        candidate="他快步走进大厅。"
        currentContent="无关正文"
      />,
    );
    expect(screen.getByRole("note")).toHaveTextContent(
      "删除 4 字，新增 4 字（非空白字符，本地比较）。",
    );
    const original = screen.getByRole("group", {
      name: "原文（删除部分划线）",
    });
    const candidate = screen.getByRole("group", {
      name: "候选（新增部分标记）",
    });
    expect(original).toHaveTextContent("他慢慢走进房间。");
    expect(candidate).toHaveTextContent("他快步走进大厅。");
    expect(original.querySelector("del")).toHaveTextContent("慢慢");
    expect(candidate.querySelector("ins")).toHaveTextContent("快步");
    expect(candidate.querySelector("del")).toBeNull();
    expect(original.querySelector("ins")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "只看候选" }));
    expect(screen.getByRole("button", { name: "只看候选" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.queryByRole("group", { name: "原文（删除部分划线）" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "只看原文" }));
    expect(
      screen.queryByRole("group", { name: "候选（新增部分标记）" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "对照" }));
    expect(screen.getAllByRole("group")).toHaveLength(3);
  });

  it("explains approximate comparisons for very different text", () => {
    render(
      <CandidateComparison
        operation="rewrite"
        original={"甲".repeat(30_000)}
        candidate={"乙".repeat(10)}
        currentContent=""
      />,
    );
    expect(screen.getByRole("note")).toHaveTextContent(
      "差异较大，未逐字标记：整段对照原文 30000 字与候选 10 字。",
    );
  });

  it("shows the insertion point for continuations with a truncated tail", () => {
    const { rerender } = render(
      <CandidateComparison
        operation="continue"
        original=""
        candidate="新的一段。"
        currentContent={`${"前".repeat(200)}结尾句。`}
      />,
    );
    const pane = screen.getByRole("group", { name: "正文末尾与候选" });
    expect(pane).toHaveTextContent(/^…前+结尾句。/u);
    expect(pane.textContent).not.toContain("前".repeat(150));
    expect(pane.querySelector("ins")).toHaveTextContent("新的一段。");
    rerender(
      <CandidateComparison
        operation="continue"
        original=""
        candidate="开篇。"
        currentContent=""
      />,
    );
    expect(screen.getByText("（当前正文为空）")).toBeInTheDocument();
    rerender(
      <CandidateComparison
        operation="continue"
        original=""
        candidate="下一句。"
        currentContent="短正文"
      />,
    );
    expect(
      screen.getByRole("group", { name: "正文末尾与候选" }).textContent,
    ).toBe("短正文\n\n下一句。");
  });
});

describe("usage parser and client", () => {
  it("parses a valid page and keeps unknown usage distinct from zero", () => {
    const page = parseUsagePage(usagePage(), projectId);
    expect(page.totals.unknown_attempts).toBe(1);
    expect(page.items[1].reported_output_tokens).toBeNull();
    expect(parseUsageAttempt(reportedAttempt)).toEqual(reportedAttempt);
  });

  it.each([
    ["wrong project", { ...usagePage(), project_id: "other" }],
    ["wrong estimate", { ...usagePage(), estimate_method: "tokens" }],
    ["not an object", []],
    ["bad totals", { ...usagePage(), totals: { ...mixedTotals, attempts: 3 } }],
    [
      "incomplete exceeds reported",
      {
        ...usagePage(),
        totals: { ...mixedTotals, incomplete_reports: 2 },
      },
    ],
    ["negative count", { ...usagePage(), total: -1 }],
    ["fraction count", { ...usagePage(), total: 1.5 }],
    ["items not a list", { ...usagePage(), items: {} }],
    [
      "unknown with tokens",
      {
        ...usagePage(),
        items: [{ ...unknownAttempt, reported_output_tokens: 0 }],
      },
    ],
    [
      "reported without tokens",
      {
        ...usagePage(),
        items: [
          {
            ...reportedAttempt,
            reported_input_tokens: null,
            reported_output_tokens: null,
            reported_total_tokens: null,
          },
        ],
      },
    ],
    ["bad id", { ...usagePage(), items: [{ ...reportedAttempt, id: "../x" }] }],
    [
      "bad operation",
      {
        ...usagePage(),
        by_operation: [{ operation: "billing", totals: zeroTotals }],
      },
    ],
    [
      "bad model kind",
      {
        ...usagePage(),
        by_model: [
          { model_kind: "remote", model_name: "x", totals: zeroTotals },
        ],
      },
    ],
    [
      "non-string model",
      {
        ...usagePage(),
        items: [{ ...reportedAttempt, model_name: 3 }],
      },
    ],
  ])("rejects %s", (_label, value) => {
    expect(() => parseUsagePage(value, projectId)).toThrow(UsageError);
  });

  it("reads one page with a plain GET and validated query", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(usagePage()));
    vi.stubGlobal("fetch", fetcher);
    await expect(
      usageClient.page(projectId, {
        chapterId,
        taskId: "run-one",
        offset: 10,
        limit: 5,
      }),
    ).resolves.toMatchObject({ total: 2 });
    const [url, options] = fetcher.mock.calls[0];
    expect(url).toBe(
      `/api/v1/projects/${projectId}/usage?offset=10&limit=5&chapter_id=${chapterId}&task_id=run-one`,
    );
    expect(options?.method).toBe("GET");
    fetcher.mockResolvedValue(Response.json(usagePage()));
    await usageClient.page(projectId);
    expect(fetcher.mock.calls[1][0]).toBe(
      `/api/v1/projects/${projectId}/usage?offset=0&limit=20`,
    );
    await expect(usageClient.page("bad/id")).rejects.toBeInstanceOf(UsageError);
  });

  it("maps API failures to author-facing messages", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      Response.json(
        {
          error: {
            code: "AI_WORKFLOW_SCHEMA_REQUIRED",
            message: "server text",
            details: {},
            retryable: false,
            suggested_action: null,
          },
          request_id: "req_usage",
        },
        { status: 409 },
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    const schemaError = await usageClient
      .page(projectId)
      .catch((error: unknown) => error);
    expect(schemaError).toBeInstanceOf(UsageError);
    expect(schemaError).toMatchObject({ code: "AI_WORKFLOW_SCHEMA_REQUIRED" });
    expect((schemaError as UsageError).message).toContain("备份并启用 AI 协作");
    fetcher.mockResolvedValue(Response.json({ nope: true }));
    await expect(usageClient.page(projectId)).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
    fetcher.mockRejectedValue(new TypeError("offline"));
    await expect(usageClient.page(projectId)).rejects.toMatchObject({
      code: "NETWORK",
    });
  });

  it("clears the session on authorization failures and keeps unknown codes generic", () => {
    const clear = vi.spyOn(securitySession, "clear");
    const own = new UsageError("x", "Y");
    expect(usageError(own)).toBe(own);
    const forbidden = usageError(
      apiError({ status: 403, code: "FORBIDDEN", message: "no" }),
    );
    expect(clear).toHaveBeenCalled();
    expect(forbidden.message).toContain("模型用量读取失败");
    expect(
      usageError(apiError({ status: 401, code: "X", message: "no" })).code,
    ).toBe("X");
    expect(
      usageError(
        apiError({
          status: 200,
          code: "INVALID_RESPONSE",
          message: "bad",
        }),
      ).message,
    ).toContain("无法安全读取");
    expect(
      usageError(
        apiError({
          status: 503,
          code: "USAGE_LEDGER_UNAVAILABLE",
          message: "x",
        }),
      ).message,
    ).toContain("写作不受影响");
    expect(usageError(new Error("boom")).message).toContain("连接中断");
  });
});

describe("ModelUsagePanel", () => {
  function open() {
    const details = screen.getByText("本章模型用量").closest("details")!;
    act(() => {
      details.open = true;
      fireEvent(details, new Event("toggle"));
    });
    return details;
  }

  it("reads nothing until opened, then shows reported, unknown and character counts", async () => {
    const usage = fakeUsage(usagePage());
    render(
      <ModelUsagePanel
        projectId={projectId}
        chapterId={chapterId}
        title="本章模型用量"
        client={usage}
      />,
    );
    expect(usage.page).not.toHaveBeenCalled();
    open();
    expect(screen.getByRole("status")).toHaveTextContent("正在读取模型用量");
    await screen.findByText("已发出的模型请求");
    expect(usage.page).toHaveBeenCalledExactlyOnceWith(
      projectId,
      { chapterId, limit: 10 },
      expect.any(AbortSignal),
    );
    expect(screen.getByText(/2 次（已返回 1 · 超时 1）/u)).toBeInTheDocument();
    expect(
      screen.getByText(/输入 120 · 输出 80（来自 1 次报告）/u),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/1 次（未计入上方 token 合计，不按 0 计）/u),
    ).toBeInTheDocument();
    expect(screen.getByText(/发送 600 字符 · 返回 240 字符/u)).toBeVisible();
    const groups = screen.getByRole("list", { name: "按操作汇总" });
    expect(within(groups).getAllByRole("listitem")).toHaveLength(2);
    const rows = within(
      screen.getByRole("list", { name: "模型请求记录" }),
    ).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent(
      "服务商报告：输入 120 · 输出 80 token · 发送 300 字符 · 返回 240 字符 · 耗时 2.1 秒",
    );
    expect(rows[0]).toHaveTextContent("（本机）");
    expect(rows[1]).toHaveTextContent(
      "not-a-date · 一致性评审 · cloud-model（云端）",
    );
    expect(rows[1]).toHaveTextContent("用量未知（服务商未报告）");
    expect(rows[1]).not.toHaveTextContent("返回");
    expect(screen.queryByText("显示更早的请求")).not.toBeInTheDocument();
  });

  it("shows an empty ledger, partial reports and every terminal state", async () => {
    const usage = fakeUsage(
      usagePage({ totals: zeroTotals, by_operation: [], items: [], total: 0 }),
      usagePage({
        totals: {
          ...zeroTotals,
          attempts: 5,
          completed: 1,
          failed: 1,
          timeout: 1,
          interrupted: 1,
          running: 1,
          reported_attempts: 1,
          incomplete_reports: 1,
          unknown_attempts: 4,
          reported_output_tokens: 5,
        },
        by_operation: [],
        items: [{ ...reportedAttempt, reported_input_tokens: null }],
        total: 1,
      }),
      usagePage({
        totals: { ...zeroTotals, attempts: 1, failed: 1, unknown_attempts: 1 },
        by_operation: [],
        items: [],
        total: 0,
      }),
    );
    render(
      <ModelUsagePanel
        projectId={projectId}
        title="本章模型用量"
        client={usage}
      />,
    );
    open();
    await screen.findByText("还没有发出过模型请求。");
    fireEvent.click(screen.getByRole("button", { name: "刷新用量" }));
    await screen.findByText(
      /5 次（已返回 1 · 失败 1 · 超时 1 · 中断 1 · 进行中 1）/u,
    );
    expect(screen.getByText(/其中 1 次只报告了部分数值/u)).toBeInTheDocument();
    expect(
      screen.getByText(/输入 未报告 · 输出 80 token/u),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "刷新用量" }));
    await screen.findByText("无报告");
    expect(usage.page).toHaveBeenLastCalledWith(
      projectId,
      { chapterId: undefined, limit: 10 },
      expect.any(AbortSignal),
    );
  });

  it("retries after an error and re-reads when the refresh key changes while open", async () => {
    const usage = fakeUsage(
      new UsageError("模型用量记录暂不可用；写作不受影响。"),
      usagePage(),
      usagePage({ totals: { ...mixedTotals, input_characters: 999 } }),
    );
    const { rerender } = render(
      <ModelUsagePanel
        projectId={projectId}
        chapterId={chapterId}
        title="本章模型用量"
        refreshKey="a"
        client={usage}
      />,
    );
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "模型用量记录暂不可用",
    );
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByText(/发送 600 字符/u);
    rerender(
      <ModelUsagePanel
        projectId={projectId}
        chapterId={chapterId}
        title="本章模型用量"
        refreshKey="b"
        client={usage}
      />,
    );
    await screen.findByText(/发送 999 字符/u);
    expect(usage.page).toHaveBeenCalledTimes(3);
  });

  it("aborts an in-flight read when closed and ignores its late result", async () => {
    const late = deferred<UsagePage>();
    const page = vi.fn().mockReturnValue(late.promise);
    render(
      <ModelUsagePanel
        projectId={projectId}
        title="本章模型用量"
        client={{ page }}
      />,
    );
    const details = open();
    const signal = page.mock.calls[0][2] as AbortSignal;
    act(() => {
      details.open = false;
      fireEvent(details, new Event("toggle"));
    });
    expect(signal.aborted).toBe(true);
    await act(async () => {
      late.resolve(usagePage());
      await late.promise;
    });
    expect(screen.queryByText("已发出的模型请求")).not.toBeInTheDocument();
  });

  it("ignores a late failure after closing", async () => {
    const late = deferred<UsagePage>();
    const page = vi.fn().mockReturnValue(late.promise);
    render(
      <ModelUsagePanel
        projectId={projectId}
        title="本章模型用量"
        client={{ page }}
      />,
    );
    const details = open();
    act(() => {
      details.open = false;
      fireEvent(details, new Event("toggle"));
    });
    await act(async () => {
      late.reject(new Error("late"));
      await late.promise.catch(() => undefined);
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("loads older requests page by page and reports a failed page", async () => {
    const usage = fakeUsage(
      usagePage({ items: [reportedAttempt], total: 3, next_offset: 1 }),
      usagePage({ items: [unknownAttempt], total: 3, next_offset: 2 }),
      new UsageError("连接中断，模型用量暂未读取，可以重试。"),
    );
    render(
      <ModelUsagePanel
        projectId={projectId}
        chapterId={chapterId}
        title="本章模型用量"
        client={usage}
      />,
    );
    open();
    const more = await screen.findByRole("button", { name: "显示更早的请求" });
    fireEvent.click(more);
    fireEvent.click(screen.getByRole("button", { name: "正在读取…" }));
    await waitFor(() =>
      expect(
        within(screen.getByRole("list", { name: "模型请求记录" })).getAllByRole(
          "listitem",
        ),
      ).toHaveLength(2),
    );
    expect(usage.page).toHaveBeenNthCalledWith(2, projectId, {
      chapterId,
      offset: 1,
      limit: 10,
    });
    fireEvent.click(screen.getByRole("button", { name: "显示更早的请求" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("连接中断");
    expect(usage.page).toHaveBeenCalledTimes(3);
  });

  it("drops an older-page result that arrives after a refresh", async () => {
    const older = deferred<UsagePage>();
    const page = vi
      .fn()
      .mockResolvedValueOnce(
        usagePage({ items: [reportedAttempt], next_offset: 1 }),
      )
      .mockReturnValueOnce(older.promise)
      .mockResolvedValueOnce(
        usagePage({ items: [reportedAttempt], next_offset: null }),
      );
    render(
      <ModelUsagePanel
        projectId={projectId}
        title="本章模型用量"
        client={{ page }}
      />,
    );
    open();
    fireEvent.click(
      await screen.findByRole("button", { name: "显示更早的请求" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "刷新用量" }));
    await waitFor(() => expect(page).toHaveBeenCalledTimes(3));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /显示更早的请求|正在读取/u }),
      ).not.toBeInTheDocument(),
    );
    await act(async () => {
      older.resolve(usagePage({ items: [unknownAttempt], next_offset: null }));
      await older.promise;
    });
    expect(
      within(screen.getByRole("list", { name: "模型请求记录" })).getAllByRole(
        "listitem",
      ),
    ).toHaveLength(1);
  });

  it("drops an older-page failure that arrives after a refresh", async () => {
    const older = deferred<UsagePage>();
    const page = vi
      .fn()
      .mockResolvedValueOnce(
        usagePage({ items: [reportedAttempt], next_offset: 1 }),
      )
      .mockReturnValueOnce(older.promise)
      .mockResolvedValueOnce(usagePage({ items: [reportedAttempt] }));
    render(
      <ModelUsagePanel
        projectId={projectId}
        title="本章模型用量"
        client={{ page }}
      />,
    );
    open();
    fireEvent.click(
      await screen.findByRole("button", { name: "显示更早的请求" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "刷新用量" }));
    await waitFor(() => expect(page).toHaveBeenCalledTimes(3));
    await act(async () => {
      older.reject(new Error("late"));
      await older.promise.catch(() => undefined);
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("assistant wiring", () => {
  const model: ModelProfile = {
    id: "default-local",
    name: "测试模型",
    kind: "local",
    base_url: "http://127.0.0.1:1234/v1",
    model: "test-model",
    max_output_tokens: 2048,
    has_key: false,
  };
  const pending: WorkflowRun = {
    run_id: "run-one",
    chapter_id: chapterId,
    operation: "rewrite",
    status: "ready",
    base_revision_id: "revision-one",
    base_version: 1,
    current_revision_id: "revision-one",
    current_version: 1,
    instruction: "",
    selected_text: "甲乙丙",
    profile_id: model.id,
    model_snapshot: model,
    max_steps: 1,
    max_output_characters: 1500,
    generated_steps: 1,
    generated_characters: 3,
    context: {
      text: "甲乙丙丁",
      sha256: "a".repeat(64),
      manifest: {
        included_sources: ["current_chapter"],
        omitted_sources: [],
        truncated: false,
        character_count: 4,
        sources: [],
      },
    },
    candidates: [
      {
        candidate_id: "candidate-one",
        sequence: 1,
        text: "甲戊丙",
        model: "test-model",
        character_count: 3,
        status: "pending",
        adopted_revision_id: null,
        adopted_version: null,
        latest_edit: null,
        edit_count: 0,
        adopted_edit_id: null,
      },
    ],
    last_error: null,
  };
  function workflow(runs: WorkflowRun[]): AIWorkflowClient {
    return {
      upgrade: vi.fn().mockResolvedValue(undefined),
      models: vi.fn().mockResolvedValue([model]),
      saveModel: vi.fn().mockResolvedValue(model),
      list: vi.fn().mockResolvedValue(runs),
      create: vi.fn(),
      action: vi.fn(),
      candidate: vi.fn(),
      saveEdit: vi.fn(),
    };
  }

  it("shows the local comparison for a pending rewrite and a chapter usage panel", async () => {
    const api = workflow([pending]);
    const usage = fakeUsage(usagePage());
    function Harness() {
      const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
      return (
        <AIWorkflowAssistant
          chapterId={chapterId}
          projectId={projectId}
          writing={writing}
          selection={null}
          client={api}
          usageClient={usage}
        />
      );
    }
    render(<Harness />);
    const comparison = await screen.findByRole("region", {
      name: "原文与候选对照",
    });
    expect(
      within(comparison)
        .getByRole("group", { name: "原文（删除部分划线）" })
        .querySelector("del"),
    ).toHaveTextContent("乙");
    expect(usage.page).not.toHaveBeenCalled();
    open();
    await screen.findByText("已发出的模型请求");
    expect(usage.page).toHaveBeenCalledWith(
      projectId,
      { chapterId, limit: 10 },
      expect.any(AbortSignal),
    );
    expect(api.action).not.toHaveBeenCalled();
    expect(api.candidate).not.toHaveBeenCalled();
  });

  it("omits the usage panel without a project id and shows continuation context", async () => {
    const api = workflow([
      { ...pending, operation: "continue", selected_text: "", max_steps: 5 },
    ]);
    function Harness() {
      const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
      return (
        <AIWorkflowAssistant
          chapterId={chapterId}
          writing={writing}
          selection={null}
          client={api}
        />
      );
    }
    render(<Harness />);
    await screen.findByRole("region", { name: "候选插入位置" });
    expect(screen.queryByText("本章模型用量")).not.toBeInTheDocument();
  });

  function open() {
    const details = screen.getByText("本章模型用量").closest("details")!;
    act(() => {
      details.open = true;
      fireEvent(details, new Event("toggle"));
    });
  }
});
