import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { characterApiClient, type CharacterApiClient } from "../api/client";
import type { VersionedCharacterResource } from "../api/contracts";
import {
  normalizeCharacterApiError,
  type CharacterApiError,
  type CharacterVersionConflict,
} from "../api/errors";
import {
  isCanonicalCharacterId,
  isCanonicalCharacterProjectId,
} from "../api/parsers";
import {
  normalizeCharacterName,
  normalizeCharacterProfile,
  normalizeCharacterRole,
} from "../validation";

export interface CharacterDraft {
  readonly name: string;
  readonly role: string;
  readonly profile: string;
}

export interface CharacterEditorBaseline {
  readonly resource: VersionedCharacterResource["character"];
  readonly etag: string;
}

interface Resolution {
  readonly reason: "version_conflict" | "write_outcome_unknown";
  readonly conflict: CharacterVersionConflict | null;
  readonly oldBaseline: CharacterEditorBaseline;
  readonly draft: CharacterDraft;
  readonly latestStatus: "idle" | "loading" | "ready" | "error";
  readonly latest: VersionedCharacterResource | null;
  readonly latestError: CharacterApiError | null;
}

export type CharacterEditorFeedback =
  | { readonly status: "idle" }
  | { readonly status: "saving" }
  | { readonly status: "success" }
  | { readonly status: "error"; readonly error: CharacterApiError }
  | { readonly status: "resolution"; readonly resolution: Resolution }
  | { readonly status: "adopted_latest" }
  | { readonly status: "rebased_draft" }
  | { readonly status: "discarded" };

export type CharacterEditorState =
  | { readonly status: "invalid_route" }
  | { readonly status: "loading" }
  | {
      readonly status: "character_not_found";
      readonly error: CharacterApiError;
    }
  | { readonly status: "project_mismatch" }
  | {
      readonly status: "ready";
      readonly baseline: CharacterEditorBaseline;
      readonly draft: CharacterDraft;
      readonly feedback: CharacterEditorFeedback;
    }
  | { readonly status: "error"; readonly error: CharacterApiError };

export interface CharacterEditorController {
  readonly state: CharacterEditorState;
  readonly dirty: boolean;
  readonly reload: () => Promise<void>;
  readonly setDraftField: (field: keyof CharacterDraft, value: string) => void;
  readonly discard: () => void;
  readonly save: () => Promise<void>;
  readonly loadLatest: () => Promise<void>;
  readonly adoptLatest: () => void;
  readonly keepDraftWithLatestBaseline: () => void;
  readonly dismissFeedback: () => void;
}

function draftFrom(resource: VersionedCharacterResource): CharacterDraft {
  return {
    name: resource.character.name,
    role: resource.character.role,
    profile: resource.character.profile,
  };
}

function ready(resource: VersionedCharacterResource): CharacterEditorState {
  return {
    status: "ready",
    baseline: { resource: resource.character, etag: resource.etag },
    draft: draftFrom(resource),
    feedback: { status: "idle" },
  };
}

export function useCharacterEditor(
  projectId: string | undefined,
  characterId: string | undefined,
  client: CharacterApiClient = characterApiClient,
): CharacterEditorController {
  const valid =
    isCanonicalCharacterProjectId(projectId) &&
    isCanonicalCharacterId(characterId);
  const [state, setState] = useState<CharacterEditorState>(
    valid ? { status: "loading" } : { status: "invalid_route" },
  );
  const stateRef = useRef(state);
  const mounted = useRef(true);
  const generation = useRef(0);
  const request = useRef<AbortController | null>(null);
  const saveLocked = useRef(false);
  const latestLocked = useRef(false);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const dirty = useMemo(() => {
    if (state.status !== "ready") return false;
    return (
      normalizeCharacterName(state.draft.name) !==
        state.baseline.resource.name ||
      normalizeCharacterRole(state.draft.role) !==
        state.baseline.resource.role ||
      normalizeCharacterProfile(state.draft.profile) !==
        state.baseline.resource.profile
    );
  }, [state]);

  const reload = useCallback(async (): Promise<void> => {
    if (!valid) {
      setState({ status: "invalid_route" });
      return;
    }
    generation.current += 1;
    const currentGeneration = generation.current;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setState({ status: "loading" });
    try {
      const resource = await client.getCharacter({
        projectId,
        characterId,
        signal: controller.signal,
      });
      if (
        mounted.current &&
        currentGeneration === generation.current &&
        !controller.signal.aborted
      ) {
        setState(
          resource.character.project_id === projectId
            ? ready(resource)
            : { status: "project_mismatch" },
        );
      }
    } catch (error) {
      const normalized = normalizeCharacterApiError(error);
      if (
        !mounted.current ||
        currentGeneration !== generation.current ||
        controller.signal.aborted ||
        normalized.kind === "aborted"
      )
        return;
      setState(
        normalized.kind === "character_not_found"
          ? { status: "character_not_found", error: normalized }
          : normalized.kind === "contract"
            ? { status: "project_mismatch" }
            : { status: "error", error: normalized },
      );
    } finally {
      if (request.current === controller) request.current = null;
    }
  }, [characterId, client, projectId, valid]);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    queueMicrotask(() => {
      if (active) void reload();
    });
    return () => {
      active = false;
      mounted.current = false;
      generation.current += 1;
      request.current?.abort();
    };
  }, [reload]);

  const save = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (
      current.status !== "ready" ||
      !valid ||
      saveLocked.current ||
      current.feedback.status === "resolution"
    )
      return;
    saveLocked.current = true;
    setState({ ...current, feedback: { status: "saving" } });
    try {
      const resource = await client.reviseCharacter({
        projectId,
        characterId,
        etag: current.baseline.etag,
        name: current.draft.name,
        role: current.draft.role,
        profile: current.draft.profile,
      });
      setState({
        ...(ready(resource) as Extract<
          CharacterEditorState,
          { status: "ready" }
        >),
        feedback: { status: "success" },
      });
    } catch (error) {
      const normalized = normalizeCharacterApiError(error);
      const unchanged = stateRef.current;
      if (unchanged.status !== "ready") return;
      if (
        normalized.kind === "version_conflict" ||
        normalized.kind === "write_outcome_unknown"
      ) {
        setState({
          ...unchanged,
          baseline: current.baseline,
          draft: current.draft,
          feedback: {
            status: "resolution",
            resolution: {
              reason: normalized.kind,
              conflict: normalized.conflict,
              oldBaseline: current.baseline,
              draft: current.draft,
              latestStatus: "idle",
              latest: null,
              latestError: null,
            },
          },
        });
      } else {
        setState({
          ...unchanged,
          baseline: current.baseline,
          draft: current.draft,
          feedback: { status: "error", error: normalized },
        });
      }
    } finally {
      saveLocked.current = false;
    }
  }, [characterId, client, projectId, valid]);

  const loadLatest = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (
      current.status !== "ready" ||
      current.feedback.status !== "resolution" ||
      !valid ||
      latestLocked.current
    )
      return;
    latestLocked.current = true;
    const resolution = current.feedback.resolution;
    setState({
      ...current,
      feedback: {
        status: "resolution",
        resolution: {
          ...resolution,
          latestStatus: "loading",
          latestError: null,
        },
      },
    });
    try {
      const latest = await client.getCharacter({ projectId, characterId });
      if (
        resolution.conflict !== null &&
        latest.version < resolution.conflict.actualVersion
      ) {
        throw new Error("Untrusted Character conflict resolution version.");
      }
      const latestState = stateRef.current;
      if (
        latestState.status === "ready" &&
        latestState.feedback.status === "resolution"
      ) {
        setState({
          ...latestState,
          feedback: {
            status: "resolution",
            resolution: {
              ...latestState.feedback.resolution,
              latestStatus: "ready",
              latest,
              latestError: null,
            },
          },
        });
      }
    } catch (error) {
      const normalized = normalizeCharacterApiError(error);
      setState((latestState) =>
        latestState.status === "ready" &&
        latestState.feedback.status === "resolution"
          ? {
              ...latestState,
              feedback: {
                status: "resolution",
                resolution: {
                  ...latestState.feedback.resolution,
                  latestStatus: "error",
                  latestError: normalized,
                },
              },
            }
          : latestState,
      );
    } finally {
      latestLocked.current = false;
    }
  }, [characterId, client, projectId, valid]);

  const resolve = useCallback((adopt: boolean): void => {
    setState((current) => {
      if (
        current.status !== "ready" ||
        current.feedback.status !== "resolution" ||
        current.feedback.resolution.latestStatus !== "ready" ||
        current.feedback.resolution.latest === null
      )
        return current;
      const latest = current.feedback.resolution.latest;
      return {
        status: "ready",
        baseline: { resource: latest.character, etag: latest.etag },
        draft: adopt ? draftFrom(latest) : current.feedback.resolution.draft,
        feedback: {
          status: adopt ? "adopted_latest" : "rebased_draft",
        },
      };
    });
  }, []);

  return {
    state,
    dirty,
    reload,
    setDraftField(field, value) {
      setState((current) =>
        current.status === "ready"
          ? {
              ...current,
              draft: { ...current.draft, [field]: value },
              feedback:
                current.feedback.status === "error" ||
                current.feedback.status === "success" ||
                current.feedback.status === "discarded"
                  ? { status: "idle" }
                  : current.feedback,
            }
          : current,
      );
    },
    discard() {
      setState((current) =>
        current.status === "ready" && current.feedback.status !== "resolution"
          ? {
              ...current,
              draft: {
                name: current.baseline.resource.name,
                role: current.baseline.resource.role,
                profile: current.baseline.resource.profile,
              },
              feedback: { status: "discarded" },
            }
          : current,
      );
    },
    save,
    loadLatest,
    adoptLatest() {
      resolve(true);
    },
    keepDraftWithLatestBaseline() {
      resolve(false);
    },
    dismissFeedback() {
      setState((current) =>
        current.status === "ready" && current.feedback.status !== "resolution"
          ? { ...current, feedback: { status: "idle" } }
          : current,
      );
    },
  };
}
