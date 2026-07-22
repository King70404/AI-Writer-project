import { useCallback, useEffect, useRef, useState } from "react";

import { projectApiClient, type ProjectDetailApiClient } from "../api/client";
import type { VersionedProjectResource } from "../api/contracts";
import { normalizeProjectApiError, type ProjectApiError } from "../api/errors";
import { isCanonicalProjectId } from "../api/parsers";

export type ProjectDetailsState =
  | { readonly status: "invalid" }
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly resource: VersionedProjectResource }
  | { readonly status: "not_found"; readonly error: ProjectApiError }
  | { readonly status: "error"; readonly error: ProjectApiError };

export interface ProjectDetailsController {
  readonly state: ProjectDetailsState;
  readonly reload: () => Promise<VersionedProjectResource | null>;
}

export function useProjectDetails(
  projectId: string | undefined,
  client: ProjectDetailApiClient = projectApiClient,
): ProjectDetailsController {
  const validProjectId = isCanonicalProjectId(projectId);
  const [state, setState] = useState<ProjectDetailsState>(
    validProjectId ? { status: "loading" } : { status: "invalid" },
  );
  const generationRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  const reload =
    useCallback(async (): Promise<VersionedProjectResource | null> => {
      if (!validProjectId) {
        setState({ status: "invalid" });
        return null;
      }
      generationRef.current += 1;
      const generation = generationRef.current;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState({ status: "loading" });
      try {
        const resource = await client.getProject(projectId, {
          signal: controller.signal,
        });
        if (
          !mountedRef.current ||
          generation !== generationRef.current ||
          controller.signal.aborted
        ) {
          return null;
        }
        setState({ status: "ready", resource });
        return resource;
      } catch (error) {
        const normalized = normalizeProjectApiError(error);
        if (
          !mountedRef.current ||
          generation !== generationRef.current ||
          controller.signal.aborted ||
          normalized.kind === "aborted"
        ) {
          return null;
        }
        setState(
          normalized.kind === "not_found"
            ? { status: "not_found", error: normalized }
            : { status: "error", error: normalized },
        );
        return null;
      }
    }, [client, projectId, validProjectId]);

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
      controllerRef.current?.abort();
    };
  }, [reload]);

  return { state, reload };
}
