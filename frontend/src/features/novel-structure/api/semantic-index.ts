import { getJson, postJson, putJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";
import { parseEstimate, type SendEstimate } from "../../usage/api/budget";
import { AIWritingError } from "./ai-writing";
import { workflowFailureMessage } from "./ai-workflow";

/**
 * C-4 语义索引：读取状态/预估从不调用模型；建立或增量更新必须由作者确认预估后手动触发，
 * 每次请求计入用量（semantic_index）并受预算约束。
 */
export interface SemanticSettings {
  readonly version: number;
  readonly enabled: boolean;
  readonly profile_id: string | null;
  readonly updated_at: string | null;
}
export interface SemanticPlan {
  readonly plan_version: string;
  readonly fact_items: number;
  readonly chunk_items: number;
  readonly requests: number;
  readonly input_characters: number;
  readonly deferred_items: number;
  readonly obsolete_entries: number;
}
export interface SemanticIndexStatus {
  readonly project_id: string;
  readonly settings: SemanticSettings;
  readonly profile: {
    readonly id: string;
    readonly name: string;
    readonly kind: "local" | "cloud";
    readonly model: string;
  } | null;
  readonly profile_problem:
    "not_configured" | "not_found" | "not_embedding" | null;
  readonly facts_total: number;
  readonly facts_indexed: number;
  readonly chapters_total: number;
  readonly chapters_indexed: number;
  readonly stale_entries: number;
  readonly up_to_date: boolean;
  readonly plan: SemanticPlan | null;
  readonly estimate: SendEstimate | null;
}
export interface SemanticBuildResult {
  readonly build_id: string;
  readonly requests_sent: number;
  readonly items_indexed: number;
  readonly entries_removed: number;
  readonly status: SemanticIndexStatus;
}

function invalid(): never {
  throw new AIWritingError(
    "语义索引数据无法安全读取，请刷新。",
    "INVALID_RESPONSE",
  );
}
function obj(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
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
function bool(value: unknown): boolean {
  if (typeof value !== "boolean") invalid();
  return value;
}
function nullableStr(value: unknown): string | null {
  return value === null ? null : str(value);
}
function id(value: string): string {
  if (!/^[A-Za-z0-9_-]{1,60}$/u.test(value)) invalid();
  return value;
}
function parseSettings(value: unknown): SemanticSettings {
  const item = obj(value);
  return {
    version: count(item.version),
    enabled: bool(item.enabled),
    profile_id: nullableStr(item.profile_id),
    updated_at: nullableStr(item.updated_at),
  };
}
const PROBLEMS = ["not_configured", "not_found", "not_embedding"] as const;
export function parseSemanticStatus(
  value: unknown,
  project: string,
): SemanticIndexStatus {
  const item = obj(value);
  if (item.project_id !== project) invalid();
  const problem = item.profile_problem;
  if (
    problem !== null &&
    !PROBLEMS.includes(problem as (typeof PROBLEMS)[number])
  )
    invalid();
  const profile = item.profile === null ? null : obj(item.profile);
  if (profile && profile.kind !== "local" && profile.kind !== "cloud")
    invalid();
  const plan = item.plan === null ? null : obj(item.plan);
  if (plan && !/^[0-9a-f]{64}$/u.test(str(plan.plan_version))) invalid();
  return {
    project_id: project,
    settings: parseSettings(item.settings),
    profile: profile
      ? {
          id: str(profile.id),
          name: str(profile.name),
          kind: profile.kind as "local" | "cloud",
          model: str(profile.model),
        }
      : null,
    profile_problem: problem as SemanticIndexStatus["profile_problem"],
    facts_total: count(item.facts_total),
    facts_indexed: count(item.facts_indexed),
    chapters_total: count(item.chapters_total),
    chapters_indexed: count(item.chapters_indexed),
    stale_entries: count(item.stale_entries),
    up_to_date: bool(item.up_to_date),
    plan: plan
      ? {
          plan_version: str(plan.plan_version),
          fact_items: count(plan.fact_items),
          chunk_items: count(plan.chunk_items),
          requests: count(plan.requests),
          input_characters: count(plan.input_characters),
          deferred_items: count(plan.deferred_items),
          obsolete_entries: count(plan.obsolete_entries),
        }
      : null,
    estimate: item.estimate === null ? null : parseEstimate(item.estimate),
  };
}

const MESSAGES: Record<string, string> = {
  SEMANTIC_INDEX_CONFLICT:
    "索引计划、价格或设置已变化。请查看新的预估后再确认；未发送任何请求。",
  SEMANTIC_INDEX_CONFIRMATION_REQUIRED:
    "请先勾选确认预估 token 与费用（云端模型还需同意发送）；未发送任何请求。",
  SEMANTIC_INDEX_UP_TO_DATE: "语义索引已是最新，无需更新。",
  SEMANTIC_INDEX_INVALID: "请选择一个“嵌入（语义索引）”用途的模型配置。",
  SEMANTIC_INDEX_UNAVAILABLE: "语义索引暂不可用；确定性召回不受影响。",
  AI_BUDGET_REFUSED:
    "预估费用超出本书严格预算（或嵌入模型未填单价），未发送任何请求。",
};
export function semanticError(error: unknown): AIWritingError {
  if (error instanceof AIWritingError) return error;
  if (error instanceof ApiError) {
    if (
      error.status === 401 ||
      (error.status === 403 &&
        error.code !== "SEMANTIC_INDEX_CONFIRMATION_REQUIRED")
    )
      securitySession.clear();
    return new AIWritingError(
      MESSAGES[error.code] ??
        `${workflowFailureMessage(error.code)} 已完成的批次会保留，未完成的部分可在查看新预估后再次确认更新。`,
      error.code,
    );
  }
  return new AIWritingError("连接中断，请刷新查看索引状态；请求不会自动重发。");
}
async function request<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw semanticError(error);
  }
}
async function mutate<T>(
  path: string,
  input: unknown,
  decode: (value: unknown) => T,
  put = false,
): Promise<T> {
  return request(async () => {
    const session = await securitySession.getValidSession();
    return (put ? putJson : postJson)(path, input, decode, {
      headers: { "X-CSRF-Token": session.csrfToken },
    });
  });
}
const base = (project: string) => `projects/${id(project)}/semantic-index`;

export const semanticIndexClient = {
  status: (project: string) =>
    request(() =>
      getJson(base(project), (value) => parseSemanticStatus(value, project)),
    ),
  saveSettings: (
    project: string,
    input: {
      readonly expected_version: number;
      readonly enabled: boolean;
      readonly profile_id: string | null;
    },
  ) => mutate(`${base(project)}/settings`, input, parseSettings, true),
  build: (
    project: string,
    input: {
      readonly plan_version: string;
      readonly confirm_estimate: true;
      readonly cloud_consent: boolean;
    },
  ) =>
    mutate(`${base(project)}/build`, input, (value) => {
      const item = obj(value);
      return {
        build_id: str(item.build_id),
        requests_sent: count(item.requests_sent),
        items_indexed: count(item.items_indexed),
        entries_removed: count(item.entries_removed),
        status: parseSemanticStatus(item.status, project),
      } satisfies SemanticBuildResult;
    }),
};
export type SemanticIndexClient = typeof semanticIndexClient;
