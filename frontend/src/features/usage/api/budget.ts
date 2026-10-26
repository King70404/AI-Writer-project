import { getJson, putJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";

/**
 * 价格、预算与发送前预估（B2）。价格只由作者填写，不预置；金额只在同一币种内相加，
 * 不换汇。预估是保守上限而非账单：输入按 UTF-8 字节数给出 token 上限，输出按模型
 * 配置的最大输出 token。未知用量按保守预留计入“待确认”，从不按 0 计。
 */
export type BudgetMode = "off" | "warn" | "strict";
export type BudgetDecision = "allowed" | "warning" | "refused";
export type BudgetReason =
  | "PRICE_MISSING"
  | "CURRENCY_MISMATCH"
  | "UNPRICED_HISTORY"
  | "TASK_LIMIT_EXCEEDED"
  | "MONTHLY_LIMIT_EXCEEDED";

export const REASON_LABELS: Record<BudgetReason, string> = {
  PRICE_MISSING: "当前模型未填写价格，无法估算金额",
  CURRENCY_MISMATCH: "模型价格币种与预算币种不同，不会自动换汇",
  UNPRICED_HISTORY: "本月或本任务有填写价格前发出的请求，金额无法确定",
  TASK_LIMIT_EXCEEDED: "加上本次保守预估会超过单任务预算",
  MONTHLY_LIMIT_EXCEEDED: "加上本次保守预估会超过本书本月预算",
};
export const MODE_LABELS: Record<BudgetMode, string> = {
  off: "不设预算",
  warn: "提示模式（超出时提醒，由你确认）",
  strict: "严格模式（可能超出时拒绝发送）",
};

export interface PriceView {
  readonly profile_id: string;
  readonly version: number;
  readonly currency: string;
  readonly input_per_million: string;
  readonly output_per_million: string;
  readonly created_at: string;
}
export interface PriceState {
  readonly profile_id: string;
  readonly current: PriceView | null;
  readonly history: readonly PriceView[];
}
export interface SpendView {
  readonly currency: string | null;
  readonly attempts: number;
  readonly settled: string;
  readonly pending: string;
  readonly upper: string;
  readonly unpriced_attempts: number;
  readonly other_currency_attempts: number;
}
export interface BudgetView {
  readonly project_id: string;
  readonly version: number;
  readonly mode: BudgetMode;
  readonly currency: string | null;
  readonly task_limit: string | null;
  readonly monthly_limit: string | null;
  readonly created_at: string | null;
  readonly month_start: string;
  readonly month: SpendView;
}
export interface SendEstimate {
  readonly estimate_method: "utf8_bytes_upper_v1";
  readonly profile_id: string;
  readonly input_characters: number;
  readonly input_tokens_upper: number;
  readonly output_tokens_upper: number;
  readonly price: PriceView | null;
  readonly estimated_cost_upper: string | null;
  readonly currency: string | null;
  readonly budget_mode: BudgetMode;
  readonly budget_currency: string | null;
  readonly task_limit: string | null;
  readonly monthly_limit: string | null;
  readonly task_spent_upper: string | null;
  readonly month_spent_upper: string | null;
  readonly unpriced_attempts: number;
  readonly decision: BudgetDecision;
  readonly reasons: readonly BudgetReason[];
}
export interface BudgetInput {
  readonly expected_version: number;
  readonly mode: BudgetMode;
  readonly currency: string | null;
  readonly task_limit: string | null;
  readonly monthly_limit: string | null;
}
export interface PriceInput {
  readonly expected_version: number;
  readonly currency: string;
  readonly input_per_million: string;
  readonly output_per_million: string;
}

export class BudgetError extends Error {
  constructor(
    message: string,
    readonly code = "BUDGET_ERROR",
  ) {
    super(message);
    this.name = "BudgetError";
  }
}

const AMOUNT = /^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?$/u;
const CURRENCY = /^[A-Z]{3}$/u;
const MODES: readonly BudgetMode[] = ["off", "warn", "strict"];
const DECISIONS: readonly BudgetDecision[] = ["allowed", "warning", "refused"];
const REASONS = Object.keys(REASON_LABELS) as BudgetReason[];

function invalid(): never {
  throw new BudgetError(
    "预算或价格数据无法安全读取，请刷新。",
    "INVALID_RESPONSE",
  );
}
function obj(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    invalid();
  return value as Record<string, unknown>;
}
function count(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    invalid();
  return value;
}
function str(value: unknown): string {
  if (typeof value !== "string") invalid();
  return value;
}
function amount(value: unknown): string {
  if (typeof value !== "string" || !AMOUNT.test(value)) invalid();
  return value;
}
function currency(value: unknown): string {
  if (typeof value !== "string" || !CURRENCY.test(value)) invalid();
  return value;
}
function nullable<T>(value: unknown, parse: (raw: unknown) => T): T | null {
  return value === null ? null : parse(value);
}
function oneOf<T extends string>(value: unknown, options: readonly T[]): T {
  if (typeof value !== "string" || !options.includes(value as T)) invalid();
  return value as T;
}
function identifier(value: string): string {
  if (!/^[A-Za-z0-9_-]{1,100}$/u.test(value)) invalid();
  return value;
}

export function isAmount(value: string): boolean {
  return AMOUNT.test(value);
}
export function isCurrency(value: string): boolean {
  return CURRENCY.test(value);
}

export function parsePrice(value: unknown): PriceView {
  const item = obj(value);
  return {
    profile_id: str(item.profile_id),
    version: count(item.version),
    currency: currency(item.currency),
    input_per_million: amount(item.input_per_million),
    output_per_million: amount(item.output_per_million),
    created_at: str(item.created_at),
  };
}
export function parsePriceState(value: unknown, profileId: string): PriceState {
  const item = obj(value);
  if (item.profile_id !== profileId || !Array.isArray(item.history)) invalid();
  return {
    profile_id: profileId,
    current: nullable(item.current, parsePrice),
    history: item.history.map(parsePrice),
  };
}
function parseSpend(value: unknown): SpendView {
  const item = obj(value);
  return {
    currency: nullable(item.currency, currency),
    attempts: count(item.attempts),
    settled: amount(item.settled),
    pending: amount(item.pending),
    upper: amount(item.upper),
    unpriced_attempts: count(item.unpriced_attempts),
    other_currency_attempts: count(item.other_currency_attempts),
  };
}
export function parseBudget(value: unknown, projectId: string): BudgetView {
  const item = obj(value);
  if (item.project_id !== projectId) invalid();
  return {
    project_id: projectId,
    version: count(item.version),
    mode: oneOf(item.mode, MODES),
    currency: nullable(item.currency, currency),
    task_limit: nullable(item.task_limit, amount),
    monthly_limit: nullable(item.monthly_limit, amount),
    created_at: nullable(item.created_at, str),
    month_start: str(item.month_start),
    month: parseSpend(item.month),
  };
}
export function parseEstimate(value: unknown): SendEstimate {
  const item = obj(value);
  if (
    item.estimate_method !== "utf8_bytes_upper_v1" ||
    !Array.isArray(item.reasons)
  )
    invalid();
  return {
    estimate_method: "utf8_bytes_upper_v1",
    profile_id: str(item.profile_id),
    input_characters: count(item.input_characters),
    input_tokens_upper: count(item.input_tokens_upper),
    output_tokens_upper: count(item.output_tokens_upper),
    price: nullable(item.price, parsePrice),
    estimated_cost_upper: nullable(item.estimated_cost_upper, amount),
    currency: nullable(item.currency, currency),
    budget_mode: oneOf(item.budget_mode, MODES),
    budget_currency: nullable(item.budget_currency, currency),
    task_limit: nullable(item.task_limit, amount),
    monthly_limit: nullable(item.monthly_limit, amount),
    task_spent_upper: nullable(item.task_spent_upper, amount),
    month_spent_upper: nullable(item.month_spent_upper, amount),
    unpriced_attempts: count(item.unpriced_attempts),
    decision: oneOf(item.decision, DECISIONS),
    reasons: item.reasons.map((reason: unknown) => oneOf(reason, REASONS)),
  };
}

const MESSAGES: Record<string, string> = {
  AI_WORKFLOW_SCHEMA_REQUIRED:
    "需要先“备份并启用 AI 协作”（数据库升级）后才能设置价格与预算。",
  USAGE_BUDGET_UNAVAILABLE: "价格与预算暂不可用；写作不受影响。",
  BUDGET_INPUT_INVALID:
    "请检查输入：币种为 3 位大写字母（如 CNY），金额为不超过 6 位小数的非负数；启用预算需填写币种和至少一项上限。",
  BUDGET_VERSION_CONFLICT: "设置已在其他窗口修改，请刷新后再保存。",
  PROJECT_NOT_FOUND: "这本小说已不存在或已删除。",
  MODEL_PROFILE_NOT_FOUND: "该模型配置已不存在，请刷新模型列表。",
};

function budgetError(error: unknown): BudgetError {
  if (error instanceof BudgetError) return error;
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) securitySession.clear();
    if (error.code === "INVALID_RESPONSE")
      return new BudgetError(
        "预算或价格数据无法安全读取，请刷新。",
        error.code,
      );
    return new BudgetError(
      MESSAGES[error.code] ??
        "预算或价格操作未完成，请稍后重试；写作不受影响。",
      error.code,
    );
  }
  return new BudgetError(
    "连接中断，未能确认预算或价格，请重试。",
    "NETWORK_ERROR",
  );
}

async function call<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw budgetError(error);
  }
}
async function put<T>(
  path: string,
  body: unknown,
  decode: (value: unknown) => T,
) {
  return call(async () => {
    const proof = await securitySession.getValidSession();
    return putJson(path, body, decode, {
      headers: { "X-CSRF-Token": proof.csrfToken },
    });
  });
}

export const budgetClient = {
  price: (profileId: string) =>
    call(() =>
      getJson(`ai/models/${identifier(profileId)}/price`, (value) =>
        parsePriceState(value, profileId),
      ),
    ),
  savePrice: (profileId: string, input: PriceInput) =>
    put(`ai/models/${identifier(profileId)}/price`, input, (value) =>
      parsePriceState(value, profileId),
    ),
  budget: (projectId: string) =>
    call(() =>
      getJson(`projects/${identifier(projectId)}/budget`, (value) =>
        parseBudget(value, projectId),
      ),
    ),
  saveBudget: (projectId: string, input: BudgetInput) =>
    put(`projects/${identifier(projectId)}/budget`, input, (value) =>
      parseBudget(value, projectId),
    ),
  estimate: (chapterId: string, runId: string) =>
    call(() =>
      getJson(
        `chapters/${identifier(chapterId)}/ai/runs/${identifier(runId)}/estimate`,
        parseEstimate,
      ),
    ),
};
export type BudgetClient = typeof budgetClient;
