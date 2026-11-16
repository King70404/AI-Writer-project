import { getJson, putJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";
import { isCanonicalProjectId } from "../../projects/api/parsers";

/**
 * 工作台汇总读模型（A2）。所有数字由服务端从已保存数据派生：
 * 字数为各章当前已保存正文的非空白字符数，AI 候选、规划与记忆不计入。
 */
export type EditorialStatus = "draft" | "review" | "final";
export type ActionKind =
  | "pending_candidate"
  | "stale_fact"
  | "pending_fact"
  | "stale_review"
  | "unfinished_review"
  | "final_changed"
  | "due_thread"
  | "budget_reminder";

export const EDITORIAL_LABELS: Record<EditorialStatus, string> = {
  draft: "草稿",
  review: "待检查",
  final: "定稿",
};

export const ACTION_LABELS: Record<ActionKind, string> = {
  stale_fact: "事实来源已变化",
  stale_review: "评审依据已变化",
  final_changed: "定稿后正文已修改",
  pending_candidate: "未处理的 AI 候选",
  pending_fact: "待确认事实",
  unfinished_review: "未完成的评审",
  due_thread: "到期伏笔或证据待复核",
  budget_reminder: "预算提醒",
};

export interface EditorialCounts {
  readonly draft: number;
  readonly review: number;
  readonly final: number;
}
export interface VolumeSummary {
  readonly volume_id: string;
  readonly title: string;
  readonly position: number;
  readonly chapter_count: number;
  readonly characters: number;
  readonly editorial: EditorialCounts;
}
export interface ActionCount {
  readonly kind: ActionKind;
  readonly items: number;
  readonly chapters: number;
}
export interface WorkspaceSummary {
  readonly project_id: string;
  readonly characters: number;
  readonly chapter_count: number;
  readonly volume_count: number;
  readonly editorial: EditorialCounts;
  readonly latest_chapter: {
    readonly chapter_id: string;
    readonly volume_id: string;
    readonly title: string;
    readonly position: number;
    readonly updated_at: string;
  } | null;
  readonly volumes: readonly VolumeSummary[];
  readonly actions: readonly ActionCount[];
  readonly action_total: number;
  readonly generated_at: string;
}
export interface ChapterSummary {
  readonly chapter_id: string;
  readonly volume_id: string;
  readonly title: string;
  readonly position: number;
  readonly characters: number;
  readonly updated_at: string;
  readonly editorial_status: EditorialStatus;
  readonly editorial_version: number;
  readonly content_changed_since_editorial: boolean;
  readonly open_actions: number;
}
export interface ActionItem {
  readonly kind: ActionKind;
  readonly chapter_id: string | null;
  readonly volume_id: string | null;
  readonly chapter_title: string;
  readonly chapter_position: number;
  readonly volume_position: number;
  readonly count: number;
  readonly entity_id?: string | null;
  readonly target_kind?: "chapter" | "thread" | "budget";
}
export interface Page<T> {
  readonly total: number;
  readonly offset: number;
  readonly next_offset: number | null;
  readonly items: readonly T[];
}
export interface EditorialState {
  readonly chapter_id: string;
  readonly project_id: string;
  readonly status: EditorialStatus;
  readonly version: number;
  readonly chapter_revision_id: string | null;
  readonly content_changed: boolean;
  readonly open_actions: number;
  readonly updated_at: string | null;
}

export class WorkbenchError extends Error {
  public readonly code: string;
  public constructor(message: string, code = "NETWORK") {
    super(message);
    this.name = "WorkbenchError";
    this.code = code;
  }
}

function invalid(): never {
  throw new WorkbenchError(
    "工作台汇总数据无法安全读取，请刷新。",
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
function count(value: unknown): number {
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
function nullable<T>(value: unknown, decode: (v: unknown) => T): T | null {
  return value === null ? null : decode(value);
}
function editorialStatus(value: unknown): EditorialStatus {
  const result = str(value);
  if (!(result in EDITORIAL_LABELS)) invalid();
  return result as EditorialStatus;
}
function actionKind(value: unknown): ActionKind {
  const result = str(value);
  if (!(result in ACTION_LABELS)) invalid();
  return result as ActionKind;
}
function editorialCounts(value: unknown): EditorialCounts {
  const item = obj(value);
  return {
    draft: count(item.draft),
    review: count(item.review),
    final: count(item.final),
  };
}

export function parseWorkspaceSummary(
  value: unknown,
  project: string,
): WorkspaceSummary {
  const item = obj(value);
  if (item.project_id !== project) invalid();
  return {
    project_id: project,
    characters: count(item.characters),
    chapter_count: count(item.chapter_count),
    volume_count: count(item.volume_count),
    editorial: editorialCounts(item.editorial),
    latest_chapter: nullable(item.latest_chapter, (raw) => {
      const latest = obj(raw);
      return {
        chapter_id: id(latest.chapter_id),
        volume_id: id(latest.volume_id),
        title: str(latest.title),
        position: count(latest.position),
        updated_at: str(latest.updated_at),
      };
    }),
    volumes: array(item.volumes, (raw) => {
      const volume = obj(raw);
      return {
        volume_id: id(volume.volume_id),
        title: str(volume.title),
        position: count(volume.position),
        chapter_count: count(volume.chapter_count),
        characters: count(volume.characters),
        editorial: editorialCounts(volume.editorial),
      };
    }),
    actions: array(item.actions, (raw) => {
      const action = obj(raw);
      return {
        kind: actionKind(action.kind),
        items: count(action.items),
        chapters: count(action.chapters),
      };
    }),
    action_total: count(item.action_total),
    generated_at: str(item.generated_at),
  };
}

function parsePage<T>(
  value: unknown,
  project: string,
  decode: (v: unknown) => T,
): Page<T> {
  const item = obj(value);
  if (item.project_id !== project) invalid();
  return {
    total: count(item.total),
    offset: count(item.offset),
    next_offset: nullable(item.next_offset, count),
    items: array(item.items, decode),
  };
}

export function parseChapterSummary(value: unknown): ChapterSummary {
  const item = obj(value);
  return {
    chapter_id: id(item.chapter_id),
    volume_id: id(item.volume_id),
    title: str(item.title),
    position: count(item.position),
    characters: count(item.characters),
    updated_at: str(item.updated_at),
    editorial_status: editorialStatus(item.editorial_status),
    editorial_version: count(item.editorial_version),
    content_changed_since_editorial: bool(item.content_changed_since_editorial),
    open_actions: count(item.open_actions),
  };
}

export function parseActionItem(value: unknown): ActionItem {
  const item = obj(value);
  const target = item.target_kind ?? "chapter";
  if (target !== "chapter" && target !== "thread" && target !== "budget")
    invalid();
  if (target === "chapter" && item.chapter_id === null) invalid();
  return {
    kind: actionKind(item.kind),
    chapter_id: nullable(item.chapter_id, id),
    volume_id: nullable(item.volume_id, id),
    chapter_title: str(item.chapter_title),
    chapter_position: count(item.chapter_position),
    volume_position: count(item.volume_position),
    count: count(item.count),
    ...(item.entity_id === undefined
      ? {}
      : { entity_id: nullable(item.entity_id, id) }),
    ...(item.target_kind === undefined ? {} : { target_kind: target }),
  };
}

export function parseEditorialState(
  value: unknown,
  chapter: string,
): EditorialState {
  const item = obj(value);
  if (item.chapter_id !== chapter) invalid();
  return {
    chapter_id: chapter,
    project_id: id(item.project_id),
    status: editorialStatus(item.status),
    version: count(item.version),
    chapter_revision_id: nullable(item.chapter_revision_id, id),
    content_changed: bool(item.content_changed),
    open_actions: count(item.open_actions),
    updated_at: nullable(item.updated_at, str),
  };
}

const MESSAGES: Record<string, string> = {
  AI_WORKFLOW_SCHEMA_REQUIRED:
    "需要先“备份并启用 AI 协作”（数据库升级）后才能显示汇总；继续写作不受影响。",
  WORKBENCH_UNAVAILABLE: "工作台汇总暂不可用；继续写作不受影响。",
  PROJECT_NOT_FOUND: "这本小说已不存在或已删除。",
  VOLUME_NOT_FOUND: "该卷已不存在，请刷新汇总。",
  CHAPTER_NOT_FOUND: "章节已不存在，请刷新。",
  EDITORIAL_CONFLICT:
    "章节状态已在其他窗口修改。已重新读取最新状态，请确认后再选择。",
  INVALID_WORKBENCH_QUERY: "汇总分页参数无效，请刷新。",
};

export function workbenchError(error: unknown): WorkbenchError {
  if (error instanceof WorkbenchError) return error;
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) securitySession.clear();
    if (error.code === "INVALID_RESPONSE") return workbenchErrorInvalid();
    return new WorkbenchError(
      MESSAGES[error.code] ?? "汇总读取失败，请稍后重试；正文没有受到影响。",
      error.code,
    );
  }
  return new WorkbenchError(
    "连接中断，汇总暂未读取；正文没有受到影响，可以重试。",
  );
}
function workbenchErrorInvalid(): WorkbenchError {
  return new WorkbenchError(
    "工作台汇总数据无法安全读取，请刷新。",
    "INVALID_RESPONSE",
  );
}

async function request<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw workbenchError(error);
  }
}

function projectPath(project: string): string {
  return `projects/${id(project)}/workspace`;
}
function pageQuery(offset: number, limit: number, volume?: string): string {
  const query = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
  });
  if (volume !== undefined) query.set("volume_id", id(volume));
  return query.toString();
}

export const workspaceClient = {
  summary: (project: string, signal?: AbortSignal) =>
    request(() =>
      getJson(
        projectPath(project),
        (value) => parseWorkspaceSummary(value, project),
        { signal },
      ),
    ),
  chapters: (
    project: string,
    offset: number,
    limit: number,
    volume?: string,
    signal?: AbortSignal,
  ) =>
    request(() =>
      getJson(
        `${projectPath(project)}/chapters?${pageQuery(offset, limit, volume)}`,
        (value) => parsePage(value, project, parseChapterSummary),
        { signal },
      ),
    ),
  actions: (
    project: string,
    offset: number,
    limit: number,
    signal?: AbortSignal,
  ) =>
    request(() =>
      getJson(
        `${projectPath(project)}/actions?${pageQuery(offset, limit)}`,
        (value) => parsePage(value, project, parseActionItem),
        { signal },
      ),
    ),
  editorial: (chapter: string, signal?: AbortSignal) =>
    request(() =>
      getJson(
        `chapters/${id(chapter)}/editorial-state`,
        (value) => parseEditorialState(value, chapter),
        { signal },
      ),
    ),
  saveEditorial: (
    chapter: string,
    status: EditorialStatus,
    expectedVersion: number,
  ) =>
    request(async () => {
      const session = await securitySession.getValidSession();
      return putJson(
        `chapters/${id(chapter)}/editorial-state`,
        { status, expected_version: expectedVersion },
        (value) => parseEditorialState(value, chapter),
        { headers: { "X-CSRF-Token": session.csrfToken } },
      );
    }),
};
export type WorkspaceClient = typeof workspaceClient;

export interface BookshelfSummary extends Pick<
  WorkspaceSummary,
  | "project_id"
  | "characters"
  | "chapter_count"
  | "volume_count"
  | "editorial"
  | "action_total"
> {
  readonly title: string;
}
export interface BookshelfOverviewPage {
  readonly total: number;
  readonly offset: number;
  readonly limit: number;
  readonly next_offset: number | null;
  readonly items: readonly BookshelfSummary[];
  readonly generated_at: string;
}
export function parseBookshelfOverview(
  value: unknown,
): BookshelfOverviewPage | null {
  if (value === null) return null;
  const item = obj(value);
  const result = {
    total: count(item.total),
    offset: count(item.offset),
    limit: count(item.limit),
    next_offset: nullable(item.next_offset, count),
    generated_at: str(item.generated_at),
    items: array(item.items, (raw) => {
      const book = obj(raw);
      if (!isCanonicalProjectId(book.project_id)) invalid();
      return {
        project_id: id(book.project_id),
        title: str(book.title),
        characters: count(book.characters),
        chapter_count: count(book.chapter_count),
        volume_count: count(book.volume_count),
        editorial: editorialCounts(book.editorial),
        action_total: count(book.action_total),
      };
    }),
  };
  if (
    result.limit < 1 ||
    result.limit > 100 ||
    result.items.length > result.limit ||
    (result.next_offset !== null &&
      result.next_offset !== result.offset + result.items.length)
  )
    invalid();
  return result;
}
export const bookshelfClient = {
  page: (offset: number, limit: number, signal?: AbortSignal) =>
    request(() =>
      getJson(
        `workspace/overview?${pageQuery(offset, limit)}`,
        parseBookshelfOverview,
        { signal },
      ),
    ),
};
