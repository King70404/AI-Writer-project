import { useCallback, useEffect, useRef, useState } from "react";

import { characterApiClient, type CharacterApiClient } from "../api/client";
import type { CharacterListItemResponse } from "../api/contracts";
import { CharacterApiError, normalizeCharacterApiError } from "../api/errors";
import {
  characterItemsAreDescending,
  characterListItemFromResponse,
  isCanonicalCharacterProjectId,
} from "../api/parsers";

export interface CharacterDraft {
  readonly name: string;
  readonly role: string;
  readonly profile: string;
}

export type CharacterListState =
  | { readonly status: "invalid_project" }
  | { readonly status: "loading" }
  | {
      readonly status: "project_not_found";
      readonly error: CharacterApiError;
    }
  | {
      readonly status: "ready" | "empty";
      readonly items: readonly CharacterListItemResponse[];
      readonly cursor: string | null;
      readonly hasMore: boolean;
      readonly loadingMore: boolean;
      readonly listError: CharacterApiError | null;
    }
  | { readonly status: "error"; readonly error: CharacterApiError };

export type CharacterCreateState =
  | { readonly status: "idle" }
  | { readonly status: "submitting" }
  | {
      readonly status: "success";
      readonly characterId: string;
    }
  | { readonly status: "error"; readonly error: CharacterApiError }
  | {
      readonly status: "outcome_unknown";
      readonly error: CharacterApiError;
      readonly resubmitConfirmed: boolean;
    };

export interface CharacterListController {
  readonly state: CharacterListState;
  readonly draft: CharacterDraft;
  readonly createState: CharacterCreateState;
  readonly setDraftField: (field: keyof CharacterDraft, value: string) => void;
  readonly reloadFirstPage: () => Promise<void>;
  readonly loadMore: () => Promise<void>;
  readonly create: () => Promise<void>;
  readonly confirmResubmit: () => void;
  readonly dismissCreateFeedback: () => void;
}

const EMPTY_DRAFT: CharacterDraft = { name: "", role: "", profile: "" };

function readyState(
  items: readonly CharacterListItemResponse[],
  cursor: string | null,
  hasMore: boolean,
): CharacterListState {
  return {
    status: items.length === 0 ? "empty" : "ready",
    items,
    cursor,
    hasMore,
    loadingMore: false,
    listError: null,
  };
}

export function useCharacterList(
  projectId: string | undefined,
  client: CharacterApiClient = characterApiClient,
): CharacterListController {
  const valid = isCanonicalCharacterProjectId(projectId);
  const [state, setState] = useState<CharacterListState>(
    valid ? { status: "loading" } : { status: "invalid_project" },
  );
  const [draft, setDraft] = useState<CharacterDraft>(EMPTY_DRAFT);
  const [createState, setCreateState] = useState<CharacterCreateState>({
    status: "idle",
  });
  const mounted = useRef(true);
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const createLocked = useRef(false);
  const moreLocked = useRef(false);
  const stateRef = useRef(state);
  const draftRef = useRef(draft);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);
  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  const reloadFirstPage = useCallback(async (): Promise<void> => {
    if (!valid) {
      setState({ status: "invalid_project" });
      return;
    }
    generation.current += 1;
    const requestGeneration = generation.current;
    controller.current?.abort();
    const requestController = new AbortController();
    controller.current = requestController;
    setState({ status: "loading" });
    try {
      const page = await client.listCharacters({
        projectId,
        limit: 20,
        signal: requestController.signal,
      });
      if (
        mounted.current &&
        requestGeneration === generation.current &&
        !requestController.signal.aborted
      ) {
        setState(readyState(page.items, page.next_cursor, page.has_more));
      }
    } catch (error) {
      const normalized = normalizeCharacterApiError(error);
      if (
        !mounted.current ||
        requestGeneration !== generation.current ||
        requestController.signal.aborted ||
        normalized.kind === "aborted"
      )
        return;
      setState(
        normalized.kind === "project_not_found"
          ? { status: "project_not_found", error: normalized }
          : { status: "error", error: normalized },
      );
    } finally {
      if (controller.current === requestController) controller.current = null;
    }
  }, [client, projectId, valid]);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    queueMicrotask(() => {
      if (active) void reloadFirstPage();
    });
    return () => {
      active = false;
      mounted.current = false;
      generation.current += 1;
      controller.current?.abort();
    };
  }, [reloadFirstPage]);

  const loadMore = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (
      !valid ||
      (current.status !== "ready" && current.status !== "empty") ||
      !current.hasMore ||
      current.cursor === null ||
      moreLocked.current
    )
      return;
    moreLocked.current = true;
    const cursor = current.cursor;
    setState((value) =>
      value.status === "ready" || value.status === "empty"
        ? { ...value, loadingMore: true, listError: null }
        : value,
    );
    try {
      const page = await client.listCharacters({
        projectId,
        limit: 20,
        cursor,
      });
      const latest = stateRef.current;
      if (latest.status !== "ready" && latest.status !== "empty") return;
      const merged = [...latest.items, ...page.items];
      if (
        new Set(merged.map((item) => item.character_id)).size !==
          merged.length ||
        !characterItemsAreDescending(merged)
      ) {
        throw new CharacterApiError({
          kind: "contract",
          code: "CHARACTER_LIST_MERGE_CONTRACT_ERROR",
          message: "角色列表分页结果无法安全合并。",
        });
      }
      setState(readyState(merged, page.next_cursor, page.has_more));
    } catch (error) {
      const normalized = normalizeCharacterApiError(error);
      if (normalized.kind !== "aborted") {
        setState((value) =>
          value.status === "ready" || value.status === "empty"
            ? {
                ...value,
                loadingMore: false,
                listError: normalized,
              }
            : value,
        );
      }
    } finally {
      moreLocked.current = false;
    }
  }, [client, projectId, valid]);

  const create = useCallback(async (): Promise<void> => {
    const list = stateRef.current;
    const currentCreate = createState;
    if (
      !valid ||
      (list.status !== "ready" && list.status !== "empty") ||
      createLocked.current ||
      currentCreate.status === "submitting" ||
      (currentCreate.status === "outcome_unknown" &&
        !currentCreate.resubmitConfirmed)
    )
      return;
    createLocked.current = true;
    setCreateState({ status: "submitting" });
    const submitted = draftRef.current;
    try {
      const resource = await client.createCharacter({
        projectId,
        name: submitted.name,
        role: submitted.role,
        profile: submitted.profile,
      });
      const item = characterListItemFromResponse(resource.character);
      const latest = stateRef.current;
      if (latest.status !== "ready" && latest.status !== "empty") return;
      const items = [item, ...latest.items];
      if (
        new Set(items.map((candidate) => candidate.character_id)).size !==
          items.length ||
        !characterItemsAreDescending(items)
      ) {
        throw new CharacterApiError({
          kind: "contract",
          code: "CHARACTER_CREATE_SORT_CONTRACT_ERROR",
          message: "新角色的排序结果无法安全加入当前列表。",
        });
      }
      setState(readyState(items, latest.cursor, latest.hasMore));
      setDraft(EMPTY_DRAFT);
      setCreateState({
        status: "success",
        characterId: resource.character.character_id,
      });
    } catch (error) {
      const normalized = normalizeCharacterApiError(error);
      setCreateState(
        normalized.kind === "write_outcome_unknown"
          ? {
              status: "outcome_unknown",
              error: normalized,
              resubmitConfirmed: false,
            }
          : { status: "error", error: normalized },
      );
    } finally {
      createLocked.current = false;
    }
  }, [client, createState, projectId, valid]);

  return {
    state,
    draft,
    createState,
    setDraftField(field, value) {
      setDraft((current) => ({ ...current, [field]: value }));
      if (createState.status === "error" || createState.status === "success")
        setCreateState({ status: "idle" });
    },
    reloadFirstPage,
    loadMore,
    create,
    confirmResubmit() {
      setCreateState((current) =>
        current.status === "outcome_unknown"
          ? { ...current, resubmitConfirmed: true }
          : current,
      );
    },
    dismissCreateFeedback() {
      if (createState.status !== "outcome_unknown")
        setCreateState({ status: "idle" });
    },
  };
}
