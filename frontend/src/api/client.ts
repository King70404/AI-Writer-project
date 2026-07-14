import { ApiError } from "./errors";
import type {
  ApiResponse,
  BackendErrorEnvelope,
  GetJsonOptions,
  JsonDecoder,
  JsonObject,
} from "./types";

const DEFAULT_API_BASE_URL = "/api/v1";
const REQUEST_ID_HEADER = "X-Request-ID";

function configuredApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  return configured === undefined || configured.length === 0
    ? DEFAULT_API_BASE_URL
    : configured;
}

export const API_BASE_URL = configuredApiBaseUrl();

function isAbsoluteUrl(value: string): boolean {
  return /^[a-z][a-z\d+.-]*:/i.test(value) || value.startsWith("//");
}

export function joinApiPath(baseUrl: string, path: string): string {
  const normalizedBase = baseUrl.trim().replace(/\/+$/, "");
  const normalizedPath = path.trim().replace(/^\/+/, "");

  if (normalizedBase.length === 0) {
    throw new Error("API 基础路径不能为空。");
  }

  if (isAbsoluteUrl(path.trim())) {
    throw new Error("API 请求路径必须是相对路径。");
  }

  const pathWithoutQuery = normalizedPath.split(/[?#]/, 1)[0];
  if (
    pathWithoutQuery
      .split("/")
      .some((segment) => segment === "." || segment === "..")
  ) {
    throw new Error("API 请求路径不能包含相对目录段。");
  }

  if (normalizedPath.length === 0) {
    return normalizedBase;
  }

  return `${normalizedBase}/${normalizedPath}`;
}

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isBackendErrorEnvelope(
  value: unknown,
): value is BackendErrorEnvelope {
  if (!isJsonObject(value) || !isJsonObject(value.error)) {
    return false;
  }

  const error = value.error;
  const suggestedAction = error.suggested_action;

  return (
    typeof error.code === "string" &&
    typeof error.message === "string" &&
    isJsonObject(error.details) &&
    typeof error.retryable === "boolean" &&
    (suggestedAction === null || typeof suggestedAction === "string") &&
    typeof value.request_id === "string"
  );
}

type JsonReadResult =
  | { readonly ok: true; readonly value: unknown }
  | { readonly ok: false };

async function readJson(response: Response): Promise<JsonReadResult> {
  try {
    const value: unknown = await response.json();
    return { ok: true, value };
  } catch {
    return { ok: false };
  }
}

function responseRequestId(response: Response): string | null {
  const requestId = response.headers.get(REQUEST_ID_HEADER)?.trim();
  return requestId === undefined || requestId.length === 0 ? null : requestId;
}

function toApiError(response: Response, parsed: JsonReadResult): ApiError {
  const headerRequestId = responseRequestId(response);

  if (parsed.ok && isBackendErrorEnvelope(parsed.value)) {
    return new ApiError({
      status: response.status,
      code: parsed.value.error.code,
      message: parsed.value.error.message,
      details: parsed.value.error.details,
      retryable: parsed.value.error.retryable,
      suggestedAction: parsed.value.error.suggested_action,
      requestId: headerRequestId ?? parsed.value.request_id,
    });
  }

  return new ApiError({
    status: response.status,
    code: "HTTP_ERROR",
    message: "请求未能完成，请稍后再试。",
    details: {},
    retryable: false,
    suggestedAction: null,
    requestId: headerRequestId,
  });
}

export async function getJson<T>(
  path: string,
  decode: JsonDecoder<T>,
  options: GetJsonOptions = {},
): Promise<ApiResponse<T>> {
  const headers = new Headers(options.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const response = await fetch(joinApiPath(API_BASE_URL, path), {
    method: "GET",
    headers,
    signal: options.signal,
  });

  const parsed = await readJson(response);
  const acceptedStatus =
    options.acceptedStatuses?.includes(response.status) === true;
  if (
    !response.ok &&
    (!acceptedStatus || (parsed.ok && isBackendErrorEnvelope(parsed.value)))
  ) {
    throw toApiError(response, parsed);
  }

  if (!parsed.ok) {
    throw new ApiError({
      status: response.status,
      code: "INVALID_RESPONSE",
      message: "服务返回了无法读取的数据。",
      details: {},
      retryable: false,
      suggestedAction: null,
      requestId: responseRequestId(response),
    });
  }

  const requestId = responseRequestId(response);
  try {
    return {
      data: decode(parsed.value),
      requestId,
    };
  } catch {
    throw new ApiError({
      status: response.status,
      code: "INVALID_RESPONSE",
      message: "服务返回了无法读取的数据。",
      details: {},
      retryable: false,
      suggestedAction: null,
      requestId,
    });
  }
}
