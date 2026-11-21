import { getJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";

/**
 * 模型用量台账（B1）。只读取已发出的模型请求记录，查看本身不调用模型。
 * 三种量严格分开：本机字符计数（估算依据，非 token）、服务商报告的 token、未知。
 * 未知不按 0 计；金额使用发送时冻结的作者价格，不是服务商账单。
 */
export type UsageOperation =
  | "generation"
  | "reference_analysis"
  | "story_review"
  | "connection_check"
  | "method_trial"
  | "plan_proposal"
  | "foreshadow_extraction"
  | "chapter_draft";
export type AttemptStatus =
  "running" | "completed" | "failed" | "timeout" | "interrupted";
export type UsageSource = "provider_reported" | "unknown";

export const OPERATION_LABELS: Record<UsageOperation, string> = {
  generation: "正文生成",
  reference_analysis: "范文分析",
  story_review: "一致性评审",
  connection_check: "连接测试消息",
  method_trial: "写作方法对照试写",
  plan_proposal: "规划拆分建议",
  foreshadow_extraction: "批量提取伏笔建议",
  chapter_draft: "章节候选稿",
};
export const STATUS_LABELS: Record<AttemptStatus, string> = {
  running: "进行中",
  completed: "已返回",
  failed: "失败",
  timeout: "超时（是否计费未知）",
  interrupted: "中断（是否计费未知）",
};

export interface UsageTotals {
  readonly attempts: number;
  readonly completed: number;
  readonly failed: number;
  readonly timeout: number;
  readonly interrupted: number;
  readonly running: number;
  readonly reported_attempts: number;
  readonly incomplete_reports: number;
  readonly unknown_attempts: number;
  readonly reported_input_tokens: number;
  readonly reported_output_tokens: number;
  readonly reported_total_tokens: number;
  readonly input_characters: number;
  readonly output_characters: number;
}
export interface UsageAttempt {
  readonly id: string;
  readonly chapter_id: string | null;
  readonly operation: UsageOperation;
  readonly task_id: string;
  readonly profile_id: string;
  readonly model_kind: "local" | "cloud";
  readonly model_name: string;
  readonly status: AttemptStatus;
  readonly error_code: string | null;
  readonly usage_source: UsageSource;
  readonly reported_input_tokens: number | null;
  readonly reported_output_tokens: number | null;
  readonly reported_total_tokens: number | null;
  readonly input_characters: number;
  readonly output_characters: number | null;
  readonly started_at: string;
  readonly finished_at: string | null;
  readonly duration_ms: number | null;
  readonly cached_input_tokens?: number | null;
  readonly cache_write_tokens?: number | null;
  readonly cache_details_status?: "not_reported" | "reported" | "invalid";
  readonly price_version?: number | null;
  readonly input_per_million?: string | null;
  readonly output_per_million?: string | null;
  readonly cached_input_per_million?: string | null;
  readonly cache_write_per_million?: string | null;
  readonly currency?: string | null;
  readonly amount?: string | null;
  readonly amount_basis?:
    | "reported_tokens"
    | "cache_upper"
    | "total_tokens_upper"
    | "reserved_upper"
    | "unknown"
    | "unpriced";
}
export interface UsagePage {
  readonly project_id: string;
  readonly chapter_id: string | null;
  readonly task_id: string | null;
  readonly estimate_method: "local_characters_v1";
  readonly totals: UsageTotals;
  readonly by_operation: readonly {
    readonly operation: UsageOperation;
    readonly totals: UsageTotals;
  }[];
  readonly by_model: readonly {
    readonly model_kind: "local" | "cloud";
    readonly model_name: string;
    readonly totals: UsageTotals;
  }[];
  readonly items: readonly UsageAttempt[];
  readonly total: number;
  readonly next_offset: number | null;
}
export interface UsageQuery {
  readonly chapterId?: string;
  readonly taskId?: string;
  readonly offset?: number;
  readonly limit?: number;
}

export class UsageError extends Error {
  public readonly code: string;
  public constructor(message: string, code = "NETWORK") {
    super(message);
    this.name = "UsageError";
    this.code = code;
  }
}

function invalid(): never {
  throw new UsageError(
    "模型用量数据无法安全读取，请刷新。",
    "INVALID_RESPONSE",
  );
}
function obj(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
  return value as Record<string, unknown>;
}
function str(value: unknown): string {
  if (typeof value !== "string") invalid();
  return value;
}
function id(value: unknown): string {
  const result = str(value);
  if (!/^[A-Za-z0-9_-]{1,100}$/u.test(result)) invalid();
  return result;
}
function count(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    invalid();
  return value;
}
function nullable<T>(value: unknown, decode: (v: unknown) => T): T | null {
  return value === null ? null : decode(value);
}
function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T {
  if (!allowed.includes(value as T)) invalid();
  return value as T;
}
function list<T>(value: unknown, decode: (v: unknown) => T): T[] {
  if (!Array.isArray(value)) invalid();
  return value.map(decode);
}
const OPERATIONS = Object.keys(OPERATION_LABELS) as UsageOperation[];
const STATUSES = Object.keys(STATUS_LABELS) as AttemptStatus[];
const KINDS = ["local", "cloud"] as const;

function parseTotals(value: unknown): UsageTotals {
  const item = obj(value);
  const totals = {
    attempts: count(item.attempts),
    completed: count(item.completed),
    failed: count(item.failed),
    timeout: count(item.timeout),
    interrupted: count(item.interrupted),
    running: count(item.running),
    reported_attempts: count(item.reported_attempts),
    incomplete_reports: count(item.incomplete_reports),
    unknown_attempts: count(item.unknown_attempts),
    reported_input_tokens: count(item.reported_input_tokens),
    reported_output_tokens: count(item.reported_output_tokens),
    reported_total_tokens: count(item.reported_total_tokens),
    input_characters: count(item.input_characters),
    output_characters: count(item.output_characters),
  };
  if (
    totals.reported_attempts + totals.unknown_attempts !== totals.attempts ||
    totals.incomplete_reports > totals.reported_attempts
  )
    invalid();
  return totals;
}

export function parseUsageAttempt(value: unknown): UsageAttempt {
  const item = obj(value);
  const source = oneOf(item.usage_source, [
    "provider_reported",
    "unknown",
  ] as const);
  const attempt: UsageAttempt = {
    id: id(item.id),
    chapter_id: nullable(item.chapter_id, id),
    operation: oneOf(item.operation, OPERATIONS),
    task_id: id(item.task_id),
    profile_id: str(item.profile_id),
    model_kind: oneOf(item.model_kind, KINDS),
    model_name: str(item.model_name),
    status: oneOf(item.status, STATUSES),
    error_code: nullable(item.error_code, str),
    usage_source: source,
    reported_input_tokens: nullable(item.reported_input_tokens, count),
    reported_output_tokens: nullable(item.reported_output_tokens, count),
    reported_total_tokens: nullable(item.reported_total_tokens, count),
    input_characters: count(item.input_characters),
    output_characters: nullable(item.output_characters, count),
    started_at: str(item.started_at),
    finished_at: nullable(item.finished_at, str),
    duration_ms: nullable(item.duration_ms, count),
    ...(item.cache_details_status === undefined
      ? {}
      : {
          cached_input_tokens: nullable(item.cached_input_tokens, count),
          cache_write_tokens: nullable(item.cache_write_tokens, count),
          cache_details_status: oneOf(item.cache_details_status, [
            "not_reported",
            "reported",
            "invalid",
          ] as const),
          price_version: nullable(item.price_version, count),
          input_per_million: nullable(item.input_per_million, str),
          output_per_million: nullable(item.output_per_million, str),
          cached_input_per_million: nullable(
            item.cached_input_per_million,
            str,
          ),
          cache_write_per_million: nullable(item.cache_write_per_million, str),
          currency: nullable(item.currency, str),
          amount: nullable(item.amount, str),
          amount_basis: oneOf(item.amount_basis, [
            "reported_tokens",
            "cache_upper",
            "total_tokens_upper",
            "reserved_upper",
            "unknown",
            "unpriced",
          ] as const),
        }),
  };
  const reported =
    attempt.reported_input_tokens !== null ||
    attempt.reported_output_tokens !== null ||
    attempt.reported_total_tokens !== null;
  // An unknown attempt must never carry token numbers (unknown is not zero).
  if ((source === "unknown") === reported) invalid();
  return attempt;
}

export function parseUsagePage(value: unknown, project: string): UsagePage {
  const item = obj(value);
  if (item.project_id !== project) invalid();
  if (item.estimate_method !== "local_characters_v1") invalid();
  return {
    project_id: project,
    chapter_id: nullable(item.chapter_id, id),
    task_id: nullable(item.task_id, id),
    estimate_method: "local_characters_v1",
    totals: parseTotals(item.totals),
    by_operation: list(item.by_operation, (raw) => {
      const entry = obj(raw);
      return {
        operation: oneOf(entry.operation, OPERATIONS),
        totals: parseTotals(entry.totals),
      };
    }),
    by_model: list(item.by_model, (raw) => {
      const entry = obj(raw);
      return {
        model_kind: oneOf(entry.model_kind, KINDS),
        model_name: str(entry.model_name),
        totals: parseTotals(entry.totals),
      };
    }),
    items: list(item.items, parseUsageAttempt),
    total: count(item.total),
    next_offset: nullable(item.next_offset, count),
  };
}

const MESSAGES: Record<string, string> = {
  AI_WORKFLOW_SCHEMA_REQUIRED:
    "需要先“备份并启用 AI 协作”（数据库升级）后才能查看模型用量。",
  USAGE_LEDGER_UNAVAILABLE: "模型用量记录暂不可用；写作不受影响。",
  PROJECT_NOT_FOUND: "这本小说已不存在或已删除。",
  INVALID_USAGE_QUERY: "用量查询参数无效，请刷新。",
};

export function usageError(error: unknown): UsageError {
  if (error instanceof UsageError) return error;
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) securitySession.clear();
    if (error.code === "INVALID_RESPONSE")
      return new UsageError(
        "模型用量数据无法安全读取，请刷新。",
        "INVALID_RESPONSE",
      );
    return new UsageError(
      MESSAGES[error.code] ?? "模型用量读取失败，请稍后重试；写作不受影响。",
      error.code,
    );
  }
  return new UsageError("连接中断，模型用量暂未读取，可以重试。");
}

export const usageClient = {
  page: async (
    project: string,
    query: UsageQuery = {},
    signal?: AbortSignal,
  ): Promise<UsagePage> => {
    const params = new URLSearchParams({
      offset: String(query.offset ?? 0),
      limit: String(query.limit ?? 20),
    });
    if (query.chapterId !== undefined)
      params.set("chapter_id", id(query.chapterId));
    if (query.taskId !== undefined) params.set("task_id", id(query.taskId));
    try {
      const result = await getJson(
        `projects/${id(project)}/usage?${params.toString()}`,
        (value) => parseUsagePage(value, project),
        { signal },
      );
      return result.data;
    } catch (error) {
      throw usageError(error);
    }
  },
};
export type UsageClient = typeof usageClient;
