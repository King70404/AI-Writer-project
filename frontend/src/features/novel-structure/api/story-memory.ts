import { getJson, postJson, putJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";
import { AIWritingError } from "./ai-writing";
import { workflowFailureMessage } from "./ai-workflow";

export interface MemoryFact {
  readonly id: string;
  readonly revision_id: string;
  readonly project_id: string;
  readonly chapter_id: string;
  readonly version: number;
  readonly source_revision: string;
  readonly title: string;
  readonly text: string;
  readonly quote: string;
  readonly status: "pending" | "confirmed" | "rejected";
  readonly stale: boolean;
}
export interface SuggestedFact {
  readonly title: string;
  readonly text: string;
  readonly quote: string;
}
export interface MemoryFinding {
  readonly quote: string;
  readonly explanation: string;
  readonly instruction: string;
  readonly fact_ids: readonly string[];
}
export interface MemoryReview {
  readonly id: string;
  readonly chapter_id: string;
  readonly source_revision: string;
  readonly version: number;
  readonly content: string;
  readonly content_truncated: boolean;
  readonly facts: readonly (SuggestedFact & { readonly id: string })[];
  readonly omitted_facts: number;
  readonly model: {
    readonly name: string;
    readonly kind: "local" | "cloud";
    readonly base_url: string;
  };
  readonly status: "ready" | "running" | "completed" | "failed";
  readonly attempts: number;
  readonly last_error: string | null;
  readonly stale: boolean;
  readonly result: null | {
    readonly summary: string;
    readonly facts: readonly SuggestedFact[];
    readonly findings: readonly MemoryFinding[];
  };
}
export interface MemoryWorkspace {
  readonly project_id: string;
  readonly chapter_id: string;
  readonly source_revision: string;
  readonly facts: readonly MemoryFact[];
  readonly reviews: readonly MemoryReview[];
  readonly recalled_facts: readonly (SuggestedFact & { readonly id: string })[];
  readonly omitted_facts: number;
  readonly impacts: readonly {
    readonly chapter_id: string;
    readonly title: string;
    readonly reason: string;
  }[];
}
export interface FactInput extends SuggestedFact {
  readonly expected_version: number;
  readonly source_revision: string;
  readonly status: MemoryFact["status"];
}

function invalid(): never {
  throw new AIWritingError(
    "故事记忆数据无法安全读取，请刷新。",
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
  if (!/^[A-Za-z0-9_-]{1,60}$/u.test(result)) invalid();
  return result;
}
function number(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    invalid();
  return value;
}
function bool(value: unknown): boolean {
  if (typeof value !== "boolean") invalid();
  return value;
}
function array<T>(value: unknown, decode: (v: unknown) => T): T[] {
  if (!Array.isArray(value)) invalid();
  return value.map(decode);
}
function suggested(value: unknown): SuggestedFact {
  const item = obj(value);
  return {
    title: str(item.title),
    text: str(item.text),
    quote: str(item.quote),
  };
}
function frozen(value: unknown): SuggestedFact & { readonly id: string } {
  return { ...suggested(value), id: id(obj(value).id) };
}
export function parseMemoryFact(value: unknown, project: string): MemoryFact {
  const item = obj(value);
  if (
    item.project_id !== project ||
    item.kind !== "fact" ||
    !["pending", "confirmed", "rejected"].includes(str(item.status))
  )
    invalid();
  return {
    ...suggested(item),
    id: id(item.id),
    revision_id: id(item.revision_id),
    project_id: project,
    chapter_id: id(item.chapter_id),
    version: number(item.version),
    source_revision: id(item.source_revision),
    status: item.status as MemoryFact["status"],
    stale: bool(item.stale),
  };
}
export function parseMemoryReview(
  value: unknown,
  project: string,
  chapter: string,
): MemoryReview {
  const item = obj(value),
    model = obj(item.model);
  if (
    item.project_id !== project ||
    item.chapter_id !== chapter ||
    item.kind !== "review" ||
    !["ready", "running", "completed", "failed"].includes(str(item.status)) ||
    !["local", "cloud"].includes(str(model.kind))
  )
    invalid();
  const content = str(item.content);
  const facts = array(item.facts, frozen);
  const result = item.result === null ? null : obj(item.result);
  const findings =
    result === null
      ? []
      : array(result.findings, (raw): MemoryFinding => {
          const finding = obj(raw),
            quote = str(finding.quote),
            factIds = array(finding.fact_ids, id);
          if (
            !quote.trim() ||
            !content.includes(quote) ||
            factIds.some((value) => !facts.some((fact) => fact.id === value))
          )
            invalid();
          return {
            quote,
            explanation: str(finding.explanation),
            instruction: str(finding.instruction),
            fact_ids: factIds,
          };
        });
  const suggestions = result === null ? [] : array(result.facts, suggested);
  if (
    suggestions.some(
      (fact) => !fact.quote.trim() || !content.includes(fact.quote),
    )
  )
    invalid();
  return {
    id: id(item.id),
    chapter_id: chapter,
    source_revision: id(item.source_revision),
    version: number(item.version),
    content,
    content_truncated: bool(item.content_truncated),
    facts,
    omitted_facts: number(item.omitted_facts),
    model: {
      name: str(model.name),
      kind: model.kind as "local" | "cloud",
      base_url: str(model.base_url),
    },
    status: item.status as MemoryReview["status"],
    attempts: number(item.attempts),
    last_error: item.last_error === null ? null : str(item.last_error),
    stale: bool(item.stale),
    result:
      result === null
        ? null
        : { summary: str(result.summary), facts: suggestions, findings },
  };
}
export function parseMemoryWorkspace(
  value: unknown,
  project: string,
  chapter: string,
): MemoryWorkspace {
  const item = obj(value);
  if (item.project_id !== project || item.chapter_id !== chapter) invalid();
  return {
    project_id: project,
    chapter_id: chapter,
    source_revision: id(item.source_revision),
    facts: array(item.facts, (value) => parseMemoryFact(value, project)),
    reviews: array(item.reviews, (value) =>
      parseMemoryReview(value, project, chapter),
    ),
    recalled_facts: array(item.recalled_facts, frozen),
    omitted_facts: number(item.omitted_facts),
    impacts: array(item.impacts, (raw) => {
      const impact = obj(raw);
      return {
        chapter_id: id(impact.chapter_id),
        title: str(impact.title),
        reason: str(impact.reason),
      };
    }),
  };
}
export function memoryError(error: unknown): AIWritingError {
  if (error instanceof AIWritingError) return error;
  if (error instanceof ApiError) {
    if (
      error.status === 401 ||
      (error.status === 403 && error.code !== "MEMORY_CONSENT_REQUIRED")
    )
      securitySession.clear();
    const messages: Record<string, string> = {
      MEMORY_CONFLICT:
        "正文、事实或评审已变化。草稿已保留，请刷新记忆后核对最新来源。",
      MEMORY_INVALID:
        "输入或模型回复无效：引文必须来自当前正文，模型输出须完整且引用有效事实。",
      MEMORY_CONSENT_REQUIRED: "请先勾选向此云模型发送预览内容的同意。",
      MEMORY_NOT_FOUND: "事实或评审不存在于当前章节，请刷新。",
      AI_WORKFLOW_SCHEMA_REQUIRED:
        "请先点击“备份并启用 AI 协作”，再使用故事记忆。",
      MEMORY_UNAVAILABLE: "故事记忆暂不可用，请重启并启用新版 AI 协作。",
    };
    return new AIWritingError(
      messages[error.code] ?? workflowFailureMessage(error.code),
      error.code,
    );
  }
  return new AIWritingError(
    "连接中断，请刷新查看已保存状态；模型请求不会自动重发。",
  );
}
async function request<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw memoryError(error);
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
function path(chapter: string): string {
  return `chapters/${id(chapter)}/memory`;
}
export const storyMemoryClient = {
  workspace: (project: string, chapter: string) =>
    request(() =>
      getJson(path(chapter), (value) =>
        parseMemoryWorkspace(value, project, chapter),
      ),
    ),
  fact: (project: string, chapter: string, input: FactInput, factId?: string) =>
    mutate(
      `${path(chapter)}/facts${factId ? `/${id(factId)}` : ""}`,
      input,
      (value) => parseMemoryFact(value, project),
      !!factId,
    ),
  prepare: (
    project: string,
    chapter: string,
    revision: string,
    profile: string,
  ) =>
    mutate(
      `${path(chapter)}/reviews`,
      { source_revision: revision, profile_id: profile },
      (value) => parseMemoryReview(value, project, chapter),
    ),
  send: (
    project: string,
    chapter: string,
    review: MemoryReview,
    consent: boolean,
  ) =>
    mutate(
      `${path(chapter)}/reviews/${id(review.id)}/send`,
      { expected_version: review.version, cloud_consent: consent },
      (value) => parseMemoryReview(value, project, chapter),
    ),
};
export type StoryMemoryClient = typeof storyMemoryClient;
