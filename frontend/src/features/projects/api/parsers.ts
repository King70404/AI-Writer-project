import type {
  BackendProjectErrorEnvelope,
  ProjectListItemResponse,
  ProjectListResponse,
  ProjectResponse,
  ProjectRevisionHistoryItemResponse,
  ProjectRevisionHistoryResponse,
  ProjectRevisionResponse,
  SecuritySessionResponse,
} from "./contracts";
import { isCanonicalPrefixedUlid } from "../../../api/identifiers";

export class ProjectContractError extends Error {
  public constructor() {
    super("Project API response did not match its contract.");
    this.name = "ProjectContractError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return (
    actual.length === expected.length &&
    expected.every((key) => Object.hasOwn(value, key))
  );
}

function requiredString(
  value: unknown,
  options: { readonly allowEmpty?: boolean; readonly maximum?: number } = {},
): string {
  if (
    typeof value !== "string" ||
    (options.allowEmpty !== true && value.length === 0) ||
    (options.maximum !== undefined && [...value].length > options.maximum)
  ) {
    throw new ProjectContractError();
  }
  return value;
}

const AWARE_RFC3339 =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u;

function requiredIdentifier(value: unknown, prefix: "prj" | "prv"): string {
  const identifier = requiredString(value, { maximum: 64 });
  if (!isCanonicalPrefixedUlid(identifier, prefix)) {
    throw new ProjectContractError();
  }
  return identifier;
}

export function isCanonicalProjectId(value: unknown): value is string {
  return isCanonicalPrefixedUlid(value, "prj");
}

export function parseProjectId(value: unknown): string {
  return requiredIdentifier(value, "prj");
}

function requiredPositiveInteger(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value <= 0) {
    throw new ProjectContractError();
  }
  return value;
}

function requiredTimestamp(value: unknown): string {
  const timestamp = requiredString(value, { maximum: 64 });
  if (
    !AWARE_RFC3339.test(timestamp) ||
    !Number.isFinite(Date.parse(timestamp))
  ) {
    throw new ProjectContractError();
  }
  return timestamp;
}

const LIST_ITEM_KEYS = [
  "project_id",
  "current_revision_id",
  "revision_number",
  "concurrency_version",
  "title",
  "created_at",
  "updated_at",
  "revision_created_at",
] as const;

export function parseProjectListItemResponse(
  value: unknown,
): ProjectListItemResponse {
  if (!isRecord(value) || !hasExactKeys(value, LIST_ITEM_KEYS)) {
    throw new ProjectContractError();
  }
  return {
    project_id: parseProjectId(value.project_id),
    current_revision_id: requiredIdentifier(value.current_revision_id, "prv"),
    revision_number: requiredPositiveInteger(value.revision_number),
    concurrency_version: requiredPositiveInteger(value.concurrency_version),
    title: requiredString(value.title, { maximum: 120 }),
    created_at: requiredTimestamp(value.created_at),
    updated_at: requiredTimestamp(value.updated_at),
    revision_created_at: requiredTimestamp(value.revision_created_at),
  };
}

const PROJECT_KEYS = [...LIST_ITEM_KEYS, "description", "head_updated_at"];

export function parseProjectResponse(value: unknown): ProjectResponse {
  if (!isRecord(value) || !hasExactKeys(value, PROJECT_KEYS)) {
    throw new ProjectContractError();
  }
  const item = parseProjectListItemResponse(
    Object.fromEntries(LIST_ITEM_KEYS.map((key) => [key, value[key]])),
  );
  return {
    ...item,
    description: requiredString(value.description, {
      allowEmpty: true,
      maximum: 2_000,
    }),
    head_updated_at: requiredTimestamp(value.head_updated_at),
  };
}

export function parseProjectListResponse(value: unknown): ProjectListResponse {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["items", "next_cursor", "has_more"]) ||
    !Array.isArray(value.items) ||
    typeof value.has_more !== "boolean" ||
    (value.next_cursor !== null && typeof value.next_cursor !== "string")
  ) {
    throw new ProjectContractError();
  }
  const items = value.items.map((item) => parseProjectListItemResponse(item));
  const projectIds = new Set(items.map((item) => item.project_id));
  if (projectIds.size !== items.length) {
    throw new ProjectContractError();
  }
  if (
    (value.has_more &&
      (items.length === 0 ||
        typeof value.next_cursor !== "string" ||
        value.next_cursor.length === 0)) ||
    (!value.has_more && value.next_cursor !== null)
  ) {
    throw new ProjectContractError();
  }
  return {
    items,
    next_cursor: value.next_cursor,
    has_more: value.has_more,
  };
}

const REVISION_HISTORY_ITEM_KEYS = [
  "revision_id",
  "revision_number",
  "title",
  "created_at",
  "is_current",
] as const;

export function parseProjectRevisionHistoryItemResponse(
  value: unknown,
): ProjectRevisionHistoryItemResponse {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, REVISION_HISTORY_ITEM_KEYS) ||
    typeof value.is_current !== "boolean"
  ) {
    throw new ProjectContractError();
  }
  return {
    revision_id: requiredIdentifier(value.revision_id, "prv"),
    revision_number: requiredPositiveInteger(value.revision_number),
    title: requiredString(value.title, { maximum: 120 }),
    created_at: requiredTimestamp(value.created_at),
    is_current: value.is_current,
  };
}

export function parseProjectRevisionHistoryResponse(
  value: unknown,
  expectedProjectId: string,
): ProjectRevisionHistoryResponse {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "project_id",
      "current_revision_number",
      "items",
      "next_cursor",
      "has_more",
    ]) ||
    !Array.isArray(value.items) ||
    typeof value.has_more !== "boolean" ||
    (value.next_cursor !== null && typeof value.next_cursor !== "string")
  ) {
    throw new ProjectContractError();
  }
  const projectId = parseProjectId(value.project_id);
  if (projectId !== expectedProjectId) {
    throw new ProjectContractError();
  }
  const currentRevisionNumber = requiredPositiveInteger(
    value.current_revision_number,
  );
  const items = value.items.map((item) =>
    parseProjectRevisionHistoryItemResponse(item),
  );
  const revisionNumbers = new Set<number>();
  const revisionIds = new Set<string>();
  let previousRevisionNumber: number | null = null;
  let currentCount = 0;
  for (const item of items) {
    if (
      revisionNumbers.has(item.revision_number) ||
      revisionIds.has(item.revision_id) ||
      (previousRevisionNumber !== null &&
        item.revision_number >= previousRevisionNumber) ||
      item.is_current !== (item.revision_number === currentRevisionNumber)
    ) {
      throw new ProjectContractError();
    }
    revisionNumbers.add(item.revision_number);
    revisionIds.add(item.revision_id);
    previousRevisionNumber = item.revision_number;
    if (item.is_current) {
      currentCount += 1;
    }
  }
  if (
    currentCount > 1 ||
    (value.has_more &&
      (items.length === 0 ||
        typeof value.next_cursor !== "string" ||
        value.next_cursor.length === 0)) ||
    (!value.has_more && value.next_cursor !== null)
  ) {
    throw new ProjectContractError();
  }
  return {
    project_id: projectId,
    current_revision_number: currentRevisionNumber,
    items,
    next_cursor: value.next_cursor,
    has_more: value.has_more,
  };
}

export function parseProjectRevisionResponse(
  value: unknown,
  expectedProjectId: string,
  expectedRevisionNumber: number,
): ProjectRevisionResponse {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, [
      "project_id",
      "revision_id",
      "revision_number",
      "title",
      "description",
      "created_at",
      "is_current",
      "current_revision_number",
    ]) ||
    typeof value.is_current !== "boolean"
  ) {
    throw new ProjectContractError();
  }
  const projectId = parseProjectId(value.project_id);
  const revisionNumber = requiredPositiveInteger(value.revision_number);
  const currentRevisionNumber = requiredPositiveInteger(
    value.current_revision_number,
  );
  if (
    projectId !== expectedProjectId ||
    revisionNumber !== expectedRevisionNumber ||
    value.is_current !== (revisionNumber === currentRevisionNumber)
  ) {
    throw new ProjectContractError();
  }
  return {
    project_id: projectId,
    revision_id: requiredIdentifier(value.revision_id, "prv"),
    revision_number: revisionNumber,
    title: requiredString(value.title, { maximum: 120 }),
    description: requiredString(value.description, {
      allowEmpty: true,
      maximum: 2_000,
    }),
    created_at: requiredTimestamp(value.created_at),
    is_current: value.is_current,
    current_revision_number: currentRevisionNumber,
  };
}

export function parseSecuritySessionResponse(
  value: unknown,
): SecuritySessionResponse {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["csrf_token", "expires_in_seconds"]) ||
    typeof value.csrf_token !== "string" ||
    value.csrf_token.length < 32 ||
    value.csrf_token.length > 512
  ) {
    throw new ProjectContractError();
  }
  return {
    csrf_token: value.csrf_token,
    expires_in_seconds: requiredPositiveInteger(value.expires_in_seconds),
  };
}

export function parseBackendProjectErrorEnvelope(
  value: unknown,
): BackendProjectErrorEnvelope {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, ["error", "request_id"]) ||
    !isRecord(value.error) ||
    !hasExactKeys(value.error, [
      "code",
      "message",
      "details",
      "retryable",
      "suggested_action",
    ]) ||
    !isRecord(value.error.details) ||
    typeof value.error.retryable !== "boolean" ||
    (value.error.suggested_action !== null &&
      typeof value.error.suggested_action !== "string")
  ) {
    throw new ProjectContractError();
  }
  return {
    error: {
      code: requiredString(value.error.code, { maximum: 128 }),
      message: requiredString(value.error.message, { maximum: 512 }),
      details: { ...value.error.details },
      retryable: value.error.retryable,
      suggested_action: value.error.suggested_action,
    },
    request_id: requiredString(value.request_id, { maximum: 128 }),
  };
}
