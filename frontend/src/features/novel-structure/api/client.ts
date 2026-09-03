import { getJson, postJson, putJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { parseStrongVersionEtag } from "../../../api/etags";
import { isCanonicalPrefixedUlid } from "../../../api/identifiers";
import {
  securitySession,
  type SecuritySessionManager,
} from "../../../api/security-session";
import {
  normalizeStructureSummary,
  normalizeStructureTitle,
  validateStructureInput,
  type StructureFieldError,
} from "../validation";

import type {
  VersionedChapterContent,
  ChapterResponse,
  OutlineResponse,
  PositionedStructureInput,
  StructureTextInput,
  VersionedChapter,
  VersionedOutline,
  VersionedResource,
  VersionedVolume,
  VolumeResponse,
} from "./contracts";
import {
  isManuscript,
  normalizeManuscript,
  parseChapterContent,
} from "./content";

export type NovelStructureErrorKind =
  | "validation"
  | "project_not_found"
  | "outline_not_found"
  | "not_found"
  | "already_exists"
  | "position_conflict"
  | "ownership_conflict"
  | "conflict"
  | "security"
  | "unavailable"
  | "contract"
  | "outcome_unknown"
  | "aborted"
  | "unknown";

export class NovelStructureApiError extends Error {
  public readonly kind: NovelStructureErrorKind;
  public readonly code: string;
  public readonly fieldErrors: readonly StructureFieldError[];
  public readonly requestId: string | null;

  public constructor(input: {
    readonly kind: NovelStructureErrorKind;
    readonly code: string;
    readonly message: string;
    readonly fieldErrors?: readonly StructureFieldError[];
    readonly requestId?: string | null;
  }) {
    super(input.message);
    this.name = "NovelStructureApiError";
    this.kind = input.kind;
    this.code = input.code;
    this.fieldErrors = input.fieldErrors ?? [];
    this.requestId = input.requestId ?? null;
  }
}

export class NovelStructureContractError extends Error {
  public constructor() {
    super("Novel Structure API response did not match its contract.");
    this.name = "NovelStructureContractError";
  }
}

type ResourceKind = "outline" | "volume" | "chapter";
type CurrentResource = OutlineResponse | VolumeResponse | ChapterResponse;

const ID_PREFIX = {
  outline: ["out", "orv"],
  volume: ["vol", "vrv"],
  chapter: ["chp", "chv"],
} as const;

const BASE_KEYS = [
  "project_id",
  "current_revision_id",
  "revision_number",
  "concurrency_version",
  "title",
  "summary",
  "created_at",
  "updated_at",
  "revision_created_at",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseResource(
  value: unknown,
  kind: ResourceKind,
  expectedProjectId: string,
  expectedParentId?: string,
): CurrentResource {
  const identityKey = `${kind}_id`;
  const expectedKeys = [
    identityKey,
    ...BASE_KEYS,
    ...(kind === "volume" ? ["position"] : []),
    ...(kind === "chapter" ? ["volume_id", "position"] : []),
  ];
  if (
    !isRecord(value) ||
    Object.keys(value).length !== expectedKeys.length ||
    !expectedKeys.every((key) => Object.hasOwn(value, key))
  ) {
    throw new NovelStructureContractError();
  }
  const [idPrefix, revisionPrefix] = ID_PREFIX[kind];
  const identity = value[identityKey];
  const projectId = value.project_id;
  const revisionId = value.current_revision_id;
  const revision = value.revision_number;
  const version = value.concurrency_version;
  const position = value.position;
  const volumeId = value.volume_id;
  const textErrors = validateStructureInput(
    value.title,
    value.summary,
    kind === "outline" ? undefined : position,
  );
  const timestampPattern =
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u;
  const timestamps = [
    value.created_at,
    value.updated_at,
    value.revision_created_at,
  ];
  if (
    !isCanonicalPrefixedUlid(identity, idPrefix) ||
    !isCanonicalPrefixedUlid(projectId, "prj") ||
    projectId !== expectedProjectId ||
    !isCanonicalPrefixedUlid(revisionId, revisionPrefix) ||
    typeof revision !== "number" ||
    !Number.isSafeInteger(revision) ||
    revision < 1 ||
    revision !== version ||
    textErrors.length > 0 ||
    normalizeStructureTitle(value.title as string) !== value.title ||
    normalizeStructureSummary(value.summary as string) !== value.summary ||
    timestamps.some(
      (item) =>
        typeof item !== "string" ||
        !timestampPattern.test(item) ||
        !Number.isFinite(Date.parse(item)),
    ) ||
    Date.parse(value.created_at as string) >
      Date.parse(value.updated_at as string) ||
    Date.parse(value.updated_at as string) !==
      Date.parse(value.revision_created_at as string) ||
    (kind === "chapter" &&
      (!isCanonicalPrefixedUlid(volumeId, "vol") ||
        (expectedParentId !== undefined && volumeId !== expectedParentId)))
  ) {
    throw new NovelStructureContractError();
  }
  return value as unknown as CurrentResource;
}

function parseList<T extends VolumeResponse | ChapterResponse>(
  value: unknown,
  kind: "volume" | "chapter",
  projectId: string,
  parentId?: string,
): readonly T[] {
  if (!Array.isArray(value)) throw new NovelStructureContractError();
  const result = value.map((item) =>
    parseResource(item, kind, projectId, parentId),
  ) as T[];
  if (
    result.some(
      (item, index) => index > 0 && result[index - 1].position >= item.position,
    )
  ) {
    throw new NovelStructureContractError();
  }
  return Object.freeze(
    result.map((item) => Object.freeze({ ...item }) as unknown as T),
  );
}

function versioned<T extends { readonly concurrency_version: number }>(
  resource: T,
  etag: string | null,
): VersionedResource<T> {
  let parsed;
  try {
    parsed = parseStrongVersionEtag(etag);
  } catch {
    throw new NovelStructureContractError();
  }
  if (parsed.version !== resource.concurrency_version) {
    throw new NovelStructureContractError();
  }
  return Object.freeze({
    resource: Object.freeze({ ...resource }),
    etag: parsed.etag,
    version: parsed.version,
  });
}

function validationError(
  code: string,
  message: string,
  fieldErrors: readonly StructureFieldError[] = [],
): NovelStructureApiError {
  return new NovelStructureApiError({
    kind: "validation",
    code,
    message,
    fieldErrors,
  });
}

function validateProjectId(projectId: string): void {
  if (!isCanonicalPrefixedUlid(projectId, "prj")) {
    throw validationError("INVALID_PROJECT_ID", "Project编号无效。");
  }
}

function validateId(value: string, prefix: "out" | "vol" | "chp"): void {
  if (!isCanonicalPrefixedUlid(value, prefix)) {
    throw validationError("INVALID_STRUCTURE_ID", "小说结构资源编号无效。");
  }
}

function validatedBody(input: StructureTextInput | PositionedStructureInput) {
  const position = "position" in input ? input.position : undefined;
  const errors = validateStructureInput(input.title, input.summary, position);
  if (errors.length > 0) {
    throw validationError(
      "INVALID_NOVEL_STRUCTURE_INPUT",
      "小说结构字段未通过验证。",
      errors,
    );
  }
  return {
    title: normalizeStructureTitle(input.title),
    summary: normalizeStructureSummary(input.summary),
    ...(position === undefined ? {} : { position }),
  };
}

function errorMessage(kind: NovelStructureErrorKind): string {
  const messages: Record<NovelStructureErrorKind, string> = {
    validation: "小说结构字段未通过服务端验证。",
    project_not_found: "指定项目不存在。",
    outline_not_found: "该项目尚未创建大纲。",
    not_found: "指定小说结构资源不存在。",
    already_exists: "该项目已经存在大纲，请重新读取。",
    position_conflict: "该顺序已被占用，请选择其他正整数。",
    ownership_conflict: "所选卷不属于当前项目。",
    conflict: "内容已被其他操作更新。草稿已保留，请重新读取后再处理。",
    security: "安全会话无效，请检查后手动重新提交。",
    unavailable: "小说结构服务暂时不可用，请稍后手动重试。",
    contract: "小说结构服务返回了无法安全读取的数据。",
    outcome_unknown: "写入结果无法确认，请重新读取后再决定是否提交。",
    aborted: "请求已取消。",
    unknown: "小说结构请求未能完成，请稍后手动重试。",
  };
  return messages[kind];
}

function normalizeError(error: unknown): NovelStructureApiError {
  if (error instanceof NovelStructureApiError) return error;
  if (error instanceof DOMException && error.name === "AbortError") {
    return new NovelStructureApiError({
      kind: "aborted",
      code: "REQUEST_ABORTED",
      message: errorMessage("aborted"),
    });
  }
  if (error instanceof NovelStructureContractError) {
    return new NovelStructureApiError({
      kind: "contract",
      code: "NOVEL_STRUCTURE_API_CONTRACT_ERROR",
      message: errorMessage("contract"),
    });
  }
  if (error instanceof ApiError) {
    let kind: NovelStructureErrorKind = "unknown";
    if (error.code === "PROJECT_NOT_FOUND") kind = "project_not_found";
    else if (error.code === "OUTLINE_NOT_FOUND") kind = "outline_not_found";
    else if (
      error.code === "VOLUME_NOT_FOUND" ||
      error.code === "CHAPTER_NOT_FOUND"
    )
      kind = "not_found";
    else if (error.code === "OUTLINE_ALREADY_EXISTS") kind = "already_exists";
    else if (
      error.code === "VOLUME_POSITION_CONFLICT" ||
      error.code === "CHAPTER_POSITION_CONFLICT"
    )
      kind = "position_conflict";
    else if (error.code === "CHAPTER_VOLUME_OWNERSHIP_MISMATCH")
      kind = "ownership_conflict";
    else if (error.status === 412) kind = "conflict";
    else if (error.status === 401 || error.status === 403) kind = "security";
    else if (
      error.status === 422 ||
      error.status === 413 ||
      error.status === 400 ||
      error.status === 428
    )
      kind = "validation";
    else if (error.code === "INVALID_RESPONSE") kind = "contract";
    else if (error.status >= 500) kind = "unavailable";
    return new NovelStructureApiError({
      kind,
      code: error.code,
      message: errorMessage(kind),
      requestId: /^[A-Za-z0-9._:-]{1,128}$/u.test(error.requestId ?? "")
        ? error.requestId
        : null,
    });
  }
  return new NovelStructureApiError({
    kind: "unknown",
    code: "NOVEL_STRUCTURE_UNKNOWN_ERROR",
    message: errorMessage("unknown"),
  });
}

function shouldClearSession(error: unknown): boolean {
  return (
    error instanceof ApiError && (error.status === 401 || error.status === 403)
  );
}

function isIndeterminate(error: unknown): boolean {
  return error instanceof TypeError;
}

function requireStatus(actual: number | undefined, expected: number): void {
  if (actual !== expected) throw new NovelStructureContractError();
}

async function write<T>(
  session: SecuritySessionManager,
  signal: AbortSignal | undefined,
  operation: (csrfToken: string) => Promise<T>,
): Promise<T> {
  let started = false;
  try {
    const proof = await session.getValidSession(signal);
    started = true;
    return await operation(proof.csrfToken);
  } catch (error) {
    if (shouldClearSession(error)) session.clear();
    if (started && isIndeterminate(error)) {
      throw new NovelStructureApiError({
        kind: "outcome_unknown",
        code: "NOVEL_STRUCTURE_WRITE_OUTCOME_UNKNOWN",
        message: errorMessage("outcome_unknown"),
      });
    }
    throw normalizeError(error);
  }
}

export interface NovelStructureApiClient {
  readonly getOutline: (
    projectId: string,
    signal?: AbortSignal,
  ) => Promise<VersionedOutline>;
  readonly createOutline: (
    projectId: string,
    input: StructureTextInput,
    signal?: AbortSignal,
  ) => Promise<VersionedOutline>;
  readonly updateOutline: (
    outlineId: string,
    projectId: string,
    input: StructureTextInput,
    etag: string,
    signal?: AbortSignal,
  ) => Promise<VersionedOutline>;
  readonly listVolumes: (
    projectId: string,
    signal?: AbortSignal,
  ) => Promise<readonly VolumeResponse[]>;
  readonly getVolume: (
    volumeId: string,
    projectId: string,
    signal?: AbortSignal,
  ) => Promise<VersionedVolume>;
  readonly createVolume: (
    projectId: string,
    input: PositionedStructureInput,
    signal?: AbortSignal,
  ) => Promise<VersionedVolume>;
  readonly updateVolume: (
    volumeId: string,
    projectId: string,
    input: PositionedStructureInput,
    etag: string,
    signal?: AbortSignal,
  ) => Promise<VersionedVolume>;
  readonly listChapters: (
    projectId: string,
    volumeId: string,
    signal?: AbortSignal,
  ) => Promise<readonly ChapterResponse[]>;
  readonly getChapter: (
    chapterId: string,
    projectId: string,
    volumeId?: string,
    signal?: AbortSignal,
  ) => Promise<VersionedChapter>;
  readonly getChapterContent: (
    chapterId: string,
    projectId: string,
    signal?: AbortSignal,
  ) => Promise<VersionedChapterContent>;
  readonly updateChapterContent: (
    chapterId: string,
    projectId: string,
    content: string,
    etag: string,
    signal?: AbortSignal,
  ) => Promise<VersionedChapterContent>;
  readonly createChapter: (
    projectId: string,
    volumeId: string,
    input: PositionedStructureInput,
    signal?: AbortSignal,
  ) => Promise<VersionedChapter>;
  readonly updateChapter: (
    chapterId: string,
    projectId: string,
    volumeId: string,
    input: PositionedStructureInput,
    etag: string,
    signal?: AbortSignal,
  ) => Promise<VersionedChapter>;
}

export function createNovelStructureApiClient(
  session: SecuritySessionManager = securitySession,
): NovelStructureApiClient {
  const current = async <T extends CurrentResource>(
    path: string,
    kind: ResourceKind,
    projectId: string,
    parentId?: string,
    signal?: AbortSignal,
  ): Promise<VersionedResource<T>> => {
    validateProjectId(projectId);
    try {
      const response = await getJson(
        path,
        (value) => parseResource(value, kind, projectId, parentId) as T,
        { signal },
      );
      requireStatus(response.status, 200);
      return versioned(response.data, response.etag ?? null);
    } catch (error) {
      throw normalizeError(error);
    }
  };

  const mutate = async <T extends CurrentResource>(input: {
    readonly method: "post" | "put";
    readonly path: string;
    readonly kind: ResourceKind;
    readonly projectId: string;
    readonly parentId?: string;
    readonly body: StructureTextInput | PositionedStructureInput;
    readonly etag?: string;
    readonly location?: string;
    readonly signal?: AbortSignal;
  }): Promise<VersionedResource<T>> => {
    validateProjectId(input.projectId);
    const body = validatedBody(input.body);
    return write(session, input.signal, async (csrfToken) => {
      const request = input.method === "post" ? postJson : putJson;
      const response = await request(
        input.path,
        body,
        (value) =>
          parseResource(
            value,
            input.kind,
            input.projectId,
            input.parentId,
          ) as T,
        {
          signal: input.signal,
          headers: {
            "X-CSRF-Token": csrfToken,
            ...(input.etag === undefined ? {} : { "If-Match": input.etag }),
          },
        },
      );
      requireStatus(response.status, input.method === "post" ? 201 : 200);
      const result = versioned(response.data, response.etag ?? null);
      if (
        input.location !== undefined &&
        response.location !==
          input.location.replace(
            "{id}",
            input.kind === "volume"
              ? (result.resource as VolumeResponse).volume_id
              : (result.resource as ChapterResponse).chapter_id,
          )
      ) {
        throw new NovelStructureContractError();
      }
      return result;
    });
  };

  return {
    getOutline(projectId, signal) {
      return current(
        `projects/${encodeURIComponent(projectId)}/outline`,
        "outline",
        projectId,
        undefined,
        signal,
      );
    },
    createOutline(projectId, input, signal) {
      return mutate({
        method: "post",
        path: `projects/${encodeURIComponent(projectId)}/outline`,
        kind: "outline",
        projectId,
        body: input,
        signal,
      });
    },
    updateOutline(outlineId, projectId, input, etag, signal) {
      validateId(outlineId, "out");
      return mutate({
        method: "put",
        path: `outlines/${encodeURIComponent(outlineId)}`,
        kind: "outline",
        projectId,
        body: input,
        etag,
        signal,
      });
    },
    async listVolumes(projectId, signal) {
      validateProjectId(projectId);
      try {
        const response = await getJson(
          `projects/${encodeURIComponent(projectId)}/volumes`,
          (value) => parseList<VolumeResponse>(value, "volume", projectId),
          { signal },
        );
        requireStatus(response.status, 200);
        return response.data;
      } catch (error) {
        throw normalizeError(error);
      }
    },
    getVolume(volumeId, projectId, signal) {
      validateId(volumeId, "vol");
      return current(
        `volumes/${encodeURIComponent(volumeId)}`,
        "volume",
        projectId,
        undefined,
        signal,
      );
    },
    createVolume(projectId, input, signal) {
      return mutate({
        method: "post",
        path: `projects/${encodeURIComponent(projectId)}/volumes`,
        kind: "volume",
        projectId,
        body: input,
        location: "/api/v1/volumes/{id}",
        signal,
      });
    },
    updateVolume(volumeId, projectId, input, etag, signal) {
      validateId(volumeId, "vol");
      return mutate({
        method: "put",
        path: `volumes/${encodeURIComponent(volumeId)}`,
        kind: "volume",
        projectId,
        body: input,
        etag,
        signal,
      });
    },
    async listChapters(projectId, volumeId, signal) {
      validateProjectId(projectId);
      validateId(volumeId, "vol");
      try {
        const response = await getJson(
          `projects/${encodeURIComponent(projectId)}/volumes/${encodeURIComponent(volumeId)}/chapters`,
          (value) =>
            parseList<ChapterResponse>(value, "chapter", projectId, volumeId),
          { signal },
        );
        requireStatus(response.status, 200);
        return response.data;
      } catch (error) {
        throw normalizeError(error);
      }
    },
    getChapter(chapterId, projectId, volumeId, signal) {
      validateId(chapterId, "chp");
      if (volumeId !== undefined) validateId(volumeId, "vol");
      return current(
        `chapters/${encodeURIComponent(chapterId)}`,
        "chapter",
        projectId,
        volumeId,
        signal,
      );
    },
    async getChapterContent(chapterId, projectId, signal) {
      validateId(chapterId, "chp");
      validateProjectId(projectId);
      try {
        const response = await getJson(
          `chapters/${encodeURIComponent(chapterId)}/content`,
          (value) => parseChapterContent(value, chapterId, projectId),
          { signal },
        );
        requireStatus(response.status, 200);
        return versioned(response.data, response.etag ?? null);
      } catch (error) {
        throw normalizeError(error);
      }
    },
    async updateChapterContent(chapterId, projectId, content, etag, signal) {
      validateId(chapterId, "chp");
      validateProjectId(projectId);
      if (!isManuscript(content))
        throw validationError(
          "INVALID_MANUSCRIPT_CONTENT",
          "正文字段未通过验证。",
        );
      try {
        parseStrongVersionEtag(etag);
      } catch {
        throw validationError(
          "INVALID_IF_MATCH",
          "正文版本信息无效，请重新加载。",
        );
      }
      return write(session, signal, async (csrfToken) => {
        const response = await putJson(
          `chapters/${encodeURIComponent(chapterId)}/content`,
          { content: normalizeManuscript(content) },
          (value) => parseChapterContent(value, chapterId, projectId),
          { signal, headers: { "X-CSRF-Token": csrfToken, "If-Match": etag } },
        );
        requireStatus(response.status, 200);
        return versioned(response.data, response.etag ?? null);
      });
    },
    createChapter(projectId, volumeId, input, signal) {
      validateId(volumeId, "vol");
      return mutate({
        method: "post",
        path: `projects/${encodeURIComponent(projectId)}/volumes/${encodeURIComponent(volumeId)}/chapters`,
        kind: "chapter",
        projectId,
        parentId: volumeId,
        body: input,
        location: "/api/v1/chapters/{id}",
        signal,
      });
    },
    updateChapter(chapterId, projectId, volumeId, input, etag, signal) {
      validateId(chapterId, "chp");
      validateId(volumeId, "vol");
      return mutate({
        method: "put",
        path: `chapters/${encodeURIComponent(chapterId)}`,
        kind: "chapter",
        projectId,
        parentId: volumeId,
        body: input,
        etag,
        signal,
      });
    },
  };
}

export const novelStructureApiClient = createNovelStructureApiClient();
