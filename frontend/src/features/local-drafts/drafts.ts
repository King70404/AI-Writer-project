import { getJson } from "../../api/client";

/**
 * 本机草稿（WF-06）：作者本机浏览器里的恢复辅助，不是已保存正文，也不属于服务器备份。
 * 键包含存储实例、小说、章节与编辑会话，多个标签页互不覆盖；不同数据根（如恢复副本）
 * 的草稿不会自动套用到同 ID 章节。草稿不含模型密钥，也不参与模型发送。
 */
export const DRAFT_PREFIX = "aiwn.draft.v1:";
export const DRAFT_SAVE_DELAY_MS = 800;

export interface LocalDraft {
  readonly v: 1;
  readonly instance: string;
  readonly projectId: string;
  readonly chapterId: string;
  readonly sessionId: string;
  readonly chapterTitle: string;
  readonly baseRevisionId: string;
  readonly baseVersion: number;
  readonly content: string;
  readonly updatedAt: string;
}
export interface StoredDraft {
  readonly key: string;
  readonly draft: LocalDraft;
}

export class DraftStorageError extends Error {
  constructor() {
    super("本机草稿未能保存：浏览器存储不可用或空间不足。");
    this.name = "DraftStorageError";
  }
}

const SEGMENT = /^[A-Za-z0-9_-]{1,100}$/u;

export function draftKey(
  draft: Pick<LocalDraft, "instance" | "projectId" | "chapterId" | "sessionId">,
): string {
  return `${DRAFT_PREFIX}${draft.instance}:${draft.projectId}:${draft.chapterId}:${draft.sessionId}`;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function parse(key: string, raw: string | null): LocalDraft | null {
  if (raw === null) return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null) return null;
  const item = value as Record<string, unknown>;
  if (
    item.v !== 1 ||
    typeof item.instance !== "string" ||
    typeof item.projectId !== "string" ||
    typeof item.chapterId !== "string" ||
    typeof item.sessionId !== "string" ||
    ![item.instance, item.projectId, item.chapterId, item.sessionId].every(
      (part) => SEGMENT.test(part),
    ) ||
    typeof item.chapterTitle !== "string" ||
    typeof item.baseRevisionId !== "string" ||
    typeof item.baseVersion !== "number" ||
    typeof item.content !== "string" ||
    typeof item.updatedAt !== "string"
  )
    return null;
  const draft = item as unknown as LocalDraft;
  return draftKey(draft) === key ? draft : null;
}

export function saveDraft(draft: LocalDraft): void {
  const target = storage();
  if (target === null) throw new DraftStorageError();
  try {
    target.setItem(draftKey(draft), JSON.stringify(draft));
  } catch {
    throw new DraftStorageError();
  }
}

export function removeDraft(key: string): void {
  try {
    storage()?.removeItem(key);
  } catch {
    // An unavailable store holds nothing to remove.
  }
}

/** 列出某小说（可选某章）的全部本机草稿，最新在前；无法解析的条目不删除也不返回。 */
export function listDrafts(
  projectId: string,
  chapterId?: string,
): StoredDraft[] {
  const target = storage();
  if (target === null) return [];
  const found: StoredDraft[] = [];
  try {
    for (let index = 0; index < target.length; index += 1) {
      const key = target.key(index);
      if (!key?.startsWith(DRAFT_PREFIX)) continue;
      const draft = parse(key, target.getItem(key));
      if (
        draft &&
        draft.projectId === projectId &&
        (chapterId === undefined || draft.chapterId === chapterId)
      )
        found.push({ key, draft });
    }
  } catch {
    return found;
  }
  return found.sort((a, b) =>
    b.draft.updatedAt.localeCompare(a.draft.updatedAt),
  );
}

export function downloadText(filename: string, content: string): void {
  const url = URL.createObjectURL(
    new Blob([content], { type: "text/plain;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function draftFilename(title: string, when: string): string {
  const safe = title.replace(/[\\/:*?"<>|\u0000-\u001f]/gu, "_").slice(0, 60);
  const stamp = when.replace(/[^0-9]/gu, "").slice(0, 14);
  return `${safe || "章节"}-本机草稿-${stamp}.txt`;
}

export async function fetchStorageInstance(): Promise<string> {
  const result = await getJson("storage-instance", (value) => {
    if (
      typeof value !== "object" ||
      value === null ||
      typeof (value as Record<string, unknown>).storage_instance_id !==
        "string" ||
      !/^[0-9a-f]{32}$/u.test(
        (value as Record<string, string>).storage_instance_id,
      )
    )
      throw new Error("invalid storage instance");
    return (value as Record<string, string>).storage_instance_id;
  });
  return result.data;
}
