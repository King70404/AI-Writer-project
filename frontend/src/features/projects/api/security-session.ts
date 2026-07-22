import { getJson } from "../../../api/client";

import { parseSecuritySessionResponse } from "./parsers";

const EXPIRY_SAFETY_WINDOW_MS = 30_000;

export interface ProjectSecurityProof {
  readonly csrfToken: string;
  readonly expiresAtMilliseconds: number;
}

export interface ProjectSecuritySessionManager {
  readonly getValidSession: (
    signal?: AbortSignal,
  ) => Promise<ProjectSecurityProof>;
  readonly clear: () => void;
}

interface ProjectSecuritySessionDependencies {
  readonly now?: () => number;
  readonly requestSession?: (signal?: AbortSignal) => Promise<{
    readonly csrf_token: string;
    readonly expires_in_seconds: number;
  }>;
}

function requestSecuritySession(signal?: AbortSignal) {
  return getJson("security/session", parseSecuritySessionResponse, {
    signal,
  }).then((response) => response.data);
}

export function createProjectSecuritySessionManager(
  dependencies: ProjectSecuritySessionDependencies = {},
): ProjectSecuritySessionManager {
  const now = dependencies.now ?? Date.now;
  const requestSession = dependencies.requestSession ?? requestSecuritySession;
  let cached: ProjectSecurityProof | null = null;
  let inFlight: Promise<ProjectSecurityProof> | null = null;
  let generation = 0;

  const getValidSession = (
    signal?: AbortSignal,
  ): Promise<ProjectSecurityProof> => {
    const currentTime = now();
    if (
      cached !== null &&
      cached.expiresAtMilliseconds - currentTime > EXPIRY_SAFETY_WINDOW_MS
    ) {
      return Promise.resolve(cached);
    }
    cached = null;
    if (inFlight !== null) {
      return inFlight;
    }
    const requestGeneration = generation;
    const request = requestSession(signal)
      .then((session) => {
        const proof = {
          csrfToken: session.csrf_token,
          expiresAtMilliseconds: now() + session.expires_in_seconds * 1_000,
        };
        if (generation === requestGeneration) {
          cached = proof;
        }
        return proof;
      })
      .finally(() => {
        if (inFlight === request) {
          inFlight = null;
        }
      });
    inFlight = request;
    return request;
  };

  const clear = (): void => {
    generation += 1;
    cached = null;
    inFlight = null;
  };

  return { getValidSession, clear };
}

export const projectSecuritySession = createProjectSecuritySessionManager();
