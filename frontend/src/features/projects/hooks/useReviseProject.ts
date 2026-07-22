import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  projectApiClient,
  type ProjectDetailApiClient,
  type ProjectRevisionApiClient,
} from "../api/client";
import type { VersionedProjectResource } from "../api/contracts";
import {
  normalizeProjectApiError,
  projectRevisionContractError,
  type ProjectApiError,
  type ProjectConflictDetails,
} from "../api/errors";

export interface ProjectDraft {
  readonly title: string;
  readonly description: string;
}

export interface ProjectRevisionConflict extends ProjectConflictDetails {
  readonly requestId: string | null;
  readonly originalBaseline: VersionedProjectResource;
  readonly draft: ProjectDraft;
  readonly latestStatus: "idle" | "loading" | "ready" | "error";
  readonly latestResource: VersionedProjectResource | null;
  readonly latestError: ProjectApiError | null;
}

export type ReviseProjectState =
  | { readonly kind: "idle" }
  | { readonly kind: "saving" }
  | { readonly kind: "success" }
  | { readonly kind: "save_error"; readonly error: ProjectApiError }
  | { readonly kind: "outcome_unknown"; readonly error: ProjectApiError }
  | { readonly kind: "conflict"; readonly conflict: ProjectRevisionConflict }
  | { readonly kind: "adopted_latest" }
  | { readonly kind: "rebased_draft" };

export type ReviseProjectSubmissionResult =
  | { readonly kind: "success" }
  | { readonly kind: "error"; readonly error: ProjectApiError }
  | { readonly kind: "outcome_unknown"; readonly error: ProjectApiError }
  | { readonly kind: "conflict"; readonly error: ProjectApiError }
  | { readonly kind: "ignored" };

export interface ReviseProjectController {
  readonly baseline: VersionedProjectResource;
  readonly draft: ProjectDraft;
  readonly dirty: boolean;
  readonly state: ReviseProjectState;
  readonly setTitle: (value: string) => void;
  readonly setDescription: (value: string) => void;
  readonly save: () => Promise<ReviseProjectSubmissionResult>;
  readonly loadLatest: () => Promise<void>;
  readonly adoptLatest: () => void;
  readonly keepDraftWithLatestBaseline: () => void;
  readonly dismissFeedback: () => void;
}

function draftFrom(resource: VersionedProjectResource): ProjectDraft {
  return {
    title: resource.project.title,
    description: resource.project.description,
  };
}

export function useReviseProject(
  initialResource: VersionedProjectResource,
  client: ProjectDetailApiClient & ProjectRevisionApiClient = projectApiClient,
): ReviseProjectController {
  const [baseline, setBaseline] = useState(initialResource);
  const [draft, setDraft] = useState<ProjectDraft>(() =>
    draftFrom(initialResource),
  );
  const [state, setState] = useState<ReviseProjectState>({ kind: "idle" });
  const stateRef = useRef(state);
  const savingRef = useRef(false);
  const latestLoadingRef = useRef(false);
  const mountedRef = useRef(true);
  const requestControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestControllerRef.current?.abort();
    };
  }, []);

  const dirty = useMemo(
    () =>
      draft.title !== baseline.project.title ||
      draft.description !== baseline.project.description,
    [baseline.project.description, baseline.project.title, draft],
  );

  const updateDraft = useCallback(
    (field: keyof ProjectDraft, value: string): void => {
      setDraft((current) => ({ ...current, [field]: value }));
      setState((current) =>
        current.kind === "save_error" ||
        current.kind === "success" ||
        current.kind === "adopted_latest" ||
        current.kind === "rebased_draft"
          ? { kind: "idle" }
          : current,
      );
    },
    [],
  );

  const save = useCallback(async (): Promise<ReviseProjectSubmissionResult> => {
    if (
      savingRef.current ||
      !dirty ||
      stateRef.current.kind === "conflict" ||
      stateRef.current.kind === "outcome_unknown"
    ) {
      return { kind: "ignored" };
    }
    savingRef.current = true;
    const lockedBaseline = baseline;
    const lockedDraft = { ...draft };
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setState({ kind: "saving" });
    try {
      const resource = await client.reviseProject(
        {
          projectId: lockedBaseline.project.project_id,
          etag: lockedBaseline.etag,
          title: lockedDraft.title,
          description: lockedDraft.description,
        },
        { signal: controller.signal },
      );
      if (
        resource.project.revision_number <=
        lockedBaseline.project.revision_number
      ) {
        throw projectRevisionContractError();
      }
      if (mountedRef.current) {
        setBaseline(resource);
        setDraft(draftFrom(resource));
        setState({ kind: "success" });
      }
      return { kind: "success" };
    } catch (error) {
      const normalized = normalizeProjectApiError(error);
      if (normalized.kind === "outcome_unknown") {
        if (mountedRef.current) {
          setState({ kind: "outcome_unknown", error: normalized });
        }
        return { kind: "outcome_unknown", error: normalized };
      }
      if (normalized.kind === "conflict" && normalized.conflict !== null) {
        const conflict: ProjectRevisionConflict = {
          ...normalized.conflict,
          requestId: normalized.requestId,
          originalBaseline: lockedBaseline,
          draft: lockedDraft,
          latestStatus: "idle",
          latestResource: null,
          latestError: null,
        };
        if (mountedRef.current) {
          setState({ kind: "conflict", conflict });
        }
        return { kind: "conflict", error: normalized };
      }
      if (mountedRef.current) {
        setState({ kind: "save_error", error: normalized });
      }
      return { kind: "error", error: normalized };
    } finally {
      savingRef.current = false;
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
      }
    }
  }, [baseline, client, dirty, draft]);

  const loadLatest = useCallback(async (): Promise<void> => {
    const current = stateRef.current;
    if (current.kind !== "conflict" || latestLoadingRef.current) {
      return;
    }
    latestLoadingRef.current = true;
    const conflict = current.conflict;
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setState({
      kind: "conflict",
      conflict: {
        ...conflict,
        latestStatus: "loading",
        latestError: null,
      },
    });
    try {
      const resource = await client.getProject(
        conflict.originalBaseline.project.project_id,
        { signal: controller.signal },
      );
      if (resource.version < conflict.actualVersion) {
        throw projectRevisionContractError();
      }
      if (mountedRef.current) {
        setState({
          kind: "conflict",
          conflict: {
            ...conflict,
            latestStatus: "ready",
            latestResource: resource,
            latestError: null,
          },
        });
      }
    } catch (error) {
      const normalized = normalizeProjectApiError(error);
      if (
        mountedRef.current &&
        normalized.kind !== "aborted" &&
        !controller.signal.aborted
      ) {
        setState({
          kind: "conflict",
          conflict: {
            ...conflict,
            latestStatus: "error",
            latestResource: null,
            latestError: normalized,
          },
        });
      }
    } finally {
      latestLoadingRef.current = false;
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
      }
    }
  }, [client]);

  const adoptLatest = useCallback((): void => {
    const current = stateRef.current;
    if (
      current.kind !== "conflict" ||
      current.conflict.latestResource === null
    ) {
      return;
    }
    const latest = current.conflict.latestResource;
    setBaseline(latest);
    setDraft(draftFrom(latest));
    setState({ kind: "adopted_latest" });
  }, []);

  const keepDraftWithLatestBaseline = useCallback((): void => {
    const current = stateRef.current;
    if (
      current.kind !== "conflict" ||
      current.conflict.latestResource === null
    ) {
      return;
    }
    setBaseline(current.conflict.latestResource);
    setDraft(current.conflict.draft);
    setState({ kind: "rebased_draft" });
  }, []);

  const dismissFeedback = useCallback((): void => {
    setState((current) =>
      current.kind === "saving" ||
      current.kind === "conflict" ||
      current.kind === "outcome_unknown"
        ? current
        : { kind: "idle" },
    );
  }, []);

  return {
    baseline,
    draft,
    dirty,
    state,
    setTitle: (value) => updateDraft("title", value),
    setDescription: (value) => updateDraft("description", value),
    save,
    loadLatest,
    adoptLatest,
    keepDraftWithLatestBaseline,
    dismissFeedback,
  };
}
