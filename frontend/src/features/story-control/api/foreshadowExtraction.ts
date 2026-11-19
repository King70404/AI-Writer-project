import { getJson, postJson, putJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";
import { parseEstimate, type SendEstimate } from "../../usage/api/budget";

/**
 * 批量提取伏笔建议（F03 / C-2）。作者选定有限的章节范围（最多 10 章、正文合计不超过上限），
 * 预览与准备只读取已保存正文并冻结，不调用模型；确认预估后整段只发送一次。
 * 每张建议卡的引文都会在冻结正文中逐字核对，找不到的卡不能采用；
 * 只有作者勾选采用的有效卡才会写入伏笔。作者可以先修改建议卡再采用（原始建议与核对结果保留以便对照，
 * 修改后的引文同样逐字核对），也可以撤销已采用的卡；伏笔之后被改过时服务端会拒绝撤销。
 */
export type ExtractionStatus = "ready" | "running" | "completed" | "failed";
export type CardProblem =
  | "quote_not_found"
  | "unknown_chapter"
  | "unknown_thread"
  | "duplicate_payoff"
  | "duplicate_title";
export type RangeProblem =
  "too_many_chapters" | "too_many_characters" | "empty_chapter";

export interface NewThreadCard {
  readonly kind: "new_thread";
  readonly title: string;
  readonly content: string;
  readonly chapter_id: string;
  readonly quote: string;
  readonly reason: string;
}
export interface PayoffCard {
  readonly kind: "payoff";
  readonly thread_id: string;
  readonly chapter_id: string;
  readonly quote: string;
  readonly reason: string;
}
export type ForeshadowCard = NewThreadCard | PayoffCard;
export interface CardCheck {
  readonly valid: boolean;
  readonly problem: CardProblem | null;
}
export interface ForeshadowAdoption {
  readonly index: number;
  readonly action: "created" | "paid_off" | "already_recorded";
  readonly thread_id: string;
  readonly edited: boolean;
}
export interface ForeshadowCardEdit {
  readonly index: number;
  readonly card: ForeshadowCard;
}
export interface ForeshadowUndo {
  readonly index: number;
  readonly action: ForeshadowAdoption["action"];
}
export interface FrozenChapter {
  readonly chapter_id: string;
  readonly title: string;
  readonly volume_position: number;
  readonly position: number;
  readonly characters: number;
}
export interface FrozenThread {
  readonly id: string;
  readonly title: string;
}
export interface ForeshadowExtraction {
  readonly id: string;
  readonly version: number;
  readonly status: ExtractionStatus;
  readonly model_name: string;
  readonly model_kind: "local" | "cloud";
  readonly author_request: string;
  readonly chapters: readonly FrozenChapter[];
  readonly total_characters: number;
  readonly threads: readonly FrozenThread[];
  readonly threads_omitted: number;
  readonly summary: string | null;
  readonly cards: readonly ForeshadowCard[];
  readonly checks: readonly CardCheck[];
  /** 按作者修改后的卡重新核对的结果；采用以它为准。 */
  readonly effective_checks: readonly CardCheck[];
  readonly edits: readonly ForeshadowCardEdit[];
  readonly undos: readonly ForeshadowUndo[];
  readonly error: string | null;
  readonly evidence: string | null;
  readonly evidence_truncated: boolean;
  readonly adoptions: readonly ForeshadowAdoption[];
  readonly request_preview: string;
}
/** 采用时实际使用的卡：有作者修改时用修改版，否则用模型原始建议。 */
export function effectiveCard(
  extraction: ForeshadowExtraction,
  index: number,
): ForeshadowCard {
  return (
    extraction.edits.find((item) => item.index === index)?.card ??
    extraction.cards[index]
  );
}

export interface ExtractionSummary {
  readonly id: string;
  readonly status: ExtractionStatus;
  readonly chapter_ids: readonly string[];
}
export interface RangePreview {
  readonly chapters: readonly FrozenChapter[];
  readonly total_characters: number;
  readonly max_chapters: number;
  readonly max_total_characters: number;
  readonly open_threads: number;
  readonly threads_omitted: number;
  readonly problem: RangeProblem | null;
}
export interface ExtractionModel {
  readonly id: string;
  readonly name: string;
  readonly kind: "local" | "cloud";
}

export class ForeshadowExtractionError extends Error {
  public readonly code: string;
  public constructor(message: string, code = "NETWORK") {
    super(message);
    this.name = "ForeshadowExtractionError";
    this.code = code;
  }
}

function invalid(): never {
  throw new ForeshadowExtractionError(
    "伏笔提取数据无法安全读取，请刷新。",
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
const status = oneOf<ExtractionStatus>([
  "ready",
  "running",
  "completed",
  "failed",
]);
const kind = oneOf<"local" | "cloud">(["local", "cloud"]);
const action = oneOf<ForeshadowAdoption["action"]>([
  "created",
  "paid_off",
  "already_recorded",
]);
const cardProblem = oneOf<CardProblem>([
  "quote_not_found",
  "unknown_chapter",
  "unknown_thread",
  "duplicate_payoff",
  "duplicate_title",
]);
const rangeProblem = oneOf<RangeProblem>([
  "too_many_chapters",
  "too_many_characters",
  "empty_chapter",
]);

function chapter(value: unknown): FrozenChapter {
  const item = obj(value);
  return {
    chapter_id: id(item.chapter_id),
    title: str(item.title),
    volume_position: int(item.volume_position),
    position: int(item.position),
    characters: int(item.characters),
  };
}
function cardCheck(value: unknown): CardCheck {
  const check = obj(value);
  return {
    valid: bool(check.valid),
    problem: nullable(check.problem, cardProblem),
  };
}
function card(value: unknown): ForeshadowCard {
  const item = obj(value);
  if (item.kind === "new_thread")
    return {
      kind: "new_thread",
      title: str(item.title),
      content: str(item.content),
      chapter_id: id(item.chapter_id),
      quote: str(item.quote),
      reason: str(item.reason),
    };
  if (item.kind === "payoff")
    return {
      kind: "payoff",
      thread_id: id(item.thread_id),
      chapter_id: id(item.chapter_id),
      quote: str(item.quote),
      reason: str(item.reason),
    };
  return invalid();
}

export function parseExtraction(
  value: unknown,
  projectId: string,
): ForeshadowExtraction {
  const item = obj(value);
  if (item.project_id !== projectId) invalid();
  const model = obj(item.model);
  const cards = list(item.cards, card);
  const checks = list(item.checks, cardCheck);
  const effectiveChecks = list(item.effective_checks, cardCheck);
  // A card without its server check is never treated as adoptable.
  if (checks.length !== cards.length || effectiveChecks.length !== cards.length)
    invalid();
  return {
    id: id(item.id),
    version: int(item.version),
    status: status(item.status),
    model_name: str(model.name),
    model_kind: kind(model.kind),
    author_request: str(item.author_request),
    chapters: list(item.chapters, chapter),
    total_characters: int(item.total_characters),
    threads: list(item.threads, (raw) => {
      const thread = obj(raw);
      return { id: id(thread.id), title: str(thread.title) };
    }),
    threads_omitted: int(item.threads_omitted),
    summary: nullable(item.summary, str),
    cards,
    checks,
    effective_checks: effectiveChecks,
    edits: list(item.edits, (raw) => {
      const edit = obj(raw);
      return { index: int(edit.index), card: card(edit.card) };
    }),
    undos: list(item.undos, (raw) => {
      const undo = obj(raw);
      return { index: int(undo.index), action: action(undo.action) };
    }),
    error: nullable(item.error, str),
    evidence: nullable(item.evidence, str),
    evidence_truncated: bool(item.evidence_truncated),
    adoptions: list(item.adoptions, (raw) => {
      const adoption = obj(raw);
      return {
        index: int(adoption.index),
        action: action(adoption.action),
        thread_id: id(adoption.thread_id),
        edited: bool(adoption.edited),
      };
    }),
    request_preview: str(item.request_preview),
  };
}

export function parseRangePreview(value: unknown): RangePreview {
  const item = obj(value);
  return {
    chapters: list(item.chapters, chapter),
    total_characters: int(item.total_characters),
    max_chapters: int(item.max_chapters),
    max_total_characters: int(item.max_total_characters),
    open_threads: int(item.open_threads),
    threads_omitted: int(item.threads_omitted),
    problem: nullable(item.problem, rangeProblem),
  };
}

const MESSAGES: Record<string, string> = {
  AI_WORKFLOW_SCHEMA_REQUIRED:
    "需要先“备份并启用 AI 协作”（数据库升级）后才能批量提取伏笔；写作不受影响。",
  STORY_CONTROL_UNAVAILABLE: "批量提取伏笔暂不可用；写作不受影响。",
  FORESHADOW_EXTRACTION_STALE:
    "准备后章节正文或伏笔已被修改，为避免引用失效的原文，本次没有采用。请重新准备。",
  FORESHADOW_EXTRACTION_CONFLICT:
    "提取状态已变化（可能已在其他窗口发送或失败），请刷新后再操作。",
  FORESHADOW_EXTRACTION_INVALID:
    "所选范围无效（超过章节或字数上限、含空章或章节已不存在），或建议记录已达上限。",
  FORESHADOW_CARD_INVALID:
    "卡片无效：引文必须逐字出自所选章节的冻结原文，伏笔名不能与已有伏笔重复，且不能改变卡片类型。",
  FORESHADOW_UNDO_CONFLICT:
    "这张卡写入的伏笔之后已被修改，为避免覆盖你的改动，没有撤销。请在伏笔里手动调整。",
  FORESHADOW_EXTRACTION_NOT_FOUND: "该提取记录已不存在，请刷新。",
  FORESHADOW_EXTRACTION_CONSENT_REQUIRED:
    "这是云端模型：请先勾选同意发送所选章节的正文。",
  STORY_CONTROL_INVALID:
    "采用失败：伏笔数量已达上限或引用的章节已不存在。伏笔未改变。",
  AI_BUDGET_REFUSED:
    "按你设定的严格预算，本次没有发送，也没有记录用量。可调整预算后重新预估。",
  MODEL_PROFILE_NOT_FOUND: "该模型配置已不存在，请重新选择模型。",
  PROJECT_NOT_FOUND: "这本小说已不存在或已删除。",
};

export function foreshadowExtractionError(
  error: unknown,
): ForeshadowExtractionError {
  if (error instanceof ForeshadowExtractionError) return error;
  if (error instanceof ApiError) {
    if (error.status === 401) securitySession.clear();
    return new ForeshadowExtractionError(
      MESSAGES[error.code] ??
        (error.status >= 500
          ? "模型服务暂不可用，本次提取已记为失败；伏笔未改变。"
          : "伏笔提取请求失败，请稍后重试；伏笔未改变。"),
      error.code,
    );
  }
  return new ForeshadowExtractionError(
    "连接中断，伏笔提取未完成；伏笔未改变，可刷新查看结果。",
  );
}

async function request<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw foreshadowExtractionError(error);
  }
}
async function csrf(): Promise<{ headers: Record<string, string> }> {
  const session = await securitySession.getValidSession();
  return { headers: { "X-CSRF-Token": session.csrfToken } };
}
function base(projectId: string): string {
  return `projects/${id(projectId)}/foreshadow-proposals`;
}

export const foreshadowExtractionClient = {
  models: () =>
    request(() =>
      getJson("ai/models", (value) => {
        const item = obj(value);
        return list(item.items, (raw) => {
          const profile = obj(raw);
          return {
            id: id(profile.id),
            name: str(profile.name),
            kind: kind(profile.kind),
          };
        });
      }),
    ),
  list: (projectId: string) =>
    request(() =>
      getJson(base(projectId), (value) =>
        list(obj(value).items, (raw): ExtractionSummary => {
          const item = obj(raw);
          return {
            id: id(item.id),
            status: status(item.status),
            chapter_ids: list(item.chapter_ids, id),
          };
        }),
      ),
    ),
  get: (projectId: string, extractionId: string) =>
    request(() =>
      getJson(`${base(projectId)}/${id(extractionId)}`, (value) =>
        parseExtraction(value, projectId),
      ),
    ),
  preview: (projectId: string, chapterIds: readonly string[]) =>
    request(async () =>
      postJson(
        `${base(projectId)}/preview`,
        { chapter_ids: chapterIds.map(id) },
        parseRangePreview,
        await csrf(),
      ),
    ),
  prepare: (
    projectId: string,
    chapterIds: readonly string[],
    profileId: string,
    authorRequest: string,
  ) =>
    request(async () =>
      postJson(
        base(projectId),
        {
          chapter_ids: chapterIds.map(id),
          profile_id: profileId,
          author_request: authorRequest,
        },
        (value) => parseExtraction(value, projectId),
        await csrf(),
      ),
    ),
  estimate: (projectId: string, extractionId: string): Promise<SendEstimate> =>
    request(() =>
      getJson(`${base(projectId)}/${id(extractionId)}/estimate`, parseEstimate),
    ),
  send: (
    projectId: string,
    extraction: ForeshadowExtraction,
    cloudConsent: boolean,
  ) =>
    request(async () =>
      postJson(
        `${base(projectId)}/${id(extraction.id)}/send`,
        { expected_version: extraction.version, cloud_consent: cloudConsent },
        (value) => parseExtraction(value, projectId),
        await csrf(),
      ),
    ),
  adopt: (
    projectId: string,
    extractionId: string,
    indexes: readonly number[],
  ) =>
    request(async () =>
      postJson(
        `${base(projectId)}/${id(extractionId)}/adopt`,
        { card_indexes: indexes },
        (value) => parseExtraction(value, projectId),
        await csrf(),
      ),
    ),
  editCard: (
    projectId: string,
    extraction: ForeshadowExtraction,
    index: number,
    card: ForeshadowCard | null,
  ) =>
    request(async () =>
      putJson(
        `${base(projectId)}/${id(extraction.id)}/cards/${int(index)}`,
        { expected_version: extraction.version, card },
        (value) => parseExtraction(value, projectId),
        await csrf(),
      ),
    ),
  undo: (projectId: string, extraction: ForeshadowExtraction, index: number) =>
    request(async () =>
      postJson(
        `${base(projectId)}/${id(extraction.id)}/undo`,
        { expected_version: extraction.version, card_index: int(index) },
        (value) => parseExtraction(value, projectId),
        await csrf(),
      ),
    ),
};
export type ForeshadowExtractionClient = typeof foreshadowExtractionClient;
