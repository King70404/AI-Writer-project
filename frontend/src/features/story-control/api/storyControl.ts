import { getJson, postJson, putJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";

/**
 * 长篇故事控制（交付包 C）：全书/分卷目标、伏笔与故事时间线、可调召回。
 * 全部由作者录入或选择；查看、筛选与预览都不调用模型。
 * 计划与伏笔是写作指导，不是已发生的正文事实。
 */
export type GoalScope = "book" | "volume";
export type LinkStatus = "planned" | "reflected" | "deferred" | "abandoned";
export type ThreadStatus =
  "planned" | "planted" | "advancing" | "paid_off" | "abandoned";
export type ThreadPriority = "high" | "normal" | "low";
export type AnchorRole = "setup" | "advance" | "payoff";
export type StateAttribute =
  "identity" | "injury" | "possession" | "knowledge" | "other";
export type OmitReason =
  | "excluded"
  | "budget"
  | "pin_not_confirmed"
  | "pin_stale"
  | "pin_not_earlier"
  | "pin_missing"
  | "pin_over_budget";

export const LINK_LABELS: Record<LinkStatus, string> = {
  planned: "计划",
  reflected: "已体现",
  deferred: "延后",
  abandoned: "放弃",
};
export const THREAD_LABELS: Record<ThreadStatus, string> = {
  planned: "计划",
  planted: "已埋设",
  advancing: "推进中",
  paid_off: "已兑现",
  abandoned: "已放弃",
};
export const PRIORITY_LABELS: Record<ThreadPriority, string> = {
  high: "高",
  normal: "中",
  low: "低",
};
export const ATTRIBUTE_LABELS: Record<StateAttribute, string> = {
  identity: "身份",
  injury: "伤势",
  possession: "持有物",
  knowledge: "知情范围",
  other: "其他",
};
export const OMIT_LABELS: Record<OmitReason, string> = {
  excluded: "作者排除",
  budget: "超出召回预算（24 项 / 10,000 字符）",
  pin_not_confirmed: "固定项未确认或已驳回",
  pin_stale: "固定项来源正文已修改，需重新确认",
  pin_not_earlier: "固定项不在本章之前",
  pin_missing: "固定项已不存在",
  pin_over_budget: "固定项超出召回预算，请减少固定项",
};

export interface GoalLink {
  readonly chapter_id: string;
  readonly status: LinkStatus;
  readonly chapter_revision_id: string | null;
  readonly quote: string | null;
  readonly note: string;
}
export interface GoalDocument {
  readonly scope: GoalScope;
  readonly volume_id: string | null;
  readonly parent_goal_ids: readonly string[];
  readonly title: string;
  readonly conflict: string;
  readonly desire: string;
  readonly obstacle: string;
  readonly turn: string;
  readonly outcome: string;
  readonly opening_state: string;
  readonly target_characters: number | null;
  readonly status: "active" | "archived";
  readonly links: readonly GoalLink[];
}
export interface Stored {
  readonly id: string;
  readonly version: number;
  readonly revision_id: string;
  readonly updated_at: string;
}
export type Goal = GoalDocument & Stored;
export interface LinkView extends GoalLink {
  readonly chapter_title: string | null;
  readonly problem: "missing" | "evidence_stale" | null;
}
export interface GoalView {
  readonly goal: Goal;
  readonly links: readonly LinkView[];
  readonly child_goal_ids: readonly string[];
  readonly reflected: number;
  readonly open_links: number;
}
export interface ChapterOption {
  readonly chapter_id: string;
  readonly volume_id: string;
  readonly title: string;
  readonly volume_position: number;
  readonly position: number;
  readonly revision_id: string;
}
export interface ArcPlan {
  readonly project_id: string;
  readonly goals: readonly GoalView[];
  readonly volumes: readonly {
    readonly volume_id: string;
    readonly title: string;
    readonly position: number;
  }[];
  readonly chapters: readonly ChapterOption[];
  readonly characters: readonly {
    readonly character_id: string;
    readonly name: string;
  }[];
}
export interface EvidenceAnchor {
  readonly role: AnchorRole;
  readonly chapter_id: string;
  readonly chapter_revision_id: string;
  readonly quote: string;
}
export interface ThreadDocument {
  readonly title: string;
  readonly content: string;
  readonly character_ids: readonly string[];
  readonly planned_setup_chapter_id: string | null;
  readonly planned_payoff_chapter_id: string | null;
  readonly planned_payoff_volume_id: string | null;
  readonly priority: ThreadPriority;
  readonly status: ThreadStatus;
  readonly note: string;
  readonly anchors: readonly EvidenceAnchor[];
}
export type Thread = ThreadDocument & Stored;
export interface ThreadView {
  readonly thread: Thread;
  readonly anchors: readonly {
    readonly anchor: EvidenceAnchor;
    readonly chapter_title: string | null;
    readonly stale: boolean;
  }[];
  readonly evidence_stale: boolean;
  readonly due: boolean;
  readonly due_reason: string | null;
}
export interface EventDocument {
  readonly title: string;
  readonly description: string;
  readonly story_time: string;
  readonly chapter_id: string | null;
  readonly character_ids: readonly string[];
  readonly after_event_ids: readonly string[];
  readonly before_event_ids: readonly string[];
  readonly archived: boolean;
}
export type StoryEvent = EventDocument & Stored;
export interface EventView {
  readonly event: StoryEvent;
  readonly story_order: number;
  readonly narrative_position: readonly number[] | null;
  readonly chapter_title: string | null;
}
export interface StateDocument {
  readonly character_id: string;
  readonly attribute: StateAttribute;
  readonly label: string;
  readonly value: string;
  readonly start_event_id: string;
  readonly end_event_id: string | null;
  readonly fact_ids: readonly string[];
  readonly archived: boolean;
}
export type CharacterState = StateDocument & Stored;
export interface TimelineWarning {
  readonly kind: "state_overlap" | "state_order_unknown";
  readonly state_ids: readonly string[];
  readonly message: string;
}
export interface Timeline {
  readonly project_id: string;
  readonly threads: readonly ThreadView[];
  readonly events: readonly EventView[];
  readonly states: readonly {
    readonly state: CharacterState;
    readonly invalid_fact_ids: readonly string[];
  }[];
  readonly warnings: readonly TimelineWarning[];
}
export interface ChapterGuide {
  readonly chapter_id: string;
  readonly project_id: string;
  readonly goals: readonly GoalView[];
  readonly setup_threads: readonly ThreadView[];
  readonly payoff_threads: readonly ThreadView[];
  readonly due_threads: readonly ThreadView[];
}
export interface FactHit {
  readonly id: string;
  readonly revision_id: string;
  readonly chapter_id: string;
  readonly chapter_title: string | null;
  readonly title: string;
  readonly text: string;
  readonly quote: string;
  readonly status: "pending" | "confirmed" | "rejected";
  readonly stale: boolean;
  readonly recallable_here: boolean | null;
}
export interface FactSearchPage {
  readonly items: readonly FactHit[];
  readonly total: number;
  readonly offset: number;
  readonly limit: number;
}
export interface RecallPolicyState {
  readonly chapter_id: string;
  readonly version: number;
  readonly pinned_fact_ids: readonly string[];
  readonly excluded_fact_ids: readonly string[];
  readonly updated_at: string | null;
}
export interface RecallPreview {
  readonly chapter_id: string;
  readonly policy_version: number;
  readonly selected: readonly {
    readonly id: string;
    readonly revision_id: string;
    readonly chapter_id: string;
    readonly title: string;
    readonly reason: "pinned" | "related";
    readonly characters: number;
  }[];
  readonly omitted: readonly {
    readonly id: string;
    readonly title: string | null;
    readonly reason: OmitReason;
  }[];
  readonly omitted_total: number;
  readonly excluded_total: number;
  readonly used_characters: number;
  readonly character_limit: number;
  readonly item_limit: number;
  readonly blocked: boolean;
}

export class StoryControlError extends Error {
  public readonly code: string;
  public constructor(message: string, code = "NETWORK") {
    super(message);
    this.name = "StoryControlError";
    this.code = code;
  }
}

function invalid(): never {
  throw new StoryControlError(
    "故事规划数据无法安全读取，请刷新。",
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
  return value === null ? null : decode(value);
}
function oneOf<T extends string>(labels: Record<T, string>) {
  return (value: unknown): T => {
    const result = str(value);
    if (!Object.hasOwn(labels, result)) invalid();
    return result as T;
  };
}
const linkStatus = oneOf(LINK_LABELS);
const threadStatus = oneOf(THREAD_LABELS);
const priority = oneOf(PRIORITY_LABELS);
const attribute = oneOf(ATTRIBUTE_LABELS);
const omitReason = oneOf(OMIT_LABELS);
const anchorRole = oneOf<AnchorRole>({
  setup: "",
  advance: "",
  payoff: "",
});
const scope = oneOf<GoalScope>({ book: "", volume: "" });
const goalStatus = oneOf<"active" | "archived">({ active: "", archived: "" });
const recallReason = oneOf<"pinned" | "related">({ pinned: "", related: "" });
const factStatus = oneOf<FactHit["status"]>({
  pending: "",
  confirmed: "",
  rejected: "",
});
const problem = oneOf<"missing" | "evidence_stale">({
  missing: "",
  evidence_stale: "",
});
const warningKind = oneOf<TimelineWarning["kind"]>({
  state_overlap: "",
  state_order_unknown: "",
});

function stored(item: Record<string, unknown>): Stored {
  return {
    id: id(item.id),
    version: int(item.version),
    revision_id: id(item.revision_id),
    updated_at: str(item.updated_at),
  };
}
function link(value: unknown): GoalLink {
  const item = obj(value);
  return {
    chapter_id: id(item.chapter_id),
    status: linkStatus(item.status),
    chapter_revision_id: nullable(item.chapter_revision_id, id),
    quote: nullable(item.quote, str),
    note: str(item.note),
  };
}
export function parseGoal(value: unknown): Goal {
  const item = obj(value);
  return {
    ...stored(item),
    scope: scope(item.scope),
    volume_id: nullable(item.volume_id, id),
    parent_goal_ids: list(item.parent_goal_ids, id),
    title: str(item.title),
    conflict: str(item.conflict),
    desire: str(item.desire),
    obstacle: str(item.obstacle),
    turn: str(item.turn),
    outcome: str(item.outcome),
    opening_state: str(item.opening_state),
    target_characters: nullable(item.target_characters, int),
    status: goalStatus(item.status),
    links: list(item.links, link),
  };
}
function goalView(value: unknown): GoalView {
  const item = obj(value);
  return {
    goal: parseGoal(item.goal),
    links: list(item.links, (raw) => {
      const view = obj(raw);
      return {
        ...link(view),
        chapter_title: nullable(view.chapter_title, str),
        problem: nullable(view.problem, problem),
      };
    }),
    child_goal_ids: list(item.child_goal_ids, id),
    reflected: int(item.reflected),
    open_links: int(item.open_links),
  };
}
export function parseArcPlan(value: unknown, project: string): ArcPlan {
  const item = obj(value);
  if (item.project_id !== project) invalid();
  return {
    project_id: project,
    goals: list(item.goals, goalView),
    volumes: list(item.volumes, (raw) => {
      const volume = obj(raw);
      return {
        volume_id: id(volume.volume_id),
        title: str(volume.title),
        position: int(volume.position),
      };
    }),
    chapters: list(item.chapters, (raw) => {
      const chapter = obj(raw);
      return {
        chapter_id: id(chapter.chapter_id),
        volume_id: id(chapter.volume_id),
        title: str(chapter.title),
        volume_position: int(chapter.volume_position),
        position: int(chapter.position),
        revision_id: id(chapter.revision_id),
      };
    }),
    characters: list(item.characters, (raw) => {
      const character = obj(raw);
      return {
        character_id: id(character.character_id),
        name: str(character.name),
      };
    }),
  };
}
function anchor(value: unknown): EvidenceAnchor {
  const item = obj(value);
  return {
    role: anchorRole(item.role),
    chapter_id: id(item.chapter_id),
    chapter_revision_id: id(item.chapter_revision_id),
    quote: str(item.quote),
  };
}
export function parseThread(value: unknown): Thread {
  const item = obj(value);
  return {
    ...stored(item),
    title: str(item.title),
    content: str(item.content),
    character_ids: list(item.character_ids, id),
    planned_setup_chapter_id: nullable(item.planned_setup_chapter_id, id),
    planned_payoff_chapter_id: nullable(item.planned_payoff_chapter_id, id),
    planned_payoff_volume_id: nullable(item.planned_payoff_volume_id, id),
    priority: priority(item.priority),
    status: threadStatus(item.status),
    note: str(item.note),
    anchors: list(item.anchors, anchor),
  };
}
function threadView(value: unknown): ThreadView {
  const item = obj(value);
  return {
    thread: parseThread(item.thread),
    anchors: list(item.anchors, (raw) => {
      const view = obj(raw);
      return {
        anchor: anchor(view.anchor),
        chapter_title: nullable(view.chapter_title, str),
        stale: bool(view.stale),
      };
    }),
    evidence_stale: bool(item.evidence_stale),
    due: bool(item.due),
    due_reason: nullable(item.due_reason, str),
  };
}
export function parseEvent(value: unknown): StoryEvent {
  const item = obj(value);
  return {
    ...stored(item),
    title: str(item.title),
    description: str(item.description),
    story_time: str(item.story_time),
    chapter_id: nullable(item.chapter_id, id),
    character_ids: list(item.character_ids, id),
    after_event_ids: list(item.after_event_ids, id),
    before_event_ids: list(item.before_event_ids, id),
    archived: bool(item.archived),
  };
}
export function parseState(value: unknown): CharacterState {
  const item = obj(value);
  return {
    ...stored(item),
    character_id: id(item.character_id),
    attribute: attribute(item.attribute),
    label: str(item.label),
    value: str(item.value),
    start_event_id: id(item.start_event_id),
    end_event_id: nullable(item.end_event_id, id),
    fact_ids: list(item.fact_ids, id),
    archived: bool(item.archived),
  };
}
export function parseTimeline(value: unknown, project: string): Timeline {
  const item = obj(value);
  if (item.project_id !== project) invalid();
  return {
    project_id: project,
    threads: list(item.threads, threadView),
    events: list(item.events, (raw) => {
      const view = obj(raw);
      return {
        event: parseEvent(view.event),
        story_order: int(view.story_order),
        narrative_position: nullable(view.narrative_position, (v) =>
          list(v, int),
        ),
        chapter_title: nullable(view.chapter_title, str),
      };
    }),
    states: list(item.states, (raw) => {
      const view = obj(raw);
      return {
        state: parseState(view.state),
        invalid_fact_ids: list(view.invalid_fact_ids, id),
      };
    }),
    warnings: list(item.warnings, (raw) => {
      const warning = obj(raw);
      return {
        kind: warningKind(warning.kind),
        state_ids: list(warning.state_ids, id),
        message: str(warning.message),
      };
    }),
  };
}
export function parseGuide(value: unknown, chapter: string): ChapterGuide {
  const item = obj(value);
  if (item.chapter_id !== chapter) invalid();
  return {
    chapter_id: chapter,
    project_id: id(item.project_id),
    goals: list(item.goals, goalView),
    setup_threads: list(item.setup_threads, threadView),
    payoff_threads: list(item.payoff_threads, threadView),
    due_threads: list(item.due_threads, threadView),
  };
}
export function parseFactPage(value: unknown): FactSearchPage {
  const item = obj(value);
  return {
    items: list(item.items, (raw) => {
      const hit = obj(raw);
      return {
        id: id(hit.id),
        revision_id: id(hit.revision_id),
        chapter_id: id(hit.chapter_id),
        chapter_title: nullable(hit.chapter_title, str),
        title: str(hit.title),
        text: str(hit.text),
        quote: str(hit.quote),
        status: factStatus(hit.status),
        stale: bool(hit.stale),
        recallable_here: nullable(hit.recallable_here, bool),
      };
    }),
    total: int(item.total),
    offset: int(item.offset),
    limit: int(item.limit),
  };
}
export function parsePolicy(
  value: unknown,
  chapter: string,
): RecallPolicyState {
  const item = obj(value);
  if (item.chapter_id !== chapter) invalid();
  return {
    chapter_id: chapter,
    version: int(item.version),
    pinned_fact_ids: list(item.pinned_fact_ids, id),
    excluded_fact_ids: list(item.excluded_fact_ids, id),
    updated_at: nullable(item.updated_at, str),
  };
}
export function parsePreview(value: unknown, chapter: string): RecallPreview {
  const item = obj(value);
  if (item.chapter_id !== chapter) invalid();
  return {
    chapter_id: chapter,
    policy_version: int(item.policy_version),
    selected: list(item.selected, (raw) => {
      const choice = obj(raw);
      return {
        id: id(choice.id),
        revision_id: id(choice.revision_id),
        chapter_id: id(choice.chapter_id),
        title: str(choice.title),
        reason: recallReason(choice.reason),
        characters: int(choice.characters),
      };
    }),
    omitted: list(item.omitted, (raw) => {
      const omission = obj(raw);
      return {
        id: id(omission.id),
        title: nullable(omission.title, str),
        reason: omitReason(omission.reason),
      };
    }),
    omitted_total: int(item.omitted_total),
    excluded_total: int(item.excluded_total),
    used_characters: int(item.used_characters),
    character_limit: int(item.character_limit),
    item_limit: int(item.item_limit),
    blocked: bool(item.blocked),
  };
}

const MESSAGES: Record<string, string> = {
  AI_WORKFLOW_SCHEMA_REQUIRED:
    "需要先“备份并启用 AI 协作”（数据库升级）后才能使用故事规划；写作不受影响。",
  STORY_CONTROL_UNAVAILABLE: "故事规划暂不可用；写作不受影响。",
  STORY_CONTROL_CONFLICT:
    "内容已在其他窗口修改，或引用的正文已变化。已保留你的输入，请刷新后再保存。",
  STORY_CONTROL_INVALID:
    "有引用无效：章节、人物、事件或事实已不存在，或引文不在当前正文中。",
  STORY_CONTROL_CYCLE: "目标或事件的前后关系形成了循环，请修改关系。",
  STORY_CONTROL_NOT_FOUND: "该条目已不存在，请刷新。",
  PROJECT_NOT_FOUND: "这本小说已不存在或已删除。",
  CHAPTER_NOT_FOUND: "章节已不存在，请刷新。",
  INVALID_STORY_CONTROL_QUERY: "筛选条件无效，请重新选择。",
  VALIDATION_ERROR: "输入不完整或格式不正确，请检查必填项。",
};

export function storyControlError(error: unknown): StoryControlError {
  if (error instanceof StoryControlError) return error;
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) securitySession.clear();
    return new StoryControlError(
      MESSAGES[error.code] ??
        (error.status === 422
          ? MESSAGES.VALIDATION_ERROR
          : "故事规划请求失败，请稍后重试；正文没有受到影响。"),
      error.code,
    );
  }
  return new StoryControlError(
    "连接中断，故事规划暂未读取或保存；正文没有受到影响，可以重试。",
  );
}

async function request<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw storyControlError(error);
  }
}
async function csrf(): Promise<{ headers: Record<string, string> }> {
  const session = await securitySession.getValidSession();
  return { headers: { "X-CSRF-Token": session.csrfToken } };
}

function project(path: string, projectId: string): string {
  return `projects/${id(projectId)}/${path}`;
}
function chapter(path: string, chapterId: string): string {
  return `chapters/${id(chapterId)}/${path}`;
}
function save<T>(
  base: string,
  itemId: string | null,
  body: object,
  decode: (value: unknown) => T,
): Promise<T> {
  return request(async () => {
    const options = await csrf();
    return itemId === null
      ? postJson(base, body, decode, options)
      : putJson(`${base}/${id(itemId)}`, body, decode, options);
  });
}

export interface FactQuery {
  readonly q?: string;
  readonly status?: FactHit["status"];
  readonly forChapter?: string;
  readonly offset?: number;
  readonly limit?: number;
}

export const storyControlClient = {
  arcPlan: (projectId: string, signal?: AbortSignal) =>
    request(() =>
      getJson(
        project("arc-plans", projectId),
        (value) => parseArcPlan(value, projectId),
        { signal },
      ),
    ),
  saveGoal: (
    projectId: string,
    goalId: string | null,
    document: GoalDocument,
    expectedVersion: number,
  ) =>
    save(
      project("arc-plans", projectId),
      goalId,
      { ...document, expected_version: expectedVersion },
      parseGoal,
    ),
  timeline: (
    projectId: string,
    filters: {
      readonly character_id?: string;
      readonly volume_id?: string;
      readonly status?: ThreadStatus;
    } = {},
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters))
      if (value) query.set(key, value);
    const text = query.toString();
    const suffix = text ? `?${text}` : "";
    return request(() =>
      getJson(
        project(`timeline${suffix}`, projectId),
        (value) => parseTimeline(value, projectId),
        { signal },
      ),
    );
  },
  saveThread: (
    projectId: string,
    threadId: string | null,
    document: ThreadDocument,
    expectedVersion: number,
  ) =>
    save(
      project("plot-threads", projectId),
      threadId,
      { ...document, expected_version: expectedVersion },
      parseThread,
    ),
  saveEvent: (
    projectId: string,
    eventId: string | null,
    document: EventDocument,
    expectedVersion: number,
  ) =>
    save(
      project("story-events", projectId),
      eventId,
      { ...document, expected_version: expectedVersion },
      parseEvent,
    ),
  saveState: (
    projectId: string,
    stateId: string | null,
    document: StateDocument,
    expectedVersion: number,
  ) =>
    save(
      project("state-intervals", projectId),
      stateId,
      { ...document, expected_version: expectedVersion },
      parseState,
    ),
  guide: (chapterId: string, signal?: AbortSignal) =>
    request(() =>
      getJson(
        chapter("story-guide", chapterId),
        (value) => parseGuide(value, chapterId),
        { signal },
      ),
    ),
  searchFacts: (projectId: string, query: FactQuery, signal?: AbortSignal) => {
    const params = new URLSearchParams({
      offset: String(query.offset ?? 0),
      limit: String(query.limit ?? 20),
    });
    if (query.q) params.set("q", query.q);
    if (query.status) params.set("status", query.status);
    if (query.forChapter) params.set("for_chapter", id(query.forChapter));
    return request(() =>
      getJson(
        project(`facts/search?${params.toString()}`, projectId),
        parseFactPage,
        {
          signal,
        },
      ),
    );
  },
  recallPolicy: (chapterId: string, signal?: AbortSignal) =>
    request(() =>
      getJson(
        chapter("recall-policy", chapterId),
        (value) => parsePolicy(value, chapterId),
        { signal },
      ),
    ),
  saveRecallPolicy: (
    chapterId: string,
    pinned: readonly string[],
    excluded: readonly string[],
    expectedVersion: number,
  ) =>
    request(async () =>
      putJson(
        chapter("recall-policy", chapterId),
        {
          pinned_fact_ids: pinned,
          excluded_fact_ids: excluded,
          expected_version: expectedVersion,
        },
        (value) => parsePolicy(value, chapterId),
        await csrf(),
      ),
    ),
  recallPreview: (
    chapterId: string,
    pinned: readonly string[],
    excluded: readonly string[],
  ) =>
    request(async () =>
      postJson(
        chapter("recall-preview", chapterId),
        { pinned_fact_ids: pinned, excluded_fact_ids: excluded },
        (value) => parsePreview(value, chapterId),
        await csrf(),
      ),
    ),
};
export type StoryControlClient = typeof storyControlClient;
