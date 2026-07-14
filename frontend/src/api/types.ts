export type JsonObject = Readonly<Record<string, unknown>>;

export interface BackendErrorEnvelope {
  readonly error: {
    readonly code: string;
    readonly message: string;
    readonly details: JsonObject;
    readonly retryable: boolean;
    readonly suggested_action: string | null;
  };
  readonly request_id: string;
}

export interface ApiResponse<T> {
  readonly data: T;
  readonly requestId: string | null;
}

export type JsonDecoder<T> = (value: unknown) => T;

export interface GetJsonOptions {
  readonly headers?: HeadersInit;
  readonly signal?: AbortSignal;
}
