import { ApiError } from "../../../api/errors";
import type { CharacterFieldError, CharacterFieldName } from "../validation";

import { CharacterContractError } from "./parsers";

export type CharacterApiErrorKind =
  | "aborted"
  | "network"
  | "validation"
  | "security"
  | "project_not_found"
  | "character_not_found"
  | "character_revision_not_found"
  | "character_id_conflict"
  | "invalid_cursor"
  | "version_conflict"
  | "persistence_unavailable"
  | "service_unavailable"
  | "contract"
  | "write_outcome_unknown"
  | "unknown";

export interface CharacterVersionConflict {
  readonly expectedVersion: number;
  readonly actualVersion: number;
  readonly requestId: string | null;
}

export interface CharacterApiErrorInit {
  readonly kind: CharacterApiErrorKind;
  readonly code: string;
  readonly message: string;
  readonly requestId?: string | null;
  readonly fieldErrors?: readonly CharacterFieldError[];
  readonly conflict?: CharacterVersionConflict | null;
}

export class CharacterApiError extends Error {
  public readonly kind: CharacterApiErrorKind;
  public readonly code: string;
  public readonly requestId: string | null;
  public readonly fieldErrors: readonly CharacterFieldError[];
  public readonly conflict: CharacterVersionConflict | null;

  public constructor(init: CharacterApiErrorInit) {
    super(init.message);
    this.name = "CharacterApiError";
    this.kind = init.kind;
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.fieldErrors = init.fieldErrors ?? [];
    this.conflict = init.conflict ?? null;
  }
}

const SECURITY_CODES = new Set([
  "SESSION_REQUIRED",
  "SESSION_EXPIRED",
  "CSRF_TOKEN_REQUIRED",
  "CSRF_TOKEN_INVALID",
  "ORIGIN_NOT_ALLOWED",
]);
const REQUEST_ID = /^[A-Za-z0-9._:-]{1,128}$/u;

function requestId(value: string | null): string | null {
  return value !== null && REQUEST_ID.test(value) ? value : null;
}

function fieldName(value: unknown): CharacterFieldName | null {
  if (value === "name" || value === "body.name") return "name";
  if (value === "role" || value === "body.role") return "role";
  if (value === "profile" || value === "body.profile") return "profile";
  return null;
}

function safeFieldErrors(
  details: Readonly<Record<string, unknown>>,
): readonly CharacterFieldError[] {
  const candidate = fieldName(details.field);
  if (candidate === null) return [];
  return [
    {
      field: candidate,
      message: `角色${candidate === "name" ? "名称" : candidate === "role" ? "定位" : "档案"}未通过服务端验证。`,
    },
  ];
}

function contractError(id: string | null = null): CharacterApiError {
  return new CharacterApiError({
    kind: "contract",
    code: "CHARACTER_API_CONTRACT_ERROR",
    message: "角色服务返回了无法安全读取的数据。",
    requestId: id,
  });
}

function positiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function conflictError(
  error: ApiError,
  submittedVersion: number | undefined,
): CharacterApiError {
  const details = error.details;
  if (
    error.code !== "CHARACTER_VERSION_CONFLICT" ||
    submittedVersion === undefined ||
    Object.keys(details).length !== 2 ||
    !positiveInteger(details.expected_version) ||
    !positiveInteger(details.actual_version) ||
    details.expected_version !== submittedVersion ||
    details.actual_version === submittedVersion
  ) {
    return contractError(requestId(error.requestId));
  }
  const id = requestId(error.requestId);
  return new CharacterApiError({
    kind: "version_conflict",
    code: error.code,
    message: "角色已被其他操作修订，草稿已保留。",
    requestId: id,
    conflict: {
      expectedVersion: details.expected_version,
      actualVersion: details.actual_version,
      requestId: id,
    },
  });
}

function kindFor(error: ApiError): CharacterApiErrorKind {
  if (
    SECURITY_CODES.has(error.code) ||
    error.status === 401 ||
    error.status === 403
  )
    return "security";
  if (error.code === "PROJECT_NOT_FOUND") return "project_not_found";
  if (error.code === "CHARACTER_NOT_FOUND") return "character_not_found";
  if (error.code === "CHARACTER_REVISION_NOT_FOUND")
    return "character_revision_not_found";
  if (error.code === "CHARACTER_ID_CONFLICT") return "character_id_conflict";
  if (
    error.code === "INVALID_CHARACTER_CURSOR" ||
    error.code === "INVALID_CHARACTER_REVISION_CURSOR"
  )
    return "invalid_cursor";
  if (error.code === "CHARACTER_PERSISTENCE_UNAVAILABLE")
    return "persistence_unavailable";
  if (
    error.code === "CHARACTER_SERVICE_UNAVAILABLE" ||
    error.code === "CHARACTER_QUERY_SERVICE_UNAVAILABLE" ||
    error.code === "CHARACTER_HISTORY_SERVICE_UNAVAILABLE"
  )
    return "service_unavailable";
  if (
    error.status === 413 ||
    error.status === 422 ||
    error.code.startsWith("INVALID_CHARACTER_") ||
    error.code === "INVALID_PROJECT_ID"
  )
    return "validation";
  if (
    error.status === 415 ||
    error.status === 428 ||
    error.code === "INVALID_IF_MATCH" ||
    error.code === "INVALID_RESPONSE"
  )
    return "contract";
  return "unknown";
}

function messageFor(kind: CharacterApiErrorKind): string {
  const messages: Record<CharacterApiErrorKind, string> = {
    character_revision_not_found: "指定的角色修订不存在。",
    aborted: "请求已取消。",
    network: "无法连接本地角色服务，请检查后手动重试。",
    validation: "角色输入未通过验证。",
    security: "安全会话无效，请检查后手动重新提交。",
    project_not_found: "指定Project不存在。",
    character_not_found: "指定角色不存在。",
    character_id_conflict: "服务端生成的角色编号发生冲突，请手动再次提交。",
    invalid_cursor: "角色列表分页位置无效，请重新加载第一页。",
    version_conflict: "角色版本冲突。",
    persistence_unavailable: "角色持久化暂时不可用。",
    service_unavailable: "角色服务暂时不可用。",
    contract: "角色服务返回了无法安全读取的数据。",
    write_outcome_unknown: "写入结果无法确认。",
    unknown: "角色请求未能完成，请稍后手动重试。",
  };
  return messages[kind];
}

export function normalizeCharacterApiError(
  error: unknown,
  submittedVersion?: number,
): CharacterApiError {
  if (error instanceof CharacterApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError") {
    return new CharacterApiError({
      kind: "aborted",
      code: "REQUEST_ABORTED",
      message: messageFor("aborted"),
    });
  }
  if (error instanceof CharacterContractError) return contractError();
  if (error instanceof ApiError) {
    if (error.status === 412) return conflictError(error, submittedVersion);
    const kind = kindFor(error);
    return new CharacterApiError({
      kind,
      code: error.code,
      message: messageFor(kind),
      requestId: requestId(error.requestId),
      fieldErrors: kind === "validation" ? safeFieldErrors(error.details) : [],
    });
  }
  if (error instanceof TypeError) {
    return new CharacterApiError({
      kind: "network",
      code: "NETWORK_ERROR",
      message: messageFor("network"),
    });
  }
  return new CharacterApiError({
    kind: "unknown",
    code: "UNKNOWN_CHARACTER_ERROR",
    message: messageFor("unknown"),
  });
}

export function characterWriteOutcomeUnknown(
  operation: "create" | "save",
): CharacterApiError {
  return new CharacterApiError({
    kind: "write_outcome_unknown",
    code:
      operation === "create"
        ? "CHARACTER_CREATE_OUTCOME_UNKNOWN"
        : "CHARACTER_SAVE_OUTCOME_UNKNOWN",
    message:
      operation === "create"
        ? "创建结果无法确认，请重新读取角色列表后人工判断。"
        : "保存结果无法确认，请读取服务器当前版本后选择处理方式。",
  });
}

export function isIndeterminateCharacterWrite(error: unknown): boolean {
  return (
    error instanceof CharacterContractError ||
    (error instanceof DOMException && error.name === "AbortError") ||
    error instanceof TypeError ||
    (error instanceof ApiError &&
      (error.status >= 500 || error.code === "INVALID_RESPONSE"))
  );
}

export function shouldClearCharacterSession(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (SECURITY_CODES.has(error.code) ||
      error.status === 401 ||
      error.status === 403)
  );
}
