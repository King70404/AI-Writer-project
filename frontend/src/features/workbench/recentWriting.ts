import { isCanonicalPrefixedUlid } from "../../api/identifiers";

/**
 * 本机“继续写作”定位记录：只保存小说/章节标识与打开时间，
 * 不保存正文、标题、ETag、游标或任何安全信息。服务端数据始终是事实源。
 */
export const RECENT_WRITING_KEY = "aiwebnovel.recent-writing.v1";
const MAX_PROJECTS = 50;

export interface RecentChapter {
  readonly projectId: string;
  readonly chapterId: string;
  readonly openedAt: string;
}

interface RecentWritingRecord {
  readonly last: RecentChapter | null;
  readonly byProject: readonly RecentChapter[];
}

const EMPTY: RecentWritingRecord = { last: null, byProject: [] };

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

function parseEntry(value: unknown): RecentChapter | null {
  if (typeof value !== "object" || value === null) return null;
  const entry = value as Record<string, unknown>;
  const { projectId, chapterId, openedAt } = entry;
  if (
    typeof projectId !== "string" ||
    typeof chapterId !== "string" ||
    typeof openedAt !== "string" ||
    !isCanonicalPrefixedUlid(projectId, "prj") ||
    !isCanonicalPrefixedUlid(chapterId, "chp") ||
    Number.isNaN(Date.parse(openedAt))
  )
    return null;
  return { projectId, chapterId, openedAt };
}

function read(): RecentWritingRecord {
  const store = storage();
  if (!store) return EMPTY;
  try {
    const raw = store.getItem(RECENT_WRITING_KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const byProject = Array.isArray(parsed.byProject)
      ? parsed.byProject
          .map(parseEntry)
          .filter((item): item is RecentChapter => item !== null)
      : [];
    return { last: parseEntry(parsed.last), byProject };
  } catch {
    return EMPTY;
  }
}

function write(record: RecentWritingRecord): void {
  const store = storage();
  if (!store) return;
  try {
    if (!record.last && !record.byProject.length)
      store.removeItem(RECENT_WRITING_KEY);
    else store.setItem(RECENT_WRITING_KEY, JSON.stringify(record));
  } catch {
    /* 本机记录不可用时只失去“继续写作”快捷入口，不影响写作。 */
  }
}

export function recordRecentChapter(
  projectId: string,
  chapterId: string,
  now: Date = new Date(),
): void {
  if (
    !isCanonicalPrefixedUlid(projectId, "prj") ||
    !isCanonicalPrefixedUlid(chapterId, "chp")
  )
    return;
  const entry = { projectId, chapterId, openedAt: now.toISOString() };
  const current = read();
  write({
    last: entry,
    byProject: [
      entry,
      ...current.byProject.filter((item) => item.projectId !== projectId),
    ].slice(0, MAX_PROJECTS),
  });
}

export function lastRecentChapter(): RecentChapter | null {
  return read().last;
}

export function recentChapterForProject(
  projectId: string,
): RecentChapter | null {
  return read().byProject.find((item) => item.projectId === projectId) ?? null;
}

/** 目标章节被删除或不属于该小说时移除失效记录，回退到结构页。 */
export function forgetRecentChapter(
  projectId: string,
  chapterId: string,
): void {
  const current = read();
  const matches = (item: RecentChapter | null) =>
    item?.projectId === projectId && item.chapterId === chapterId;
  write({
    last: matches(current.last) ? null : current.last,
    byProject: current.byProject.filter((item) => !matches(item)),
  });
}
