import { useCallback, useEffect, useRef, useState } from "react";

import {
  DRAFT_SAVE_DELAY_MS,
  DraftStorageError,
  draftKey,
  fetchStorageInstance,
  listDrafts,
  removeDraft,
  saveDraft,
  type StoredDraft,
} from "./drafts";

export interface DraftSource {
  readonly projectId: string;
  readonly chapterId: string;
  readonly chapterTitle: string;
  /** 编辑区当前文字。 */
  readonly content: string;
  /** 服务器已确认保存的正文及其版本。 */
  readonly savedContent: string;
  readonly savedRevisionId: string;
  readonly savedVersion: number;
}

export type InstanceState =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly id: string }
  | { readonly status: "unavailable" };

/**
 * 编辑中有界延迟保存本机草稿；服务器确认相同内容后才清理。重开章节时列出可恢复的草稿，
 * 只核对存储实例、章节归属和内容，不自动写回服务器。
 */
export function useLocalDraft(
  source: DraftSource,
  loadInstance: () => Promise<string> = fetchStorageInstance,
) {
  const [instance, setInstance] = useState<InstanceState>({
    status: "loading",
  });
  const [sessionId] = useState(() => crypto.randomUUID());
  const [storageError, setStorageError] = useState(false);
  const [recoverable, setRecoverable] = useState<readonly StoredDraft[]>([]);
  const [foreign, setForeign] = useState(0);
  const scanned = useRef(false);
  const loader = useRef(loadInstance);
  const latest = useRef(source);
  useEffect(() => {
    latest.current = source;
  });
  useEffect(() => {
    let alive = true;
    loader
      .current()
      .then((id) => {
        if (alive) setInstance({ status: "ready", id });
      })
      .catch(() => {
        if (alive) setInstance({ status: "unavailable" });
      });
    return () => {
      alive = false;
    };
  }, []);
  const { projectId, chapterId } = source;
  // Scan once per opened chapter: other sessions' drafts that differ from the server.
  useEffect(() => {
    if (instance.status !== "ready" || scanned.current) return;
    scanned.current = true;
    const all = listDrafts(projectId, chapterId).filter(
      (item) => item.draft.sessionId !== sessionId,
    );
    const saved = latest.current.savedContent;
    for (const item of all)
      if (item.draft.instance === instance.id && item.draft.content === saved)
        removeDraft(item.key); // The server already holds this exact text.
    setRecoverable(
      all.filter(
        (item) =>
          item.draft.instance === instance.id && item.draft.content !== saved,
      ),
    );
    setForeign(
      all.filter((item) => item.draft.instance !== instance.id).length,
    );
  }, [chapterId, instance, projectId, sessionId]);
  const { content, savedContent, savedRevisionId, savedVersion, chapterTitle } =
    source;
  useEffect(() => {
    if (instance.status !== "ready") return;
    const key = draftKey({
      instance: instance.id,
      projectId,
      chapterId,
      sessionId,
    });
    if (content === savedContent) {
      removeDraft(key);
      return;
    }
    const timer = window.setTimeout(() => {
      try {
        saveDraft({
          v: 1,
          instance: instance.id,
          projectId,
          chapterId,
          sessionId,
          chapterTitle,
          baseRevisionId: savedRevisionId,
          baseVersion: savedVersion,
          content,
          updatedAt: new Date().toISOString(),
        });
        setStorageError(false);
      } catch (error) {
        if (error instanceof DraftStorageError) setStorageError(true);
      }
    }, DRAFT_SAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [
    chapterId,
    chapterTitle,
    content,
    instance,
    projectId,
    savedContent,
    savedRevisionId,
    savedVersion,
    sessionId,
  ]);
  const discard = useCallback((key: string) => {
    removeDraft(key);
    setRecoverable((items) => items.filter((item) => item.key !== key));
  }, []);
  const dismiss = useCallback((key: string) => {
    setRecoverable((items) => items.filter((item) => item.key !== key));
  }, []);
  return {
    instance,
    // A failure only matters while unsaved text exists.
    storageError: storageError && content !== savedContent,
    recoverable,
    foreign,
    discard,
    dismiss,
  };
}
