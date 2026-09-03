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
    }
  }, [client, publish]);

  const edit = useCallback(
    (value: string) => {
      const before = current.current;
      if (before.reloading) return;
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

  return { state, edit, save, reloadServer };
}
