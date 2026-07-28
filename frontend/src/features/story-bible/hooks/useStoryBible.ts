import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { storyBibleApiClient, type StoryBibleApiClient } from "../api/client";
import type { VersionedStoryBibleResource } from "../api/contracts";
import {
  normalizeStoryBibleApiError,
  storyBibleContractError,
  type StoryBibleApiError,
} from "../api/errors";
import { isCanonicalStoryBibleProjectId } from "../api/parsers";

export interface StoryBibleDraft {
  readonly title: string;
  readonly content: string;
}

export type StoryBibleCreateStatusKind =
  | "idle"
  | "submitting"
  | "success"
  | "error"
  | "outcome_unknown"
  | "already_exists";

export interface StoryBibleCreateStatus {
  readonly kind: StoryBibleCreateStatusKind;
  readonly error: StoryBibleApiError | null;
  readonly verifying: boolean;
  readonly verificationError: StoryBibleApiError | null;
}

export interface StoryBibleResolution {
  readonly reason: "conflict" | "outcome_unknown";
  readonly message: string;
  readonly requestId: string | null;
  readonly expectedVersion: number | null;
  readonly actualVersion: number | null;
  readonly oldBaseline: VersionedStoryBibleResource;
  readonly draft: StoryBibleDraft;
  readonly latestStatus: "idle" | "loading" | "ready" | "error";
  readonly latestResource: VersionedStoryBibleResource | null;
  readonly latestError: StoryBibleApiError | null;
}

export type StoryBibleReadyStatus =
  | { readonly kind: "idle" }
  | { readonly kind: "saving" }
  | { readonly kind: "success" }
  | { readonly kind: "save_error"; readonly error: StoryBibleApiError }
  | { readonly kind: "resolution"; readonly resolution: StoryBibleResolution }
  | { readonly kind: "adopted_latest" }
  | { readonly kind: "rebased_draft" }
  | { readonly kind: "discarded_draft" };

export type StoryBiblePageState =
  | { readonly status: "invalid_project" }
  | { readonly status: "loading" }
  | {
      readonly status: "project_not_found";
      readonly error: StoryBibleApiError;
    }
  | {
      readonly status: "create_ready";
      readonly draft: StoryBibleDraft;
      readonly create: StoryBibleCreateStatus;
    }
  | {
      readonly status: "ready";
      readonly baseline: VersionedStoryBibleResource;
      readonly draft: StoryBibleDraft;
      readonly save: StoryBibleReadyStatus;
    }
  | { readonly status: "error"; readonly error: StoryBibleApiError };

export interface StoryBibleController {
  readonly state: StoryBiblePageState;
  readonly dirty: boolean;
  readonly reload: () => Promise<void>;
  readonly setTitle: (value: string) => void;
  readonly setContent: (value: string) => void;
  readonly create: () => Promise<void>;
  readonly verifyCreateResult: () => Promise<void>;
  readonly save: () => Promise<void>;
  readonly discardDraft: () => void;
  readonly loadLatest: () => Promise<void>;
  readonly adoptLatest: () => void;
  readonly keepDraftWithLatestBaseline: () => void;
  readonly dismissFeedback: () => void;
}

const EMPTY_DRAFT: StoryBibleDraft = { title: "", content: "" };
const IDLE_CREATE: StoryBibleCreateStatus = {
  kind: "idle",
  error: null,
  verifying: false,
  verificationError: null,
};

function draftFrom(resource: VersionedStoryBibleResource): StoryBibleDraft {
  return {
    title: resource.storyBible.title,
    content: resource.storyBible.content,
  };
}

function readyState(
  resource: VersionedStoryBibleResource,
): StoryBiblePageState {
  return {
    status: "ready",
    baseline: resource,
    draft: draftFrom(resource),
    save: { kind: "idle" },
  };
}

export function useStoryBible(
  projectId: string | undefined,
  client: StoryBibleApiClient = storyBibleApiClient,
): StoryBibleController {
  const validProjectId = isCanonicalStoryBibleProjectId(projectId);
  const [state, setState] = useState<StoryBiblePageState>(
    validProjectId ? { status: "loading" } : { status: "invalid_project" },
  );
  const stateRef = useRef(state);
  const mountedRef = useRef(true);
  const generationRef = useRef(0);
  const requestControllerRef = useRef<AbortController | null>(null);
  const createInFlightRef = useRef(false);
  const saveInFlightRef = useRef(false);
  const latestInFlightRef = useRef(false);
  const verificationInFlightRef = useRef(false);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const dirty = useMemo(
    () =>
      state.status === "ready" &&
      (state.draft.title !== state.baseline.storyBible.title ||
        state.draft.content !== state.baseline.storyBible.content),
    [state],
  );

  const loadForProject = useCallback(
    async (
      mode: "initial" | "verification",
      preservedDraft: StoryBibleDraft = EMPTY_DRAFT,
    ): Promise<void> => {
      if (!validProjectId) {
        setState({ status: "invalid_project" });
        return;
      }
      generationRef.current += 1;
      const generation = generationRef.current;
      requestControllerRef.current?.abort();
      const controller = new AbortController();
      requestControllerRef.current = controller;
      if (mode === "initial") {
        setState({ status: "loading" });
      }
      try {
        const resource = await client.getStoryBibleForProject({
          projectId,
          signal: controller.signal,
        });
        if (
          mountedRef.current &&
          generation === generationRef.current &&
          !controller.signal.aborted
        ) {
          setState(readyState(resource));
        }
      } catch (error) {
        const normalized = normalizeStoryBibleApiError(error);
        if (
          !mountedRef.current ||
          generation !== generationRef.current ||
          controller.signal.aborted ||
          normalized.kind === "aborted"
        ) {
          return;
        }
        if (normalized.kind === "story_bible_for_project_not_found") {
          setState({
            status: "create_ready",
            draft: preservedDraft,
            create: IDLE_CREATE,
          });
        } else if (normalized.kind === "project_not_found") {
          setState({ status: "project_not_found", error: normalized });
        } else if (mode === "verification") {
          setState((current) =>
            current.status === "create_ready"
              ? {
                  ...current,
                  create: {
                    ...current.create,
                    verifying: false,
                    verificationError: normalized,
                  },
                }
              : current,
          );
        } else {
          setState({ status: "error", error: normalized });
        }
      } finally {
        if (requestControllerRef.current === controller) {
          requestControllerRef.current = null;
        }
      }
    },
    [client, projectId, validProjectId],
  );

  const reload = useCallback(
    async (): Promise<void> => loadForProject("initial"),
    [loadForProject],
  );

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
      generationRef.current += 1;
      requestControllerRef.current?.abort();
    };
  }, [reload]);

  const updateDraft = useCallback(
    (field: keyof StoryBibleDraft, value: string): void => {
      setState((current) => {
        if (current.status === "create_ready") {
          return {
            ...current,
            draft: { ...current.draft, [field]: value },
            create:
              current.create.kind === "error" ||
              current.create.kind === "success"
                ? IDLE_CREATE
                : current.create,
          };
        }
        if (current.status !== "ready") {
          return current;
        }
        return {
          ...current,
          draft: { ...current.draft, [field]: value },
          save:
            current.save.kind === "save_error" ||
            current.save.kind === "success" ||
            current.save.kind === "adopted_latest" ||
            current.save.kind === "rebased_draft" ||
            current.save.kind === "discarded_draft"
              ? { kind: "idle" }
              : current.save,
        };
      });
    },
    [],
  );

  const create = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (
      !validProjectId ||
      current.status !== "create_ready" ||
      createInFlightRef.current ||
      current.create.kind === "outcome_unknown" ||
      current.create.kind === "already_exists"
    ) {
      return;
    }
    createInFlightRef.current = true;
    const lockedDraft = { ...current.draft };
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setState({
      ...current,
      create: {
        kind: "submitting",
        error: null,
        verifying: false,
        verificationError: null,
      },
    });
    try {
      const resource = await client.createStoryBible({
        projectId,
        title: lockedDraft.title,
        content: lockedDraft.content,
        signal: controller.signal,
      });
      if (mountedRef.current) {
        setState(readyState(resource));
      }
    } catch (error) {
      const normalized = normalizeStoryBibleApiError(error);
      if (mountedRef.current) {
        setState({
          status: "create_ready",
          draft: lockedDraft,
          create: {
            kind:
              normalized.kind === "outcome_unknown"
                ? "outcome_unknown"
                : normalized.kind === "already_exists"
                  ? "already_exists"
                  : "error",
            error: normalized,
            verifying: false,
            verificationError: null,
          },
        });
      }
    } finally {
      createInFlightRef.current = false;
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
      }
    }
  }, [client, projectId, validProjectId]);

  const verifyCreateResult = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (
      current.status !== "create_ready" ||
      (current.create.kind !== "outcome_unknown" &&
        current.create.kind !== "already_exists") ||
      verificationInFlightRef.current
    ) {
      return;
    }
    verificationInFlightRef.current = true;
    setState({
      ...current,
      create: {
        ...current.create,
        verifying: true,
        verificationError: null,
      },
    });
    try {
      await loadForProject("verification", current.draft);
    } finally {
      verificationInFlightRef.current = false;
    }
  }, [loadForProject]);

  const save = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (
      current.status !== "ready" ||
      saveInFlightRef.current ||
      current.save.kind === "resolution" ||
      (current.draft.title === current.baseline.storyBible.title &&
        current.draft.content === current.baseline.storyBible.content)
    ) {
      return;
    }
    saveInFlightRef.current = true;
    const lockedBaseline = current.baseline;
    const lockedDraft = { ...current.draft };
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setState({ ...current, save: { kind: "saving" } });
    try {
      const resource = await client.reviseStoryBible({
        storyBibleId: lockedBaseline.storyBible.story_bible_id,
        expectedProjectId: lockedBaseline.storyBible.project_id,
        etag: lockedBaseline.etag,
        title: lockedDraft.title,
        content: lockedDraft.content,
        signal: controller.signal,
      });
      if (
        resource.storyBible.revision_number <=
        lockedBaseline.storyBible.revision_number
      ) {
        throw storyBibleContractError();
      }
      if (mountedRef.current) {
        setState({
          status: "ready",
          baseline: resource,
          draft: draftFrom(resource),
          save: { kind: "success" },
        });
      }
    } catch (error) {
      const normalized = normalizeStoryBibleApiError(error);
      if (!mountedRef.current) {
        return;
      }
      if (normalized.kind === "conflict" && normalized.conflict !== null) {
        setState({
          status: "ready",
          baseline: lockedBaseline,
          draft: lockedDraft,
          save: {
            kind: "resolution",
            resolution: {
              reason: "conflict",
              message: normalized.message,
              requestId: normalized.requestId,
              expectedVersion: normalized.conflict.expectedVersion,
              actualVersion: normalized.conflict.actualVersion,
              oldBaseline: lockedBaseline,
              draft: lockedDraft,
              latestStatus: "idle",
              latestResource: null,
              latestError: null,
            },
          },
        });
      } else if (normalized.kind === "outcome_unknown") {
        setState({
          status: "ready",
          baseline: lockedBaseline,
          draft: lockedDraft,
          save: {
            kind: "resolution",
            resolution: {
              reason: "outcome_unknown",
              message: normalized.message,
              requestId: normalized.requestId,
              expectedVersion: lockedBaseline.version,
              actualVersion: null,
              oldBaseline: lockedBaseline,
              draft: lockedDraft,
              latestStatus: "idle",
              latestResource: null,
              latestError: null,
            },
          },
        });
      } else {
        setState({
          status: "ready",
          baseline: lockedBaseline,
          draft: lockedDraft,
          save: { kind: "save_error", error: normalized },
        });
      }
    } finally {
      saveInFlightRef.current = false;
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
      }
    }
  }, [client]);

  const discardDraft = useCallback((): void => {
    setState((current) =>
      current.status === "ready" &&
      current.save.kind !== "saving" &&
      current.save.kind !== "resolution"
        ? {
            ...current,
            draft: draftFrom(current.baseline),
            save: { kind: "discarded_draft" },
          }
        : current,
    );
  }, []);

  const loadLatest = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (
      current.status !== "ready" ||
      current.save.kind !== "resolution" ||
      latestInFlightRef.current
    ) {
      return;
    }
    latestInFlightRef.current = true;
    const resolution = current.save.resolution;
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setState({
      ...current,
      save: {
        kind: "resolution",
        resolution: {
          ...resolution,
          latestStatus: "loading",
          latestError: null,
        },
      },
    });
    try {
      const resource = await client.getStoryBible({
        storyBibleId: resolution.oldBaseline.storyBible.story_bible_id,
        expectedProjectId: resolution.oldBaseline.storyBible.project_id,
        signal: controller.signal,
      });
      if (
        resolution.actualVersion !== null &&
        resource.version < resolution.actualVersion
      ) {
        throw storyBibleContractError();
      }
      if (mountedRef.current) {
        setState({
          status: "ready",
          baseline: resolution.oldBaseline,
          draft: resolution.draft,
          save: {
            kind: "resolution",
            resolution: {
              ...resolution,
              latestStatus: "ready",
              latestResource: resource,
              latestError: null,
            },
          },
        });
      }
    } catch (error) {
      const normalized = normalizeStoryBibleApiError(error);
      if (
        mountedRef.current &&
        normalized.kind !== "aborted" &&
        !controller.signal.aborted
      ) {
        setState({
          status: "ready",
          baseline: resolution.oldBaseline,
          draft: resolution.draft,
          save: {
            kind: "resolution",
            resolution: {
              ...resolution,
              latestStatus: "error",
              latestResource: null,
              latestError: normalized,
            },
          },
        });
      }
    } finally {
      latestInFlightRef.current = false;
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
      }
    }
  }, [client]);

  const adoptLatest = useCallback((): void => {
    const current = stateRef.current;
    if (
      current.status !== "ready" ||
      current.save.kind !== "resolution" ||
      current.save.resolution.latestResource === null
    ) {
      return;
    }
    const latest = current.save.resolution.latestResource;
    setState({
      status: "ready",
      baseline: latest,
      draft: draftFrom(latest),
      save: { kind: "adopted_latest" },
    });
  }, []);

  const keepDraftWithLatestBaseline = useCallback((): void => {
    const current = stateRef.current;
    if (
      current.status !== "ready" ||
      current.save.kind !== "resolution" ||
      current.save.resolution.latestResource === null
    ) {
      return;
    }
    setState({
      status: "ready",
      baseline: current.save.resolution.latestResource,
      draft: current.save.resolution.draft,
      save: { kind: "rebased_draft" },
    });
  }, []);

  const dismissFeedback = useCallback((): void => {
    setState((current) =>
      current.status === "ready" &&
      current.save.kind !== "saving" &&
      current.save.kind !== "resolution"
        ? { ...current, save: { kind: "idle" } }
        : current,
    );
  }, []);

  return {
    state,
    dirty,
    reload,
    setTitle: (value) => updateDraft("title", value),
    setContent: (value) => updateDraft("content", value),
    create,
    verifyCreateResult,
    save,
    discardDraft,
    loadLatest,
    adoptLatest,
    keepDraftWithLatestBaseline,
    dismissFeedback,
  };
}
