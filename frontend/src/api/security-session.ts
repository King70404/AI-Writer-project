import { getJson } from "./client";

const EXPIRY_SAFETY_WINDOW_MS = 30_000;

export interface SecurityProof {
  readonly csrfToken: string;
  readonly expiresAtMilliseconds: number;
}

export interface SecuritySessionManager {
  readonly getValidSession: (signal?: AbortSignal) => Promise<SecurityProof>;
  readonly clear: () => void;
}

interface SecuritySessionResponse {
  readonly csrf_token: string;
  readonly expires_in_seconds: number;
}

interface SecuritySessionDependencies {
  readonly now?: () => number;
  readonly requestSession?: (
    signal?: AbortSignal,
  ) => Promise<SecuritySessionResponse>;
}

function isSecuritySessionResponse(
  value: unknown,
): value is SecuritySessionResponse {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record);
  return (
    keys.length === 2 &&
    Object.hasOwn(record, "csrf_token") &&
    Object.hasOwn(record, "expires_in_seconds") &&
    typeof record.csrf_token === "string" &&
    record.csrf_token.length >= 32 &&
    record.csrf_token.length <= 512 &&
    typeof record.expires_in_seconds === "number" &&
    Number.isSafeInteger(record.expires_in_seconds) &&
    record.expires_in_seconds > 0
  );
}

function parseSecuritySession(value: unknown): SecuritySessionResponse {
  if (!isSecuritySessionResponse(value)) {
    throw new Error("Security session response did not match its contract.");
  }
  return value;
}

function requestSecuritySession(signal?: AbortSignal) {
  return getJson("security/session", parseSecuritySession, { signal }).then(
    (response) => response.data,
  );
}

export function createSecuritySessionManager(
  dependencies: SecuritySessionDependencies = {},
): SecuritySessionManager {
  const now = dependencies.now ?? Date.now;
  const requestSession = dependencies.requestSession ?? requestSecuritySession;
  let cached: SecurityProof | null = null;
  let inFlight: Promise<SecurityProof> | null = null;
  let generation = 0;

  const getValidSession = (signal?: AbortSignal): Promise<SecurityProof> => {
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

export const securitySession = createSecuritySessionManager();
