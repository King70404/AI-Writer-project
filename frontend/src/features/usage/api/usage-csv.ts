import {
  OPERATION_LABELS,
  STATUS_LABELS,
  type UsageAttempt,
  type UsageClient,
} from "./usage";

/** Export cap: the ledger API pages 100 rows; more than this is refused, not truncated. */
export const MAX_EXPORT_ROWS = 5000;

const HEADER = [
  "开始时间",
  "结束时间",
  "章节",
  "操作",
  "任务",
  "模型配置",
  "模型类型",
  "模型",
  "状态",
  "错误代码",
  "用量来源",
  "报告输入 token",
  "报告输出 token",
  "报告合计 token",
  "本机输入字符",
  "本机输出字符",
  "耗时毫秒",
] as const;

export class UsageExportTooLarge extends Error {
  public constructor() {
    super(`用量记录超过 ${MAX_EXPORT_ROWS} 条，请按章节筛选后再导出。`);
    this.name = "UsageExportTooLarge";
  }
}

function cell(value: string | number | null): string {
  const text = value === null ? "未知" : String(value);
  // Neutralise spreadsheet formulas and quote every cell.
  const safe = /^[=+\-@\t\r]/u.test(text) ? `'${text}` : text;
  return `"${safe.replaceAll('"', '""')}"`;
}

function row(item: UsageAttempt): string {
  return [
    item.started_at,
    item.finished_at ?? "",
    item.chapter_id ?? "",
    OPERATION_LABELS[item.operation],
    item.task_id,
    item.profile_id,
    item.model_kind === "local" ? "本地" : "云端",
    item.model_name,
    STATUS_LABELS[item.status],
    item.error_code ?? "",
    item.usage_source === "provider_reported" ? "服务商报告" : "未知",
    item.reported_input_tokens,
    item.reported_output_tokens,
    item.reported_total_tokens,
    item.input_characters,
    item.output_characters,
    item.duration_ms,
  ]
    .map((value) => (value === "" ? '""' : cell(value)))
    .join(",");
}

/** UTF-8 with BOM so spreadsheet apps read the Chinese headers. No text, keys or URLs. */
export function usageCsv(items: readonly UsageAttempt[]): string {
  return (
    "\uFEFF" +
    [HEADER.map(cell).join(","), ...items.map(row)].join("\r\n") +
    "\r\n"
  );
}

export async function collectUsage(
  client: UsageClient,
  projectId: string,
  chapterId?: string,
): Promise<readonly UsageAttempt[]> {
  const items: UsageAttempt[] = [];
  let offset: number | null = 0;
  while (offset !== null) {
    const page = await client.page(projectId, {
      chapterId,
      offset,
      limit: 100,
    });
    if (page.total > MAX_EXPORT_ROWS) throw new UsageExportTooLarge();
    items.push(...page.items);
    offset = page.next_offset;
  }
  return items;
}

export function downloadUsageCsv(text: string): void {
  const url = URL.createObjectURL(
    new Blob([text], { type: "text/csv;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  try {
    anchor.href = url;
    anchor.download = "模型用量.csv";
    document.body.append(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(url);
  }
}
