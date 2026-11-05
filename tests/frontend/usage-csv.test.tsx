import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  UsageAttempt,
  UsageClient,
  UsagePage,
  UsageTotals,
} from "../../frontend/src/features/usage/api/usage";
import {
  MAX_EXPORT_ROWS,
  collectUsage,
  usageCsv,
} from "../../frontend/src/features/usage/api/usage-csv";
import { ModelUsagePanel } from "../../frontend/src/features/usage/components/ModelUsagePanel";

const totals: UsageTotals = {
  attempts: 1,
  completed: 1,
  failed: 0,
  timeout: 0,
  interrupted: 0,
  running: 0,
  reported_attempts: 1,
  incomplete_reports: 0,
  unknown_attempts: 0,
  reported_input_tokens: 10,
  reported_output_tokens: 20,
  reported_total_tokens: 30,
  input_characters: 40,
  output_characters: 50,
};
const attempt: UsageAttempt = {
  id: "a1",
  chapter_id: "chapter-1",
  operation: "generation",
  task_id: "run-1",
  profile_id: "default-local",
  model_kind: "local",
  model_name: '=cmd"x',
  status: "completed",
  error_code: null,
  usage_source: "provider_reported",
  reported_input_tokens: 10,
  reported_output_tokens: 20,
  reported_total_tokens: 30,
  input_characters: 40,
  output_characters: 50,
  started_at: "2026-11-05 9:00",
  finished_at: null,
  duration_ms: null,
};
function page(overrides: Partial<UsagePage> = {}): UsagePage {
  return {
    project_id: "p1",
    chapter_id: null,
    task_id: null,
    estimate_method: "local_characters_v1",
    totals,
    by_operation: [],
    by_model: [],
    items: [attempt],
    total: 1,
    next_offset: null,
    ...overrides,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("用量 CSV 导出", () => {
  it("带 BOM 和中文表头，未知值不写成 0，并中和公式", () => {
    const csv = usageCsv([
      attempt,
      {
        ...attempt,
        id: "a2",
        chapter_id: null,
        model_kind: "cloud",
        model_name: "m",
        status: "timeout",
        error_code: "AIProviderTimeout",
        usage_source: "unknown",
        reported_input_tokens: null,
        reported_output_tokens: null,
        reported_total_tokens: null,
        output_characters: null,
      },
    ]);
    expect(csv.startsWith('\uFEFF"开始时间"')).toBe(true);
    const lines = csv.trim().split("\r\n");
    expect(lines).toHaveLength(3);
    expect(lines[1]).toContain('"\'=cmd""x"');
    expect(lines[1]).toContain('"服务商报告","10","20","30","40","50","未知"');
    expect(lines[2]).toContain('"云端"');
    expect(lines[2]).toContain(
      '"未知","未知","未知","未知","40","未知","未知"',
    );
  });

  it("按页收集全部记录，超过上限时拒绝而不是截断", async () => {
    const client = {
      page: vi
        .fn()
        .mockResolvedValueOnce(page({ total: 2, next_offset: 1 }))
        .mockResolvedValueOnce(
          page({ total: 2, items: [{ ...attempt, id: "a2" }] }),
        ),
    } as unknown as UsageClient;
    const items = await collectUsage(client, "p1", "chapter-1");
    expect(items.map((item) => item.id)).toEqual(["a1", "a2"]);
    expect(client.page).toHaveBeenNthCalledWith(2, "p1", {
      chapterId: "chapter-1",
      offset: 1,
      limit: 100,
    });
    const big = {
      page: vi.fn().mockResolvedValue(page({ total: MAX_EXPORT_ROWS + 1 })),
    } as unknown as UsageClient;
    await expect(collectUsage(big, "p1")).rejects.toThrow(
      "请按章节筛选后再导出",
    );
  });

  it("面板按钮下载 CSV，失败时显示原因", async () => {
    const create = vi.fn(() => "blob:usage");
    const revoke = vi.fn();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: create,
      revokeObjectURL: revoke,
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const pageMock = vi
      .fn()
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(page({ total: MAX_EXPORT_ROWS + 1 }));
    const client = { page: pageMock } as unknown as UsageClient;
    const { container } = render(
      <ModelUsagePanel projectId="p1" title="用量" client={client} />,
    );
    const details = container.querySelector("details")!;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    fireEvent.click(await screen.findByRole("button", { name: "导出 CSV" }));
    await vi.waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenCalledTimes(1);
    expect(revoke).toHaveBeenCalledWith("blob:usage");
    fireEvent.click(screen.getByRole("button", { name: "导出 CSV" }));
    expect(
      await screen.findByText(/请按章节筛选后再导出/u),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
