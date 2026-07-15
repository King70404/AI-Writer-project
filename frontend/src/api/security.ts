import { getJson } from "./client";
import type { ApiResponse } from "./types";

const CSRF_HEADER_NAME = "X-CSRF-Token";

export interface LocalSecuritySession {
  readonly csrf_token: string;
  readonly expires_in_seconds: number;
}

let inMemoryCsrfToken: string | null = null;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function decodeLocalSecuritySession(value: unknown): LocalSecuritySession {
  if (
    !isRecord(value) ||
    typeof value.csrf_token !== "string" ||
    value.csrf_token.length < 32 ||
    typeof value.expires_in_seconds !== "number" ||
    !Number.isSafeInteger(value.expires_in_seconds) ||
    value.expires_in_seconds <= 0
  ) {
    throw new Error("Invalid local security session response.");
  }
  return {
    csrf_token: value.csrf_token,
    expires_in_seconds: value.expires_in_seconds,
  };
}

export async function establishLocalSecuritySession(
  signal?: AbortSignal,
): Promise<ApiResponse<LocalSecuritySession>> {
  inMemoryCsrfToken = null;
  const response = await getJson(
    "security/session",
    decodeLocalSecuritySession,
    { signal },
  );
  inMemoryCsrfToken = response.data.csrf_token;
  return response;
}

export function localCsrfHeaders(): Readonly<Record<string, string>> {
  if (inMemoryCsrfToken === null) {
    return {};
  }
  return { [CSRF_HEADER_NAME]: inMemoryCsrfToken };
}

export function clearLocalSecuritySession(): void {
  inMemoryCsrfToken = null;
}
