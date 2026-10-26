import { useCallback, useEffect, useRef, useState } from "react";

import {
  NovelStructureApiError,
  type NovelStructureApiClient,
} from "../api/client";
import { normalizeManuscript } from "../api/content";
import type { VersionedChapterContent } from "../api/contracts";

export const CHAPTER_AUTOSAVE_MS = 1000;
export type SaveStatus = "saved" | "dirty" | "saving" | "error" | "conflict";

interface WritingState {
  readonly content: string;
  readonly snapshot: VersionedChapterContent;
  readonly status: SaveStatus;
  readonly reloading: boolean;
  readonly reloadFailed: boolean;
}

export function useChapterWriting(
  initial: VersionedChapterContent,
  client: NovelStructureApiClient,
) {
  const [state, setState] = useState<WritingState>({
    content: initial.resource.content,
    snapshot: initial,
    status: "saved",
    reloading: false,
    reloadFailed: false,
  });
  const current = useRef(state);
  const mounted = useRef(false);
  const inFlight = useRef(false);
  const saveWaiters = useRef<(() => void)[]>([]);
  const operation = useRef<AbortController | null>(null);
  const publish = useCallback((next: WritingState) => {
    current.current = next;
    setState(next);
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      operation.current?.abort();
    };
  }, []);

  const save = useCallback(async () => {
    const before = current.current;
    if (
      !mounted.current ||
      inFlight.current ||
      before.reloading ||
      before.reloadFailed ||
      before.status === "conflict" ||
      before.status === "saved"
    )
      return;
    inFlight.current = true;
    const controller = new AbortController();
    operation.current = controller;
    const submitted = before.content;
    publish({ ...before, status: "saving" });
    try {
      const result = await client.updateChapterContent(
        before.snapshot.resource.chapter_id,
        before.snapshot.resource.project_id,
        submitted,
        before.snapshot.etag,
        controller.signal,
      );
      if (!mounted.current) return;
      const latest = current.current;
      const unchanged = latest.content === submitted;
      publish({
        ...latest,
        snapshot: result,
        content: unchanged ? result.resource.content : latest.content,
        status: unchanged ? "saved" : "dirty",
      });
    } catch (error) {
      if (!mounted.current) return;
      publish({
        ...current.current,
        status:
          error instanceof NovelStructureApiError && error.kind === "conflict"
            ? "conflict"
            : "error",
      });
    } finally {
      inFlight.current = false;
      saveWaiters.current.splice(0).forEach((resolve) => resolve());
    }
  }, [client, publish]);

  const flush = useCallback(async (): Promise<boolean> => {
    while (mounted.current) {
      const latest = current.current;
      if (
        latest.reloading ||
        latest.reloadFailed ||
        latest.status === "error" ||
        latest.status === "conflict"
      )
        return false;
      if (inFlight.current) {
        await new Promise<void>((resolve) => saveWaiters.current.push(resolve));
      } else if (latest.status === "saved") {
        return true;
      } else {
        await save();
      }
    }
    return false;
  }, [save]);

  const getContent = useCallback(() => current.current.content, []);

  const edit = useCallback(
    (value: string) => {
      const before = current.current;
      if (before.reloading || before.reloadFailed) return;
      publish({
        ...before,
        content: normalizeManuscript(value),
        status:
          before.status === "conflict"
            ? "conflict"
            : inFlight.current
              ? "saving"
              : "dirty",
      });
    },
    [publish],
  );

  const reloadServer = useCallback(async () => {
    const before = current.current;
    if (inFlight.current || before.reloading) return;
    const controller = new AbortController();
    operation.current = controller;
    publish({ ...before, reloading: true, reloadFailed: false });
    try {
      const result = await client.getChapterContent(
        before.snapshot.resource.chapter_id,
        before.snapshot.resource.project_id,
        controller.signal,
      );
      if (!mounted.current) return;
      if (result.resource.volume_id !== before.snapshot.resource.volume_id)
        throw new Error("Chapter ownership changed.");
      publish({
        content: result.resource.content,
        snapshot: result,
        status: "saved",
        reloading: false,
        reloadFailed: false,
      });
    } catch {
      if (!mounted.current) return;
      publish({ ...current.current, reloading: false, reloadFailed: true });
    }
  }, [client, publish]);

  /**
   * 版本冲突后作者明确选择保留本地正文：读取服务器最新版本作为新的版本条件，
   * 本地文字保持不变，随后照常（带版本检查）保存。不自动合并。
   */
  const keepLocal = useCallback(async (): Promise<boolean> => {
    const before = current.current;
    if (before.status !== "conflict" || inFlight.current || before.reloading)
      return false;
    const controller = new AbortController();
    operation.current = controller;
    publish({ ...before, reloading: true, reloadFailed: false });
    try {
      const result = await client.getChapterContent(
        before.snapshot.resource.chapter_id,
        before.snapshot.resource.project_id,
        controller.signal,
      );
      if (!mounted.current) return false;
      if (result.resource.volume_id !== before.snapshot.resource.volume_id)
        throw new Error("Chapter ownership changed.");
      const local = current.current.content;
      publish({
        content: local,
        snapshot: result,
        status: local === result.resource.content ? "saved" : "dirty",
        reloading: false,
        reloadFailed: false,
      });
      return true;
    } catch {
      if (mounted.current)
        publish({ ...current.current, reloading: false, status: "conflict" });
      return false;
    }
  }, [client, publish]);

  const acceptExternal = useCallback(
    async (commit: () => Promise<void>): Promise<boolean> => {
      const before = current.current;
      if (
        inFlight.current ||
        before.reloading ||
        before.reloadFailed ||
        before.status !== "saved"
      )
        return false;
      // Lock local editing across adoption and the authoritative content read.
      // A successful server adoption is never written again through autosave.
      publish({ ...before, reloading: true, reloadFailed: false });
      try {
        await commit();
        const result = await client.getChapterContent(
          before.snapshot.resource.chapter_id,
          before.snapshot.resource.project_id,
        );
        if (!mounted.current) return false;
        if (
          result.resource.volume_id !== before.snapshot.resource.volume_id ||
          result.version < before.snapshot.version
        )
          throw new Error("Chapter snapshot changed unexpectedly.");
        publish({
          content: result.resource.content,
          snapshot: result,
          status: "saved",
          reloading: false,
          reloadFailed: false,
        });
        return true;
      } catch (failure) {
        if (mounted.current)
          publish({
            ...current.current,
            status: "conflict",
            reloading: false,
            reloadFailed: true,
          });
        throw failure;
      }
    },
    [client, publish],
  );

  useEffect(() => {
    if (state.status !== "dirty" || state.reloading) return;
    const timer = window.setTimeout(() => {
      void save();
    }, CHAPTER_AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [save, state.content, state.reloading, state.status]);

  useEffect(() => {
    if (state.status === "saved") return;
    const protect = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [state.status]);

  return {
    state,
    edit,
    save,
    reloadServer,
    flush,
    getContent,
    acceptExternal,
    keepLocal,
  };
}
