import { useCallback, useEffect, useRef, useState } from "react";

import {
  characterRevisionHistoryApiClient,
  type CharacterRevisionHistoryApiClient,
} from "../api/history";
import type {
  CharacterRevisionHistoryItemResponse,
  CharacterRevisionResponse,
} from "../api/contracts";
import {
  normalizeCharacterApiError,
  type CharacterApiError,
} from "../api/errors";
import {
  isCanonicalCharacterId,
  isCanonicalCharacterProjectId,
} from "../api/parsers";

const HISTORY_PAGE_SIZE = 20;

export type CharacterRevisionHistoryStatus =
  | "invalid_route"
  | "loading_history"
  | "character_not_found"
  | "project_mismatch"
  | "ready"
  | "empty"
  | "error";

export interface CharacterRevisionHistoryState {
  readonly status: CharacterRevisionHistoryStatus;
  readonly items: readonly CharacterRevisionHistoryItemResponse[];
  readonly currentRevisionNumber: number | null;
  readonly hasMore: boolean;
  readonly nextCursor: string | null;
  readonly error: CharacterApiError | null;
  readonly loadMoreStatus: "idle" | "loading_more" | "load_more_error";
  readonly loadMoreError: CharacterApiError | null;
}

export type CharacterRevisionViewerState =
  | { readonly status: "idle" }
  | { readonly status: "loading_revision"; readonly revisionNumber: number }
  | {
      readonly status: "ready";
      readonly revisionNumber: number;
      readonly revision: CharacterRevisionResponse;
    }
  | {
      readonly status: "revision_error";
      readonly revisionNumber: number;
      readonly error: CharacterApiError;
    };

const loadingState: CharacterRevisionHistoryState = {
  status: "loading_history",
  items: [],
  currentRevisionNumber: null,
  hasMore: false,
  nextCursor: null,
  error: null,
  loadMoreStatus: "idle",
  loadMoreError: null,
};

export function useCharacterRevisionHistory(
  projectId: string | undefined,
  characterId: string | undefined,
  client: CharacterRevisionHistoryApiClient = characterRevisionHistoryApiClient,
) {
  const validRoute =
    isCanonicalCharacterProjectId(projectId) &&
    isCanonicalCharacterId(characterId);
  const [history, setHistory] = useState<CharacterRevisionHistoryState>(
    validRoute ? loadingState : { ...loadingState, status: "invalid_route" },
  );
  const [viewer, setViewer] = useState<CharacterRevisionViewerState>({
    status: "idle",
  });
  const historyRef = useRef(history);
  const historyGeneration = useRef(0);
  const viewerGeneration = useRef(0);
  const historyController = useRef<AbortController | null>(null);
  const viewerController = useRef<AbortController | null>(null);
  const loadMoreInFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  const reload = useCallback(async (): Promise<boolean> => {
    historyGeneration.current += 1;
    viewerGeneration.current += 1;
    const generation = historyGeneration.current;
    historyController.current?.abort();
    viewerController.current?.abort();
    loadMoreInFlight.current = false;
    setViewer({ status: "idle" });
    if (!validRoute) {
      setHistory({ ...loadingState, status: "invalid_route" });
      return false;
    }
    const controller = new AbortController();
    historyController.current = controller;
    setHistory(loadingState);
    try {
      const page = await client.listCharacterRevisions({
        characterId,
        expectedProjectId: projectId,
        limit: HISTORY_PAGE_SIZE,
        signal: controller.signal,
      });
      if (
        !mounted.current ||
        generation !== historyGeneration.current ||
        controller.signal.aborted
      ) {
        return false;
      }
      if (page.character_id !== characterId || page.project_id !== projectId) {
        setHistory({ ...loadingState, status: "project_mismatch" });
        return false;
      }
      setHistory({
        status: page.items.length === 0 ? "empty" : "ready",
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
      const normalized = normalizeCharacterApiError(error);
      if (
        !mounted.current ||
        generation !== historyGeneration.current ||
        controller.signal.aborted ||
        normalized.kind === "aborted"
      ) {
        return false;
      }
      setHistory({
        ...loadingState,
        status:
          normalized.kind === "character_not_found"
            ? "character_not_found"
            : "error",
        error: normalized,
      });
      return false;
    }
  }, [characterId, client, projectId, validRoute]);

  const loadMore = useCallback(async (): Promise<void> => {
    const current = historyRef.current;
    if (
      !validRoute ||
      current.status !== "ready" ||
      !current.hasMore ||
      current.nextCursor === null ||
      loadMoreInFlight.current
    ) {
      return;
    }
    loadMoreInFlight.current = true;
    const generation = historyGeneration.current;
    const controller = new AbortController();
    historyController.current = controller;
    setHistory({
      ...current,
      loadMoreStatus: "loading_more",
      loadMoreError: null,
    });
    try {
      const page = await client.listCharacterRevisions({
        characterId,
        expectedProjectId: projectId,
        limit: HISTORY_PAGE_SIZE,
        cursor: current.nextCursor,
        signal: controller.signal,
      });
      if (
        !mounted.current ||
        generation !== historyGeneration.current ||
        controller.signal.aborted
      ) {
        return;
      }
      const ids = new Set(current.items.map((item) => item.revision_id));
      const numbers = new Set(
        current.items.map((item) => item.revision_number),
      );
      if (
        page.character_id !== characterId ||
        page.project_id !== projectId ||
        page.items.some(
          (item) =>
            ids.has(item.revision_id) || numbers.has(item.revision_number),
        ) ||
        (page.items.length > 0 &&
          current.items[current.items.length - 1].revision_number <=
            page.items[0].revision_number)
      ) {
        throw new Error(
          "Character history page did not continue the current sequence.",
        );
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
      const normalized = normalizeCharacterApiError(error);
      if (
        !mounted.current ||
        generation !== historyGeneration.current ||
        controller.signal.aborted ||
        normalized.kind === "aborted"
      ) {
        return;
      }
      setHistory({
        ...current,
        loadMoreStatus: "load_more_error",
        loadMoreError: normalized,
      });
    } finally {
      loadMoreInFlight.current = false;
    }
  }, [characterId, client, projectId, validRoute]);

  const selectRevision = useCallback(
    async (revisionNumber: number): Promise<void> => {
      const current = historyRef.current;
      if (
        !validRoute ||
        current.status !== "ready" ||
        !Number.isSafeInteger(revisionNumber) ||
        revisionNumber < 1
      ) {
        return;
      }
      viewerGeneration.current += 1;
      const generation = viewerGeneration.current;
      viewerController.current?.abort();
      const controller = new AbortController();
      viewerController.current = controller;
      setViewer({ status: "loading_revision", revisionNumber });
      try {
        const revision = await client.getCharacterRevision({
          characterId,
          expectedProjectId: projectId,
          revisionNumber,
          signal: controller.signal,
        });
        if (
          !mounted.current ||
          generation !== viewerGeneration.current ||
          controller.signal.aborted
        ) {
          return;
        }
        setViewer({ status: "ready", revisionNumber, revision });
      } catch (error) {
        const normalized = normalizeCharacterApiError(error);
        if (
          !mounted.current ||
          generation !== viewerGeneration.current ||
          controller.signal.aborted ||
          normalized.kind === "aborted"
        ) {
          return;
        }
        setViewer({
          status: "revision_error",
          revisionNumber,
          error: normalized,
        });
      }
    },
    [characterId, client, projectId, validRoute],
  );

  const retrySelectedRevision = useCallback(async (): Promise<void> => {
    if (viewer.status === "ready" || viewer.status === "revision_error") {
      await selectRevision(viewer.revisionNumber);
    }
  }, [selectRevision, viewer]);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    queueMicrotask(() => {
      if (active) void reload();
    });
    return () => {
      active = false;
      mounted.current = false;
      historyGeneration.current += 1;
      viewerGeneration.current += 1;
      historyController.current?.abort();
      viewerController.current?.abort();
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
