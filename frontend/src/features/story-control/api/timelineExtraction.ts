import { getJson, postJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";
import { parseEstimate, type SendEstimate } from "../../usage/api/budget";
import type { StateAttribute } from "./storyControl";

/**
 * 批量提取故事事件与人物状态（F03，与 C-2 批量提取伏笔同类）。作者选定有限的章节范围，
 * 预览与准备只读取已保存正文并冻结（连同人物、已有事件和仍有效的人物状态），不调用模型；
 * 确认预估后整段只发送一次。每张证据卡的引文都会在冻结正文中逐字核对，
 * 找不到的卡不能采用；只有作者勾选采用的有效卡才会写入时间线。
 */
export type ExtractionStatus = "ready" | "running" | "completed" | "failed";
export type TimelineCardProblem =
  | "quote_not_found"
  | "unknown_chapter"
  | "unknown_character"
  | "unknown_event"
  | "unknown_state"
  | "unknown_event_card"
  | "duplicate_title"
  | "duplicate_end"
  | "state_mismatch";
export type RangeProblem =
  "too_many_chapters" | "too_many_characters" | "empty_chapter";

export interface EventCard {
  readonly kind: "event";
  readonly title: string;
  readonly description: string;
  readonly story_time: string;
  readonly chapter_id: string;
  readonly character_ids: readonly string[];
  readonly after_event_ids: readonly string[];
  readonly quote: string;
  readonly reason: string;
}
export interface StateCard {
  readonly kind: "state";
  readonly character_id: string;
  readonly attribute: StateAttribute;
  readonly label: string;
  readonly value: string;
  readonly chapter_id: string;
  readonly quote: string;
  readonly start_event_id: string | null;
  readonly start_event_card: number | null;
  readonly ends_state_id: string | null;
  readonly reason: string;
}
export type TimelineCard = EventCard | StateCard;
export interface TimelineCardCheck {
  readonly valid: boolean;
  readonly problem: TimelineCardProblem | null;
}
export interface TimelineAdoption {
  readonly index: number;
  readonly action: "event_created" | "state_created";
  readonly target_id: string;
  readonly ended_state_id: string | null;
}
export interface FrozenChapter {
  readonly chapter_id: string;
  readonly title: string;
  readonly volume_position: number;
  readonly position: number;
  readonly characters: number;
}
export interface FrozenCharacter {
  readonly character_id: string;
  readonly name: string;
}
export interface FrozenEvent {
  readonly id: string;
  readonly title: string;
}
export interface FrozenState {
  readonly id: string;
  readonly character_id: string;
  readonly label: string;
  readonly value: string;
}
export interface TimelineExtraction {
  readonly id: string;
  readonly version: number;
  readonly status: ExtractionStatus;
  readonly model_name: string;
  readonly model_kind: "local" | "cloud";
  readonly author_request: string;
  readonly chapters: readonly FrozenChapter[];
  readonly total_characters: number;
  readonly characters: readonly FrozenCharacter[];
  readonly events: readonly FrozenEvent[];
  readonly events_omitted: number;
  readonly states: readonly FrozenState[];
  readonly states_omitted: number;
  readonly summary: string | null;
  readonly cards: readonly TimelineCard[];
  readonly checks: readonly TimelineCardCheck[];
  readonly error: string | null;
  readonly evidence: string | null;
  readonly evidence_truncated: boolean;
  readonly adoptions: readonly TimelineAdoption[];
  readonly request_preview: string;
}
export interface TimelineExtractionSummary {
  readonly id: string;
  readonly status: ExtractionStatus;
  readonly chapter_ids: readonly string[];
}
export interface TimelineRangePreview {
  readonly chapters: readonly FrozenChapter[];
  readonly total_characters: number;
  readonly max_chapters: number;
  readonly max_total_characters: number;
  readonly characters: number;
  readonly events: number;
  readonly events_omitted: number;
  readonly open_states: number;
  readonly states_omitted: number;
  readonly problem: RangeProblem | null;
}
export interface ExtractionModel {
  readonly id: string;
  readonly name: string;
  readonly kind: "local" | "cloud";
}

export class TimelineExtractionError extends Error {
  public readonly code: string;
  public constructor(message: string, code = "NETWORK") {
    super(message);
    this.name = "TimelineExtractionError";
    this.code = code;
  }
}

function invalid(): never {
  throw new TimelineExtractionError(
    "事件与人物状态提取数据无法安全读取，请刷新。",
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
const action = oneOf<TimelineAdoption["action"]>([
  "event_created",
  "state_created",
]);
const attribute = oneOf<StateAttribute>([
  "identity",
  "injury",
  "possession",
  "knowledge",
  "other",
]);
const cardProblem = oneOf<TimelineCardProblem>([
  "quote_not_found",
  "unknown_chapter",
  "unknown_character",
  "unknown_event",
  "unknown_state",
  "unknown_event_card",
  "duplicate_title",
  "duplicate_end",
  "state_mismatch",
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
function card(value: unknown): TimelineCard {
  const item = obj(value);
  if (item.kind === "event")
    return {
      kind: "event",
      title: str(item.title),
      description: str(item.description),
      story_time: str(item.story_time),
      chapter_id: id(item.chapter_id),
      character_ids: list(item.character_ids, id),
      after_event_ids: list(item.after_event_ids, id),
      quote: str(item.quote),
      reason: str(item.reason),
    };
  if (item.kind === "state") {
    const start = nullable(item.start_event_id, id);
    const startCard = nullable(item.start_event_card, int);
    // A state starts at exactly one event or event card; anything else is unsafe.
    if ((start === null) === (startCard === null)) invalid();
    return {
      kind: "state",
      character_id: id(item.character_id),
      attribute: attribute(item.attribute),
      label: str(item.label),
      value: str(item.value),
      chapter_id: id(item.chapter_id),
      quote: str(item.quote),
      start_event_id: start,
      start_event_card: startCard,
      ends_state_id: nullable(item.ends_state_id, id),
      reason: str(item.reason),
    };
  }
  return invalid();
}

export function parseTimelineExtraction(
  value: unknown,
  projectId: string,
): TimelineExtraction {
  const item = obj(value);
  if (item.project_id !== projectId) invalid();
  const model = obj(item.model);
  const cards = list(item.cards, card);
  const checks = list(item.checks, (raw) => {
    const check = obj(raw);
    return {
      valid: bool(check.valid),
      problem: nullable(check.problem, cardProblem),
    };
  });
  // A card without its server check is never treated as adoptable.
  if (checks.length !== cards.length) invalid();
  return {
    id: id(item.id),
    version: int(item.version),
    status: status(item.status),
    model_name: str(model.name),
    model_kind: kind(model.kind),
    author_request: str(item.author_request),
    chapters: list(item.chapters, chapter),
    total_characters: int(item.total_characters),
    characters: list(item.characters, (raw) => {
      const entry = obj(raw);
      return { character_id: id(entry.character_id), name: str(entry.name) };
    }),
    events: list(item.events, (raw) => {
      const entry = obj(raw);
      return { id: id(entry.id), title: str(entry.title) };
    }),
    events_omitted: int(item.events_omitted),
    states: list(item.states, (raw) => {
      const entry = obj(raw);
      return {
        id: id(entry.id),
        character_id: id(entry.character_id),
        label: str(entry.label),
        value: str(entry.value),
      };
    }),
    states_omitted: int(item.states_omitted),
    summary: nullable(item.summary, str),
    cards,
    checks,
    error: nullable(item.error, str),
    evidence: nullable(item.evidence, str),
    evidence_truncated: bool(item.evidence_truncated),
    adoptions: list(item.adoptions, (raw) => {
      const adoption = obj(raw);
      return {
        index: int(adoption.index),
        action: action(adoption.action),
        target_id: id(adoption.target_id),
        ended_state_id: nullable(adoption.ended_state_id, id),
      };
    }),
    request_preview: str(item.request_preview),
  };
}

export function parseTimelineRangePreview(
  value: unknown,
): TimelineRangePreview {
  const item = obj(value);
  return {
    chapters: list(item.chapters, chapter),
    total_characters: int(item.total_characters),
    max_chapters: int(item.max_chapters),
    max_total_characters: int(item.max_total_characters),
    characters: int(item.characters),
    events: int(item.events),
    events_omitted: int(item.events_omitted),
    open_states: int(item.open_states),
    states_omitted: int(item.states_omitted),
    problem: nullable(item.problem, rangeProblem),
  };
}

const MESSAGES: Record<string, string> = {
  AI_WORKFLOW_SCHEMA_REQUIRED:
    "需要先“备份并启用 AI 协作”（数据库升级）后才能批量提取事件与人物状态；写作不受影响。",
  STORY_CONTROL_UNAVAILABLE: "批量提取事件与人物状态暂不可用；写作不受影响。",
  TIMELINE_EXTRACTION_STALE:
    "准备后章节正文、引用的事件或要结束的人物状态已被修改，为避免引用失效的原文，本次没有采用。请重新准备。",
  TIMELINE_EXTRACTION_CONFLICT:
    "提取状态已变化（可能已在其他窗口发送或失败），请刷新后再操作。",
  TIMELINE_EXTRACTION_INVALID:
    "所选范围无效（超过章节或字数上限、含空章或章节已不存在），或提取记录已达上限。",
  TIMELINE_CARD_INVALID: "所选卡片的引文或引用没有通过核对，不能采用。",
  TIMELINE_CARD_NEEDS_EVENT:
    "所选人物状态从一张建议事件开始，请同时勾选那张事件卡（或先采用它）。",
  TIMELINE_EXTRACTION_NOT_FOUND: "该提取记录已不存在，请刷新。",
  TIMELINE_EXTRACTION_CONSENT_REQUIRED:
    "这是云端模型：请先勾选同意发送所选章节的正文。",
  STORY_CONTROL_INVALID:
    "采用失败：事件或人物状态数量已达上限，或引用的章节、人物、事件已不存在或先后矛盾。",
  STORY_CONTROL_CYCLE: "采用失败：事件先后关系会形成循环。",
  AI_BUDGET_REFUSED:
    "按你设定的严格预算，本次没有发送，也没有记录用量。可调整预算后重新预估。",
  MODEL_PROFILE_NOT_FOUND: "该模型配置已不存在，请重新选择模型。",
  PROJECT_NOT_FOUND: "这本小说已不存在或已删除。",
};

export function timelineExtractionError(
  error: unknown,
): TimelineExtractionError {
  if (error instanceof TimelineExtractionError) return error;
  if (error instanceof ApiError) {
    if (error.status === 401) securitySession.clear();
    return new TimelineExtractionError(
      MESSAGES[error.code] ??
        (error.status >= 500
          ? "模型服务暂不可用，本次提取已记为失败；时间线未改变。"
          : "事件与人物状态提取请求失败，请稍后重试；时间线未改变。"),
      error.code,
    );
  }
  return new TimelineExtractionError(
    "连接中断，提取未完成；时间线未改变，可刷新查看结果。",
  );
}

async function request<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw timelineExtractionError(error);
  }
}
async function csrf(): Promise<{ headers: Record<string, string> }> {
  const session = await securitySession.getValidSession();
  return { headers: { "X-CSRF-Token": session.csrfToken } };
}
function base(projectId: string): string {
  return `projects/${id(projectId)}/timeline-proposals`;
}

export const timelineExtractionClient = {
  models: () =>
    request(() =>
      getJson("ai/models", (value) => {
        const item = obj(value);
        return list(item.items, (raw): ExtractionModel => {
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
        list(obj(value).items, (raw): TimelineExtractionSummary => {
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
        parseTimelineExtraction(value, projectId),
      ),
    ),
  preview: (projectId: string, chapterIds: readonly string[]) =>
    request(async () =>
      postJson(
        `${base(projectId)}/preview`,
        { chapter_ids: chapterIds.map(id) },
        parseTimelineRangePreview,
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
        (value) => parseTimelineExtraction(value, projectId),
        await csrf(),
      ),
    ),
  estimate: (projectId: string, extractionId: string): Promise<SendEstimate> =>
    request(() =>
      getJson(`${base(projectId)}/${id(extractionId)}/estimate`, parseEstimate),
    ),
  send: (
    projectId: string,
    extraction: TimelineExtraction,
    cloudConsent: boolean,
  ) =>
    request(async () =>
      postJson(
        `${base(projectId)}/${id(extraction.id)}/send`,
        { expected_version: extraction.version, cloud_consent: cloudConsent },
        (value) => parseTimelineExtraction(value, projectId),
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
        (value) => parseTimelineExtraction(value, projectId),
        await csrf(),
      ),
    ),
};
export type TimelineExtractionClient = typeof timelineExtractionClient;
