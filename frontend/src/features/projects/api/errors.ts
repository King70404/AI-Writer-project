import { ApiError } from "../../../api/errors";

import { ProjectContractError } from "./parsers";

export type ProjectApiErrorKind =
  | "network"
  | "aborted"
  | "outcome_unknown"
  | "validation"
  | "security"
  | "not_found"
  | "conflict"
  | "unavailable"
  | "contract"
  | "unknown";

export type ProjectFieldName = "title" | "description" | "limit";

export interface ProjectFieldError {
  readonly field: ProjectFieldName;
  readonly message: string;
}

export interface ProjectConflictDetails {
  readonly expectedVersion: number;
  readonly actualVersion: number;
}

interface ProjectApiErrorInit {
  readonly kind: ProjectApiErrorKind;
  readonly code: string;
  readonly message: string;
  readonly requestId?: string | null;
  readonly fieldErrors?: readonly ProjectFieldError[];
  readonly conflict?: ProjectConflictDetails | null;
}

export class ProjectApiError extends Error {
  public readonly kind: ProjectApiErrorKind;
  public readonly code: string;
  public readonly requestId: string | null;
  public readonly fieldErrors: readonly ProjectFieldError[];
  public readonly conflict: ProjectConflictDetails | null;

  public constructor(init: ProjectApiErrorInit) {
    super(init.message);
    this.name = "ProjectApiError";
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

function fieldErrors(
  details: Readonly<Record<string, unknown>>,
): ProjectFieldError[] {
  const errors = details.errors;
  if (!Array.isArray(errors)) {
    return [];
  }
  const result: ProjectFieldError[] = [];
  for (const value of errors) {
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      continue;
    }
    const field = (value as Record<string, unknown>).field;
    const normalized =
      field === "body.title" || field === "title"
        ? "title"
        : field === "body.description" || field === "description"
          ? "description"
          : field === "query.limit" || field === "limit"
            ? "limit"
            : null;
    if (
      normalized !== null &&
      !result.some((item) => item.field === normalized)
    ) {
      result.push({
        field: normalized,
        message:
          normalized === "title"
            ? "项目标题未通过服务端验证。"
            : normalized === "description"
              ? "项目简介未通过服务端验证。"
              : "列表页大小未通过服务端验证。",
      });
    }
  }
  return result;
}

function apiErrorKind(error: ApiError): ProjectApiErrorKind {
  if (
    SECURITY_CODES.has(error.code) ||
    error.status === 401 ||
    error.status === 403
  ) {
    return "security";
  }
  if (
    error.status === 413 ||
    error.status === 422 ||
    error.code.startsWith("INVALID_PROJECT_")
  ) {
    return "validation";
  }
  if (error.status === 404) {
    return "not_found";
  }
  if ([409, 412, 428].includes(error.status)) {
    return "conflict";
  }
  if (error.status === 503) {
    return "unavailable";
  }
  if (error.status === 415 || error.code === "INVALID_RESPONSE") {
    return "contract";
  }
  return "unknown";
}

function isSafePositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function contractError(requestId: string | null = null): ProjectApiError {
  return new ProjectApiError({
    kind: "contract",
    code: "PROJECT_API_CONTRACT_ERROR",
    message: "项目服务返回了无法安全读取的数据。",
    requestId,
  });
}

function normalizeVersionConflict(
  error: ApiError,
  submittedVersion: number | undefined,
): ProjectApiError {
  const details = error.details;
  const keys = Object.keys(details);
  if (
    error.code !== "PROJECT_VERSION_CONFLICT" ||
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
  return new ProjectApiError({
    kind: "conflict",
    code: error.code,
    message: "项目已被其他操作修订。草稿已保留，请读取最新版本后选择处理方式。",
    requestId: safeRequestId(error.requestId),
    conflict: {
      expectedVersion: details.expected_version,
      actualVersion: details.actual_version,
    },
  });
}

function safeMessage(kind: ProjectApiErrorKind, code: string): string {
  if (kind === "security") {
    return code === "ORIGIN_NOT_ALLOWED"
      ? "当前页面来源未通过安全验证。"
      : "安全会话无效，请检查后手动重新提交。";
  }
  if (kind === "validation") {
    return code === "REQUEST_TOO_LARGE"
      ? "提交内容超过服务允许的大小。"
      : "提交内容未通过服务端验证。";
  }
  if (kind === "not_found") {
    return "指定项目不存在。";
  }
  if (kind === "conflict") {
    return "项目状态已变化，请重新读取后再操作。";
  }
  if (kind === "unavailable") {
    return "项目服务暂时不可用，请稍后手动重试。";
  }
  if (kind === "contract") {
    return code === "UNSUPPORTED_MEDIA_TYPE"
      ? "项目服务拒绝了请求的数据格式。"
      : "项目服务返回了无法安全读取的数据。";
  }
  return "项目请求未能完成，请稍后手动重试。";
}

export function normalizeProjectApiError(
  error: unknown,
  submittedVersion?: number,
): ProjectApiError {
  if (error instanceof ProjectApiError) {
    return error;
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ProjectApiError({
      kind: "aborted",
      code: "REQUEST_ABORTED",
      message: "请求已取消；若创建请求已发出，请先检查列表再决定是否重新提交。",
    });
  }
  if (error instanceof ProjectContractError) {
    return contractError();
  }
  if (error instanceof ApiError) {
    if (error.status === 412) {
      return normalizeVersionConflict(error, submittedVersion);
    }
    const kind = apiErrorKind(error);
    return new ProjectApiError({
      kind,
      code: error.code,
      message: safeMessage(kind, error.code),
      requestId: safeRequestId(error.requestId),
      fieldErrors: kind === "validation" ? fieldErrors(error.details) : [],
    });
  }
  if (error instanceof TypeError) {
    return new ProjectApiError({
      kind: "network",
      code: "NETWORK_ERROR",
      message: "无法连接本地项目服务，请检查后手动重试。",
    });
  }
  return new ProjectApiError({
    kind: "unknown",
    code: "UNKNOWN_PROJECT_ERROR",
    message: "项目请求未能完成，请稍后手动重试。",
  });
}

export function projectOutcomeUnknownError(error: unknown): ProjectApiError {
  return new ProjectApiError({
    kind: "outcome_unknown",
    code:
      error instanceof DOMException && error.name === "AbortError"
        ? "PROJECT_REVISION_ABORTED"
        : "PROJECT_REVISION_NETWORK_INTERRUPTED",
    message: "保存结果未确认，请重新加载项目核实。",
  });
}

export function projectRevisionContractError(): ProjectApiError {
  return contractError();
}

export function shouldClearProjectSecuritySession(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (SECURITY_CODES.has(error.code) ||
      error.status === 401 ||
      error.status === 403)
  );
}

export function duplicateProjectContractError(): ProjectApiError {
  return new ProjectApiError({
    kind: "contract",
    code: "DUPLICATE_PROJECT_ID",
    message: "项目列表分页响应包含重复项目，已保留当前列表。",
  });
}
