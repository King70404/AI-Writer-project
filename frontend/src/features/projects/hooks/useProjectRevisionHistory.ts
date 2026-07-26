import { useCallback, useEffect, useRef, useState } from "react";

import {
  projectApiClient,
  type ProjectRevisionHistoryApiClient,
} from "../api/client";
import type {
  ProjectRevisionHistoryItemResponse,
  ProjectRevisionResponse,
} from "../api/contracts";
import {
  duplicateProjectRevisionContractError,
  normalizeProjectApiError,
  type ProjectApiError,
} from "../api/errors";
import { isCanonicalProjectId } from "../api/parsers";
import { PROJECT_REVISION_HISTORY_PAGE_SIZE } from "../constants";

export interface ProjectRevisionHistoryState {
  readonly status: "invalid" | "loading" | "ready" | "not_found" | "error";
  readonly items: readonly ProjectRevisionHistoryItemResponse[];
  readonly currentRevisionNumber: number | null;
  readonly hasMore: boolean;
  readonly nextCursor: string | null;
  readonly error: ProjectApiError | null;
  readonly loadMoreStatus: "idle" | "loading" | "error";
  readonly loadMoreError: ProjectApiError | null;
}

export type ProjectRevisionViewerState =
  | { readonly status: "idle" }
  | { readonly status: "loading"; readonly revisionNumber: number }
  | {
      readonly status: "ready";
      readonly revisionNumber: number;
      readonly revision: ProjectRevisionResponse;
    }
  | {
      readonly status: "error";
      readonly revisionNumber: number;
      readonly error: ProjectApiError;
    };

export interface ProjectRevisionHistoryController {
  readonly history: ProjectRevisionHistoryState;
  readonly viewer: ProjectRevisionViewerState;
  readonly reload: () => Promise<boolean>;
  readonly loadMore: () => Promise<void>;
  readonly selectRevision: (revisionNumber: number) => Promise<void>;
  readonly retrySelectedRevision: () => Promise<void>;
}

const loadingState: ProjectRevisionHistoryState = {
  status: "loading",
  items: [],
  currentRevisionNumber: null,
  hasMore: false,
  nextCursor: null,
  error: null,
  loadMoreStatus: "idle",
  loadMoreError: null,
};

const invalidState: ProjectRevisionHistoryState = {
  ...loadingState,
  status: "invalid",
};

export function useProjectRevisionHistory(
  projectId: string | undefined,
  client: ProjectRevisionHistoryApiClient = projectApiClient,
): ProjectRevisionHistoryController {
  const validProjectId = isCanonicalProjectId(projectId);
  const [history, setHistory] = useState<ProjectRevisionHistoryState>(
    validProjectId ? loadingState : invalidState,
  );
  const [viewer, setViewer] = useState<ProjectRevisionViewerState>({
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
      const page = await client.listProjectRevisions({
        projectId,
        limit: PROJECT_REVISION_HISTORY_PAGE_SIZE,
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
      const normalized = normalizeProjectApiError(error);
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
        status: normalized.kind === "not_found" ? "not_found" : "error",
        error: normalized,
      });
      return false;
    }
  }, [client, projectId, validProjectId]);

  const loadMore = useCallback(async (): Promise<void> => {
    const current = historyRef.current;
    if (
      !validProjectId ||
      current.status !== "ready" ||
      !current.hasMore ||
      current.nextCursor === null ||
      loadMoreInFlightRef.current
    ) {
      return;
    }
    loadMoreInFlightRef.current = true;
    const cursor = current.nextCursor;
    const generation = historyGenerationRef.current;
    const controller = new AbortController();
    historyControllerRef.current = controller;
    setHistory({ ...current, loadMoreStatus: "loading", loadMoreError: null });
    try {
      const page = await client.listProjectRevisions({
        projectId,
        limit: PROJECT_REVISION_HISTORY_PAGE_SIZE,
        cursor,
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
        page.project_id !== projectId ||
        page.items.some(
          (item) =>
            revisionIds.has(item.revision_id) ||
            revisionNumbers.has(item.revision_number),
        )
      ) {
        throw duplicateProjectRevisionContractError();
      }
      setHistory({
        status: "ready",
        items: [...current.items, ...page.items],
        currentRevisionNumber: current.currentRevisionNumber,
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
        error: null,
        loadMoreStatus: "idle",
        loadMoreError: null,
      });
    } catch (error) {
      const normalized = normalizeProjectApiError(error);
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
  }, [client, projectId, validProjectId]);

  const selectRevision = useCallback(
    async (revisionNumber: number): Promise<void> => {
      if (
        !validProjectId ||
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
        const revision = await client.getProjectRevision({
          projectId,
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
        const normalized = normalizeProjectApiError(error);
        if (
          !mountedRef.current ||
          generation !== viewerGenerationRef.current ||
          controller.signal.aborted ||
          normalized.kind === "aborted"
        ) {
          return;
        }
        setViewer({
          status: "error",
          revisionNumber,
          error: normalized,
        });
      }
    },
    [client, projectId, validProjectId],
  );

  const retrySelectedRevision = useCallback(async (): Promise<void> => {
    if (viewer.status === "loading" || viewer.status === "idle") {
      return;
    }
    await selectRevision(viewer.revisionNumber);
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
