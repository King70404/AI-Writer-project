import { ApiError } from "../../../api/errors";
import type { StoryBibleFieldError, StoryBibleFieldName } from "../validation";

import { StoryBibleContractError } from "./parsers";

export type StoryBibleApiErrorKind =
  | "network"
  | "aborted"
  | "validation"
  | "security"
  | "project_not_found"
  | "story_bible_not_found"
  | "story_bible_for_project_not_found"
  | "already_exists"
  | "conflict"
  | "unavailable"
  | "contract"
  | "outcome_unknown"
  | "unknown";

export interface StoryBibleConflictDetails {
  readonly expectedVersion: number;
  readonly actualVersion: number;
}

interface StoryBibleApiErrorInit {
  readonly kind: StoryBibleApiErrorKind;
  readonly code: string;
  readonly message: string;
  readonly requestId?: string | null;
  readonly fieldErrors?: readonly StoryBibleFieldError[];
  readonly conflict?: StoryBibleConflictDetails | null;
}

export class StoryBibleApiError extends Error {
  public readonly kind: StoryBibleApiErrorKind;
  public readonly code: string;
  public readonly requestId: string | null;
  public readonly fieldErrors: readonly StoryBibleFieldError[];
  public readonly conflict: StoryBibleConflictDetails | null;

  public constructor(init: StoryBibleApiErrorInit) {
    super(init.message);
    this.name = "StoryBibleApiError";
    this.kind = init.kind;
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.fieldErrors = init.fieldErrors ?? [];
    this.conflict = init.conflict ?? null;
  }
}

const REQUEST_ID = /^[A-Za-z0-9._:-]{1,128}$/u;
const SECURITY_CODES = new Set([
  "SESSION_REQUIRED",
  "SESSION_EXPIRED",
  "CSRF_TOKEN_REQUIRED",
  "CSRF_TOKEN_INVALID",
  "ORIGIN_NOT_ALLOWED",
]);

function safeRequestId(value: string | null): string | null {
  return value !== null && REQUEST_ID.test(value) ? value : null;
}

function normalizeField(value: unknown): StoryBibleFieldName | null {
  return value === "title" || value === "body.title"
    ? "title"
    : value === "content" || value === "body.content"
      ? "content"
      : null;
}

function fixedFieldError(field: StoryBibleFieldName): StoryBibleFieldError {
  return {
    field,
    message:
      field === "title"
        ? "Story Bible标题未通过服务端验证。"
        : "Story Bible正文未通过服务端验证。",
  };
}

function fieldErrors(
  details: Readonly<Record<string, unknown>>,
): StoryBibleFieldError[] {
  const result: StoryBibleFieldError[] = [];
  const add = (candidate: unknown): void => {
    const field = normalizeField(candidate);
    if (field !== null && !result.some((item) => item.field === field)) {
      result.push(fixedFieldError(field));
    }
  };
  add(details.field);
  if (Array.isArray(details.errors)) {
    for (const error of details.errors) {
      if (
        typeof error === "object" &&
        error !== null &&
        !Array.isArray(error)
      ) {
        add((error as Record<string, unknown>).field);
      }
    }
  }
  return result;
}

function contractError(requestId: string | null = null): StoryBibleApiError {
  return new StoryBibleApiError({
    kind: "contract",
    code: "STORY_BIBLE_API_CONTRACT_ERROR",
    message: "Story Bible服务返回了无法安全读取的数据。",
    requestId,
  });
}

function isSafePositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function normalizeVersionConflict(
  error: ApiError,
  submittedVersion: number | undefined,
): StoryBibleApiError {
  const details = error.details;
  const keys = Object.keys(details);
  if (
    error.code !== "STORY_BIBLE_VERSION_CONFLICT" ||
    submittedVersion === undefined ||
    keys.length !== 2 ||
    !Object.hasOwn(details, "expected_version") ||
    !Object.hasOwn(details, "actual_version") ||
    !isSafePositiveInteger(details.expected_version) ||
    !isSafePositiveInteger(details.actual_version) ||
    details.expected_version !== submittedVersion ||
    details.actual_version === submittedVersion
  ) {
    return contractError(safeRequestId(error.requestId));
  }
  return new StoryBibleApiError({
    kind: "conflict",
    code: error.code,
    message:
      "Story Bible已被其他操作修订。草稿已保留，请读取最新版本后选择处理方式。",
    requestId: safeRequestId(error.requestId),
    conflict: {
      expectedVersion: details.expected_version,
      actualVersion: details.actual_version,
    },
  });
}

function apiErrorKind(error: ApiError): StoryBibleApiErrorKind {
  if (
    SECURITY_CODES.has(error.code) ||
    error.status === 401 ||
    error.status === 403
  ) {
    return "security";
  }
  if (error.code === "PROJECT_NOT_FOUND") {
    return "project_not_found";
  }
  if (error.code === "STORY_BIBLE_NOT_FOUND") {
    return "story_bible_not_found";
  }
  if (error.code === "STORY_BIBLE_FOR_PROJECT_NOT_FOUND") {
    return "story_bible_for_project_not_found";
  }
  if (error.code === "STORY_BIBLE_ALREADY_EXISTS_FOR_PROJECT") {
    return "already_exists";
  }
  if (
    error.status === 413 ||
    error.status === 422 ||
    error.code.startsWith("INVALID_STORY_BIBLE_") ||
    error.code === "INVALID_PROJECT_ID"
  ) {
    return "validation";
  }
  if (error.status === 503) {
    return "unavailable";
  }
  if (
    error.status === 415 ||
    error.status === 428 ||
    error.code === "INVALID_RESPONSE"
  ) {
    return "contract";
  }
  return "unknown";
}

function safeMessage(kind: StoryBibleApiErrorKind, code: string): string {
  if (kind === "security") {
    return code === "ORIGIN_NOT_ALLOWED"
      ? "当前页面来源未通过安全验证。"
      : "安全会话无效，请检查后手动重新提交。";
  }
  if (kind === "project_not_found") {
    return "指定项目不存在。";
  }
  if (kind === "story_bible_not_found") {
    return "指定Story Bible不存在。";
  }
  if (kind === "story_bible_for_project_not_found") {
    return "该项目尚未创建Story Bible。";
  }
  if (kind === "already_exists") {
    return "该项目已经存在 Story Bible，请重新读取。";
  }
  if (kind === "validation") {
    return code === "REQUEST_TOO_LARGE"
      ? "提交内容超过服务允许的大小。"
      : "Story Bible内容未通过服务端验证。";
  }
  if (kind === "unavailable") {
    return "Story Bible服务暂时不可用，请稍后手动重试。";
  }
  if (kind === "contract") {
    return "Story Bible服务返回了无法安全读取的数据。";
  }
  return "Story Bible请求未能完成，请稍后手动重试。";
}

export function normalizeStoryBibleApiError(
  error: unknown,
  submittedVersion?: number,
): StoryBibleApiError {
  if (error instanceof StoryBibleApiError) {
    return error;
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return new StoryBibleApiError({
      kind: "aborted",
      code: "REQUEST_ABORTED",
      message: "请求已取消。",
    });
  }
  if (error instanceof StoryBibleContractError) {
    return contractError();
  }
  if (error instanceof ApiError) {
    if (error.status === 412) {
      return normalizeVersionConflict(error, submittedVersion);
    }
    const kind = apiErrorKind(error);
    return new StoryBibleApiError({
      kind,
      code: error.code,
      message: safeMessage(kind, error.code),
      requestId: safeRequestId(error.requestId),
      fieldErrors: kind === "validation" ? fieldErrors(error.details) : [],
    });
  }
  if (error instanceof TypeError) {
    return new StoryBibleApiError({
      kind: "network",
      code: "NETWORK_ERROR",
      message: "无法连接本地Story Bible服务，请检查后手动重试。",
    });
  }
  return new StoryBibleApiError({
    kind: "unknown",
    code: "UNKNOWN_STORY_BIBLE_ERROR",
    message: "Story Bible请求未能完成，请稍后手动重试。",
  });
}

export function storyBibleOutcomeUnknownError(
  operation: "create" | "save",
): StoryBibleApiError {
  return new StoryBibleApiError({
    kind: "outcome_unknown",
    code:
      operation === "create"
        ? "STORY_BIBLE_CREATE_OUTCOME_UNKNOWN"
        : "STORY_BIBLE_SAVE_OUTCOME_UNKNOWN",
    message:
      operation === "create"
        ? "创建结果未确认，请重新读取 Story Bible 核实。"
        : "保存结果未确认，请重新读取 Story Bible 核实。",
  });
}

export function isIndeterminateWriteFailure(error: unknown): boolean {
  return (
    error instanceof StoryBibleContractError ||
    (error instanceof StoryBibleApiError && error.kind === "contract") ||
    (error instanceof DOMException && error.name === "AbortError") ||
    error instanceof TypeError ||
    (error instanceof ApiError &&
      (error.status >= 500 || error.code === "INVALID_RESPONSE"))
  );
}

export function shouldClearStoryBibleSecuritySession(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (SECURITY_CODES.has(error.code) ||
      error.status === 401 ||
      error.status === 403)
  );
}

export function storyBibleContractError(): StoryBibleApiError {
  return contractError();
}
