import { useCallback, useEffect, useRef, useState } from "react";

import { projectApiClient, type ProjectApiClient } from "../api/client";
import type { CreateProjectRequest, ProjectResponse } from "../api/contracts";
import { normalizeProjectApiError, type ProjectApiError } from "../api/errors";

export type CreateProjectState =
  | { readonly kind: "idle" }
  | { readonly kind: "submitting" }
  | { readonly kind: "success"; readonly project: ProjectResponse }
  | { readonly kind: "error"; readonly error: ProjectApiError }
  | { readonly kind: "partial_success"; readonly project: ProjectResponse };

export type CreateProjectSubmissionResult =
  | { readonly kind: "success"; readonly project: ProjectResponse }
  | { readonly kind: "partial_success"; readonly project: ProjectResponse }
  | { readonly kind: "error"; readonly error: ProjectApiError }
  | { readonly kind: "ignored" };

export interface CreateProjectController {
  readonly state: CreateProjectState;
  readonly submit: (
    input: CreateProjectRequest,
  ) => Promise<CreateProjectSubmissionResult>;
  readonly dismissFeedback: () => void;
}

export function useCreateProject(
  refreshProjects: () => Promise<boolean>,
  client: ProjectApiClient = projectApiClient,
): CreateProjectController {
  const [state, setState] = useState<CreateProjectState>({ kind: "idle" });
  const submittingRef = useRef(false);
  const mountedRef = useRef(true);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
    };
  }, []);

  const submit = useCallback(
    async (
      input: CreateProjectRequest,
    ): Promise<CreateProjectSubmissionResult> => {
      if (submittingRef.current) {
        return { kind: "ignored" };
      }
      submittingRef.current = true;
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ kind: "submitting" });
      try {
        const project = await client.createProject(input, {
          signal: controller.signal,
        });
        const refreshed = await refreshProjects();
        const result = refreshed
          ? ({ kind: "success", project } as const)
          : ({ kind: "partial_success", project } as const);
        if (mountedRef.current) {
          setState(result);
        }
        return result;
      } catch (error) {
        const result = {
          kind: "error",
          error: normalizeProjectApiError(error),
        } as const;
        if (mountedRef.current) {
          setState(result);
        }
        return result;
      } finally {
        submittingRef.current = false;
        if (controllerRef.current === controller) {
          controllerRef.current = null;
        }
      }
    },
    [client, refreshProjects],
  );

  const dismissFeedback = useCallback((): void => {
    if (state.kind !== "submitting") {
      setState({ kind: "idle" });
    }
  }, [state.kind]);

  return { state, submit, dismissFeedback };
}
