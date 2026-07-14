import type { JsonObject } from "./types";

interface ApiErrorInit {
  readonly status: number;
  readonly code: string;
  readonly message: string;
  readonly details: JsonObject;
  readonly retryable: boolean;
  readonly suggestedAction: string | null;
  readonly requestId: string | null;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly details: JsonObject;
  public readonly retryable: boolean;
  public readonly suggestedAction: string | null;
  public readonly requestId: string | null;

  public constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details;
    this.retryable = init.retryable;
    this.suggestedAction = init.suggestedAction;
    this.requestId = init.requestId;
  }
}
