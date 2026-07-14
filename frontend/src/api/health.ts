import { getJson } from "./client";
import { ApiError } from "./errors";
import type { ApiResponse } from "./types";

export interface LiveHealthResponse {
  readonly status: "ok";
  readonly service: string;
  readonly version: string;
}

export type RequiredHealthCheckStatus = "ok" | "failed";
export type FrontendHealthCheckStatus =
  | RequiredHealthCheckStatus
  | "not_required";

export interface ReadyHealthResponse {
  readonly status: "ready" | "not_ready";
  readonly checks: {
    readonly configuration: RequiredHealthCheckStatus;
    readonly application: RequiredHealthCheckStatus;
    readonly database: RequiredHealthCheckStatus;
    readonly frontend: FrontendHealthCheckStatus;
  };
}

export type BackendNotReadyReason =
  | "configuration"
  | "application"
  | "database"
  | "frontend"
  | "readiness";

export type BackendHealthResult =
  | {
      readonly kind: "ready";
      readonly live: ApiResponse<LiveHealthResponse>;
      readonly ready: ApiResponse<ReadyHealthResponse>;
    }
  | {
      readonly kind: "backend_not_ready";
      readonly reason: BackendNotReadyReason;
      readonly requestId: string | null;
    };

export interface BackendHealthCheckOptions {
  readonly signal?: AbortSignal;
  readonly timeoutMs?: number;
}

const DEFAULT_HEALTH_TIMEOUT_MS = 8_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isRequiredCheck(value: unknown): value is RequiredHealthCheckStatus {
  return value === "ok" || value === "failed";
}

function isFrontendCheck(value: unknown): value is FrontendHealthCheckStatus {
  return isRequiredCheck(value) || value === "not_required";
}

function decodeLiveHealth(value: unknown): LiveHealthResponse {
  if (
    !isRecord(value) ||
    value.status !== "ok" ||
    typeof value.service !== "string" ||
    value.service.trim().length === 0 ||
    typeof value.version !== "string" ||
    value.version.trim().length === 0
  ) {
    throw new Error("Invalid live health response.");
  }

  return {
    status: "ok",
    service: value.service,
    version: value.version,
  };
}

function decodeReadyHealth(value: unknown): ReadyHealthResponse {
  if (
    !isRecord(value) ||
    (value.status !== "ready" && value.status !== "not_ready") ||
    !isRecord(value.checks)
  ) {
    throw new Error("Invalid ready health response.");
  }

  const checks = value.checks;
  const frontend = checks.frontend ?? "not_required";
  if (
    !isRequiredCheck(checks.configuration) ||
    !isRequiredCheck(checks.application) ||
    !isRequiredCheck(checks.database) ||
    !isFrontendCheck(frontend)
  ) {
    throw new Error("Invalid ready health checks.");
  }

  return {
    status: value.status,
    checks: {
      configuration: checks.configuration,
      application: checks.application,
      database: checks.database,
      frontend,
    },
  };
}

export function getLiveHealth(
  signal?: AbortSignal,
): Promise<ApiResponse<LiveHealthResponse>> {
  return getJson("health/live", decodeLiveHealth, { signal });
}

export function getReadyHealth(
  signal?: AbortSignal,
): Promise<ApiResponse<ReadyHealthResponse>> {
  return getJson("health/ready", decodeReadyHealth, {
    signal,
    acceptedStatuses: [503],
  });
}

function notReadyReason(response: ReadyHealthResponse): BackendNotReadyReason {
  if (response.checks.configuration === "failed") {
    return "configuration";
  }
  if (response.checks.application === "failed") {
    return "application";
  }
  if (response.checks.database === "failed") {
    return "database";
  }
  if (response.checks.frontend === "failed") {
    return "frontend";
  }
  return "readiness";
}

export class HealthCheckTimeoutError extends Error {
  public constructor() {
    super("The local backend health check timed out.");
    this.name = "HealthCheckTimeoutError";
  }
}

export async function checkBackendHealth(
  options: BackendHealthCheckOptions = {},
): Promise<BackendHealthResult> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_HEALTH_TIMEOUT_MS;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new RangeError("Health check timeout must be positive.");
  }

  const controller = new AbortController();
  let timedOut = false;
  const forwardAbort = () => controller.abort(options.signal?.reason);

  if (options.signal?.aborted === true) {
    forwardAbort();
  } else {
    options.signal?.addEventListener("abort", forwardAbort, { once: true });
  }

  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const live = await getLiveHealth(controller.signal);
    let ready: ApiResponse<ReadyHealthResponse>;
    try {
      ready = await getReadyHealth(controller.signal);
    } catch (error) {
      if (error instanceof ApiError && !controller.signal.aborted) {
        return {
          kind: "backend_not_ready",
          reason: "readiness",
          requestId: error.requestId ?? live.requestId,
        };
      }
      throw error;
    }

    if (
      ready.data.status === "ready" &&
      ready.data.checks.configuration === "ok" &&
      ready.data.checks.application === "ok" &&
      ready.data.checks.database === "ok" &&
      ready.data.checks.frontend !== "failed"
    ) {
      return { kind: "ready", live, ready };
    }

    return {
      kind: "backend_not_ready",
      reason: notReadyReason(ready.data),
      requestId: ready.requestId ?? live.requestId,
    };
  } catch (error) {
    if (timedOut) {
      throw new HealthCheckTimeoutError();
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    options.signal?.removeEventListener("abort", forwardAbort);
  }
}
