import { useCallback, useEffect, useRef, useState } from "react";

import { projectApiClient, type ProjectApiClient } from "../api/client";
import type { ProjectListItemResponse } from "../api/contracts";
import {
  duplicateProjectContractError,
  normalizeProjectApiError,
  type ProjectApiError,
} from "../api/errors";
import { PROJECT_LIST_PAGE_SIZE } from "../constants";

export interface ProjectListState {
  readonly status: "loading" | "ready" | "error";
  readonly items: readonly ProjectListItemResponse[];
  readonly hasMore: boolean;
  readonly nextCursor: string | null;
  readonly error: ProjectApiError | null;
  readonly loadMoreStatus: "idle" | "loading" | "error";
  readonly loadMoreError: ProjectApiError | null;
}

const initialState: ProjectListState = {
  status: "loading",
  items: [],
  hasMore: false,
  nextCursor: null,
  error: null,
  loadMoreStatus: "idle",
  loadMoreError: null,
};

export interface ProjectListController extends ProjectListState {
  readonly reload: () => Promise<boolean>;
  readonly loadMore: () => Promise<void>;
}

export function useProjectList(
  client: ProjectApiClient = projectApiClient,
): ProjectListController {
  const [state, setState] = useState<ProjectListState>(initialState);
  const stateRef = useRef(state);
  const generationRef = useRef(0);
  const activeControllerRef = useRef<AbortController | null>(null);
  const loadMoreInFlightRef = useRef(false);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const reload = useCallback(async (): Promise<boolean> => {
    generationRef.current += 1;
    const generation = generationRef.current;
    activeControllerRef.current?.abort();
    loadMoreInFlightRef.current = false;
    const controller = new AbortController();
    activeControllerRef.current = controller;
    setState(initialState);
    try {
      const page = await client.listProjects({
        limit: PROJECT_LIST_PAGE_SIZE,
        signal: controller.signal,
      });
      if (generation !== generationRef.current || controller.signal.aborted) {
        return false;
      }
      setState({
        status: "ready",
        items: page.items,
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
        generation !== generationRef.current ||
        controller.signal.aborted ||
        normalized.kind === "aborted"
      ) {
        return false;
      }
      setState({
        status: "error",
        items: [],
        hasMore: false,
        nextCursor: null,
        error: normalized,
        loadMoreStatus: "idle",
        loadMoreError: null,
      });
      return false;
    }
  }, [client]);

  const loadMore = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (
      current.status !== "ready" ||
      loadMoreInFlightRef.current ||
      current.loadMoreStatus === "loading" ||
      !current.hasMore ||
      current.nextCursor === null
    ) {
      return;
    }
    loadMoreInFlightRef.current = true;
    const cursor = current.nextCursor;
    const generation = generationRef.current;
    const controller = new AbortController();
    activeControllerRef.current = controller;
    setState({ ...current, loadMoreStatus: "loading", loadMoreError: null });
    try {
      const page = await client.listProjects({
        limit: PROJECT_LIST_PAGE_SIZE,
        cursor,
        signal: controller.signal,
      });
      if (generation !== generationRef.current || controller.signal.aborted) {
        return;
      }
      const existingIds = new Set(current.items.map((item) => item.project_id));
      if (page.items.some((item) => existingIds.has(item.project_id))) {
        throw duplicateProjectContractError();
      }
      setState({
        status: "ready",
        items: [...current.items, ...page.items],
        hasMore: page.has_more,
        nextCursor: page.next_cursor,
        error: null,
        loadMoreStatus: "idle",
        loadMoreError: null,
      });
    } catch (error) {
      const normalized = normalizeProjectApiError(error);
      if (
        generation !== generationRef.current ||
        controller.signal.aborted ||
        normalized.kind === "aborted"
      ) {
        return;
      }
      setState({
        ...current,
        loadMoreStatus: "error",
        loadMoreError: normalized,
      });
    } finally {
      loadMoreInFlightRef.current = false;
    }
  }, [client]);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) {
        void reload();
      }
    });
    return () => {
      active = false;
      generationRef.current += 1;
      activeControllerRef.current?.abort();
    };
  }, [reload]);

  return { ...state, reload, loadMore };
}
