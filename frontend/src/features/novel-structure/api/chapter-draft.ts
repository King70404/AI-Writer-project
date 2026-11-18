import { getJson, postJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";
import { parseEstimate, type SendEstimate } from "../../usage/api/budget";

/**
 * 章节候选稿（F05 扩展，`chapter_draft`）。作者为一章确认请求数与总字数额度后，
 * 准备只冻结当前已保存版本与写作上下文，不调用模型；每段都是一次单独计量的请求（200–300 字），
 * 失败即停止、不自动重试。前面未采用的段落只作为“本次候选稿”传给下一段，
 * 不会成为事实，也不进入其他任务。采用时核对基线版本，正文手改过则拒绝并保留候选稿。
 */
export type DraftStatus = "ready" | "running" | "failed" | "exhausted";
export type SegmentStatus = "pending" | "adopted";

export interface DraftSegment {
  readonly index: number;
  readonly attempt: number;
  readonly text: string;
  readonly characters: number;
  readonly model: string;
  readonly status: SegmentStatus;
  readonly adopted_revision_id: string | null;
}
export interface DraftFailure {
  readonly attempt: number;
  readonly error: string;
  readonly evidence: string | null;
  readonly evidence_truncated: boolean;
}
export interface DraftReceipt {
  readonly idempotency_key: string;
  readonly segment_indexes: readonly number[];
  readonly revision_id: string;
}
export interface ChapterDraft {
  readonly id: string;
  readonly chapter_id: string;
  readonly version: number;
  readonly status: DraftStatus;
  readonly model_name: string;
  readonly model_kind: "local" | "cloud";
  readonly instruction: string;
  readonly max_segments: number;
  readonly max_output_characters: number;
  readonly attempts: number;
  readonly generated_characters: number;
  readonly remaining_requests: number;
  readonly remaining_characters: number;
  readonly can_send: boolean;
  readonly base_revision_id: string;
  readonly current_revision_id: string;
  readonly included_sources: readonly string[];
  readonly omitted_sources: readonly string[];
  readonly segments: readonly DraftSegment[];
  readonly failures: readonly DraftFailure[];
  readonly receipts: readonly DraftReceipt[];
  readonly last_error: string | null;
  readonly writing_job_id: string | null;
  readonly next_request_preview: string;
}
export interface DraftSummary {
  readonly id: string;
  readonly status: DraftStatus;
  readonly segments: number;
  readonly adopted: number;
}
export interface DraftPreparation {
  readonly profileId: string;
  readonly instruction: string;
  readonly maxSegments: number;
  readonly maxOutputCharacters: number;
  readonly writingJobId?: string;
}

export class ChapterDraftError extends Error {
  public readonly code: string;
  public constructor(message: string, code = "NETWORK") {
    super(message);
    this.name = "ChapterDraftError";
    this.code = code;
  }
}

function invalid(): never {
  throw new ChapterDraftError(
    "章节候选稿数据无法安全读取，请刷新。",
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
function int(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    invalid();
  return value;
}
function bool(value: unknown): boolean {
  if (typeof value !== "boolean") invalid();
  return value;
}
function list<T>(value: unknown, decode: (v: unknown) => T): T[] {
  if (!Array.isArray(value)) invalid();
  return value.map(decode);
}
function nullable<T>(value: unknown, decode: (v: unknown) => T): T | null {
  return value === null || value === undefined ? null : decode(value);
}
function oneOf<T extends string>(options: readonly T[]) {
  return (value: unknown): T => {
    const result = str(value);
    if (!options.includes(result as T)) invalid();
    return result as T;
  };
}
const status = oneOf<DraftStatus>(["ready", "running", "failed", "exhausted"]);
const segmentStatus = oneOf<SegmentStatus>(["pending", "adopted"]);
const kind = oneOf<"local" | "cloud">(["local", "cloud"]);

export function parseDraft(value: unknown, chapterId: string): ChapterDraft {
  const item = obj(value);
  if (item.chapter_id !== chapterId) invalid();
  const model = obj(item.model);
  const segments = list(item.segments, (raw): DraftSegment => {
    const segment = obj(raw);
    return {
      index: int(segment.index),
      attempt: int(segment.attempt),
      text: str(segment.text),
      characters: int(segment.characters),
      model: str(segment.model),
      status: segmentStatus(segment.status),
      adopted_revision_id: nullable(segment.adopted_revision_id, id),
    };
  });
  // Segment indexes are positions; anything else could adopt the wrong text.
  if (segments.some((segment, index) => segment.index !== index)) invalid();
  return {
    id: id(item.id),
    chapter_id: id(item.chapter_id),
    version: int(item.version),
    status: status(item.status),
    model_name: str(model.name),
    model_kind: kind(model.kind),
    instruction: str(item.instruction),
    max_segments: int(item.max_segments),
    max_output_characters: int(item.max_output_characters),
    attempts: int(item.attempts),
    generated_characters: int(item.generated_characters),
    remaining_requests: int(item.remaining_requests),
    remaining_characters: int(item.remaining_characters),
    can_send: bool(item.can_send),
    base_revision_id: id(item.base_revision_id),
    current_revision_id: id(item.current_revision_id),
    included_sources: list(item.included_sources, str),
    omitted_sources: list(item.omitted_sources, str),
    segments,
    failures: list(item.failures, (raw): DraftFailure => {
      const failure = obj(raw);
      return {
        attempt: int(failure.attempt),
        error: str(failure.error),
        evidence: nullable(failure.evidence, str),
        evidence_truncated: bool(failure.evidence_truncated),
      };
    }),
    receipts: list(item.receipts, (raw): DraftReceipt => {
      const receipt = obj(raw);
      return {
        idempotency_key: str(receipt.idempotency_key),
        segment_indexes: list(receipt.segment_indexes, int),
        revision_id: id(receipt.revision_id),
      };
    }),
    last_error: nullable(item.last_error, str),
    writing_job_id: nullable(item.writing_job_id, id),
    next_request_preview: str(item.next_request_preview),
  };
}

const MESSAGES: Record<string, string> = {
  AI_WORKFLOW_SCHEMA_REQUIRED:
    "需要先“备份并启用 AI 协作”（数据库升级）后才能使用章节候选稿；写作不受影响。",
  AI_SERVICE_UNAVAILABLE: "章节候选稿暂不可用；写作不受影响。",
  CHAPTER_DRAFT_STALE:
    "正文在候选稿基线之后被修改过。为避免覆盖手改内容，本次没有写入也没有发送；候选稿已保留供比较，可重新准备。",
  CHAPTER_DRAFT_CONFLICT:
    "候选稿状态已变化（可能已在其他窗口发送或已用完额度），请刷新后再操作。",
  CHAPTER_DRAFT_QUOTA_EXHAUSTED: "本候选稿的请求次数或字数额度已用完。",
  CHAPTER_DRAFT_INVALID:
    "请求无效（额度超出上限、所选段落不存在或已采用），或本章候选稿记录已达上限。",
  CHAPTER_DRAFT_NOT_FOUND: "该候选稿已不存在，请刷新。",
  CHAPTER_DRAFT_CONSENT_REQUIRED:
    "这是云端模型：请先勾选同意发送本章上下文与候选稿。",
  AI_WORKFLOW_CONFLICT:
    "跨章任务额度已用完或任务状态不允许发送；没有发出请求。",
  AI_CONTEXT_CHANGED: "准备期间正文发生变化，请保存后重新准备。",
  AI_BUDGET_REFUSED:
    "按你设定的严格预算，本次没有发送，也没有记录用量。可调整预算后重新预估。",
  MODEL_PROFILE_NOT_FOUND: "该模型配置已不存在，请重新选择模型。",
};

export function chapterDraftError(error: unknown): ChapterDraftError {
  if (error instanceof ChapterDraftError) return error;
  if (error instanceof ApiError) {
    if (error.status === 401) securitySession.clear();
    return new ChapterDraftError(
      MESSAGES[error.code] ??
        (error.status >= 500
          ? "模型服务暂不可用，本段已记为失败并停止；正文未改变，可在额度内手动重试。"
          : "候选稿请求失败；正文未改变。"),
      error.code,
    );
  }
  return new ChapterDraftError(
    "连接中断，候选稿操作未完成；正文未改变，可刷新查看结果。",
  );
}

async function request<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw chapterDraftError(error);
  }
}
async function csrf(): Promise<{ headers: Record<string, string> }> {
  const session = await securitySession.getValidSession();
  return { headers: { "X-CSRF-Token": session.csrfToken } };
}
function base(chapterId: string): string {
  return `chapters/${id(chapterId)}/ai/drafts`;
}

export const chapterDraftClient = {
  list: (chapterId: string) =>
    request(() =>
      getJson(base(chapterId), (value) =>
        list(obj(value).items, (raw): DraftSummary => {
          const item = obj(raw);
          return {
            id: id(item.id),
            status: status(item.status),
            segments: int(item.segments),
            adopted: int(item.adopted),
          };
        }),
      ),
    ),
  get: (chapterId: string, draftId: string) =>
    request(() =>
      getJson(`${base(chapterId)}/${id(draftId)}`, (value) =>
        parseDraft(value, chapterId),
      ),
    ),
  prepare: (chapterId: string, input: DraftPreparation) =>
    request(async () =>
      postJson(
        base(chapterId),
        {
          profile_id: id(input.profileId),
          instruction: input.instruction,
          max_segments: input.maxSegments,
          max_output_characters: input.maxOutputCharacters,
          ...(input.writingJobId ? { writing_job_id: input.writingJobId } : {}),
        },
        (value) => parseDraft(value, chapterId),
        await csrf(),
      ),
    ),
  estimate: (chapterId: string, draftId: string): Promise<SendEstimate> =>
    request(() =>
      getJson(`${base(chapterId)}/${id(draftId)}/estimate`, parseEstimate),
    ),
  send: (
    chapterId: string,
    draft: ChapterDraft,
    segments: number,
    cloudConsent: boolean,
  ) =>
    request(async () =>
      postJson(
        `${base(chapterId)}/${id(draft.id)}/send`,
        {
          expected_version: draft.version,
          cloud_consent: cloudConsent,
          segments,
        },
        (value) => parseDraft(value, chapterId),
        await csrf(),
      ),
    ),
  adopt: (
    chapterId: string,
    draftId: string,
    idempotencyKey: string,
    segmentIndexes: readonly number[] | null,
  ) =>
    request(async () =>
      postJson(
        `${base(chapterId)}/${id(draftId)}/adopt`,
        segmentIndexes === null
          ? { idempotency_key: idempotencyKey }
          : {
              idempotency_key: idempotencyKey,
              segment_indexes: [...segmentIndexes],
            },
        (value) => parseDraft(value, chapterId),
        await csrf(),
      ),
    ),
};
export type ChapterDraftClient = typeof chapterDraftClient;
