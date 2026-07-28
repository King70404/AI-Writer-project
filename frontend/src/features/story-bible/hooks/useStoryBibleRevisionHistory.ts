import { useCallback, useEffect, useRef, useState } from "react";

import {
  storyBibleApiClient,
  storyBibleRevisionHistoryApiClient,
  type StoryBibleApiClient,
  type StoryBibleRevisionHistoryApiClient,
} from "../api/client";
import type {
  StoryBibleRevisionHistoryItemResponse,
  StoryBibleRevisionResponse,
} from "../api/contracts";
import {
  normalizeStoryBibleApiError,
  storyBibleContractError,
  type StoryBibleApiError,
} from "../api/errors";
import { isCanonicalStoryBibleProjectId } from "../api/parsers";

const HISTORY_PAGE_SIZE = 20;

export interface StoryBibleRevisionHistoryState {
  readonly status: "invalid" | "loading" | "ready" | "not_found" | "error";
  readonly storyBibleId: string | null;
  readonly items: readonly StoryBibleRevisionHistoryItemResponse[];
  readonly currentRevisionNumber: number | null;
  readonly hasMore: boolean;
  readonly nextCursor: string | null;
  readonly error: StoryBibleApiError | null;
  readonly loadMoreStatus: "idle" | "loading" | "error";
  readonly loadMoreError: StoryBibleApiError | null;
}

export type StoryBibleRevisionViewerState =
  | { readonly status: "idle" }
  | { readonly status: "loading"; readonly revisionNumber: number }
  | {
      readonly status: "ready";
      readonly revisionNumber: number;
      readonly revision: StoryBibleRevisionResponse;
    }
  | {
      readonly status: "error";
      readonly revisionNumber: number;
      readonly error: StoryBibleApiError;
    };

export interface StoryBibleRevisionHistoryController {
  readonly history: StoryBibleRevisionHistoryState;
  readonly viewer: StoryBibleRevisionViewerState;
  readonly reload: () => Promise<boolean>;
  readonly loadMore: () => Promise<void>;
  readonly selectRevision: (revisionNumber: number) => Promise<void>;
  readonly retrySelectedRevision: () => Promise<void>;
}

const loadingState: StoryBibleRevisionHistoryState = {
  status: "loading",
  storyBibleId: null,
  items: [],
  currentRevisionNumber: null,
  hasMore: false,
  nextCursor: null,
  error: null,
  loadMoreStatus: "idle",
  loadMoreError: null,
};

const invalidState: StoryBibleRevisionHistoryState = {
  ...loadingState,
  status: "invalid",
};

export function useStoryBibleRevisionHistory(
  projectId: string | undefined,
  currentClient: StoryBibleApiClient = storyBibleApiClient,
  historyClient: StoryBibleRevisionHistoryApiClient = storyBibleRevisionHistoryApiClient,
): StoryBibleRevisionHistoryController {
  const validProjectId = isCanonicalStoryBibleProjectId(projectId);
  const [history, setHistory] = useState<StoryBibleRevisionHistoryState>(
    validProjectId ? loadingState : invalidState,
  );
  const [viewer, setViewer] = useState<StoryBibleRevisionViewerState>({
    status: "idle",
  });
  const historyRef = useRef(history);
  const historyGenerationRef = useRef(0);
  const viewerGenerationRef = useRef(0);
  const historyControllerRef = useRef<AbortController | null>(null);
  const viewerControllerRef = useRef<AbortController | null>(null);
  const loadMoreInFlightRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  const reload = useCallback(async (): Promise<boolean> => {
    historyGenerationRef.current += 1;
    viewerGenerationRef.current += 1;
    const generation = historyGenerationRef.current;
    historyControllerRef.current?.abort();
    viewerControllerRef.current?.abort();
    loadMoreInFlightRef.current = false;
    setViewer({ status: "idle" });
    if (!validProjectId) {
      setHistory(invalidState);
      return false;
    }
    const controller = new AbortController();
    historyControllerRef.current = controller;
    setHistory(loadingState);
    try {
      const current = await currentClient.getStoryBibleForProject({
        projectId,
        signal: controller.signal,
      });
      const storyBibleId = current.storyBible.story_bible_id;
      const page = await historyClient.listStoryBibleRevisions({
        storyBibleId,
        expectedProjectId: projectId,
        limit: HISTORY_PAGE_SIZE,
        signal: controller.signal,
      });
      if (
        !mountedRef.current ||
        generation !== historyGenerationRef.current ||
        controller.signal.aborted
      ) {
        return false;
      }
      setHistory({
        status: "ready",
        storyBibleId,
        items: page.items,
        currentRevisionNumber: page.current_revision_number,
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
        error: null,
        loadMoreStatus: "idle",
        loadMoreError: null,
      });
      return true;
    } catch (error) {
      const normalized = normalizeStoryBibleApiError(error);
      if (
        !mountedRef.current ||
        generation !== historyGenerationRef.current ||
        controller.signal.aborted ||
        normalized.kind === "aborted"
      ) {
        return false;
      }
      setHistory({
        ...loadingState,
        status:
          normalized.kind === "project_not_found" ||
          normalized.kind === "story_bible_for_project_not_found"
            ? "not_found"
            : "error",
        error: normalized,
      });
      return false;
    }
  }, [currentClient, historyClient, projectId, validProjectId]);

  const loadMore = useCallback(async (): Promise<void> => {
    const current = historyRef.current;
    if (
      !validProjectId ||
      current.status !== "ready" ||
      current.storyBibleId === null ||
      !current.hasMore ||
      current.nextCursor === null ||
      loadMoreInFlightRef.current
    ) {
      return;
    }
    loadMoreInFlightRef.current = true;
    const generation = historyGenerationRef.current;
    const controller = new AbortController();
    historyControllerRef.current = controller;
    setHistory({ ...current, loadMoreStatus: "loading", loadMoreError: null });
    try {
      const page = await historyClient.listStoryBibleRevisions({
        storyBibleId: current.storyBibleId,
        expectedProjectId: projectId,
        limit: HISTORY_PAGE_SIZE,
        cursor: current.nextCursor,
        signal: controller.signal,
      });
      if (
        !mountedRef.current ||
        generation !== historyGenerationRef.current ||
        controller.signal.aborted
      ) {
        return;
      }
      const revisionIds = new Set(
        current.items.map((item) => item.revision_id),
      );
      const revisionNumbers = new Set(
        current.items.map((item) => item.revision_number),
      );
      if (
        page.story_bible_id !== current.storyBibleId ||
        page.items.some(
          (item) =>
            revisionIds.has(item.revision_id) ||
            revisionNumbers.has(item.revision_number),
        )
      ) {
        throw storyBibleContractError();
      }
      setHistory({
        ...current,
        items: [...current.items, ...page.items],
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
        loadMoreStatus: "idle",
        loadMoreError: null,
      });
    } catch (error) {
      const normalized = normalizeStoryBibleApiError(error);
      if (
        !mountedRef.current ||
        generation !== historyGenerationRef.current ||
        controller.signal.aborted ||
        normalized.kind === "aborted"
      ) {
        return;
      }
      setHistory({
        ...current,
        loadMoreStatus: "error",
        loadMoreError: normalized,
      });
    } finally {
      loadMoreInFlightRef.current = false;
    }
  }, [historyClient, projectId, validProjectId]);

  const selectRevision = useCallback(
    async (revisionNumber: number): Promise<void> => {
      const current = historyRef.current;
      if (
        !validProjectId ||
        current.status !== "ready" ||
        current.storyBibleId === null ||
        !Number.isSafeInteger(revisionNumber) ||
        revisionNumber < 1
      ) {
        return;
      }
      viewerGenerationRef.current += 1;
      const generation = viewerGenerationRef.current;
      viewerControllerRef.current?.abort();
      const controller = new AbortController();
      viewerControllerRef.current = controller;
      setViewer({ status: "loading", revisionNumber });
      try {
        const revision = await historyClient.getStoryBibleRevision({
          storyBibleId: current.storyBibleId,
          expectedProjectId: projectId,
          revisionNumber,
          signal: controller.signal,
        });
        if (
          !mountedRef.current ||
          generation !== viewerGenerationRef.current ||
          controller.signal.aborted
        ) {
          return;
        }
        setViewer({ status: "ready", revisionNumber, revision });
      } catch (error) {
        const normalized = normalizeStoryBibleApiError(error);
        if (
          !mountedRef.current ||
          generation !== viewerGenerationRef.current ||
          controller.signal.aborted ||
          normalized.kind === "aborted"
        ) {
          return;
        }
        setViewer({ status: "error", revisionNumber, error: normalized });
      }
    },
    [historyClient, projectId, validProjectId],
  );

  const retrySelectedRevision = useCallback(async (): Promise<void> => {
    if (viewer.status !== "idle" && viewer.status !== "loading") {
      await selectRevision(viewer.revisionNumber);
    }
  }, [selectRevision, viewer]);

  useEffect(() => {
    mountedRef.current = true;
    let active = true;
    queueMicrotask(() => {
      if (active) {
        void reload();
      }
    });
    return () => {
      active = false;
      mountedRef.current = false;
      historyGenerationRef.current += 1;
      viewerGenerationRef.current += 1;
      historyControllerRef.current?.abort();
      viewerControllerRef.current?.abort();
    };
  }, [reload]);

  return {
    history,
    viewer,
    reload,
    loadMore,
    selectRevision,
    retrySelectedRevision,
  };
}
