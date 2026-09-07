import { getJson, postJson, putJson } from "../../../api/client";
import {
  PROJECT_LIST_PAGE_SIZE,
  PROJECT_REVISION_HISTORY_PAGE_SIZE,
} from "../constants";
import { validateProjectInput } from "../validation";

import type {
  CreateProjectRequest,
  ProjectListResponse,
  ProjectResponse,
  ProjectRevisionHistoryResponse,
  ProjectRevisionResponse,
  ReviseProjectRequest,
  VersionedProjectResource,
} from "./contracts";
import { createVersionedProjectResource, parseProjectEtag } from "./etags";
import {
  normalizeProjectApiError,
  ProjectApiError,
  projectOutcomeUnknownError,
  shouldClearProjectSecuritySession,
} from "./errors";
import {
  isCanonicalProjectId,
  parseProjectListResponse,
  parseProjectResponse,
  parseProjectRevisionHistoryResponse,
  parseProjectRevisionResponse,
} from "./parsers";
import {
  projectSecuritySession,
  type ProjectSecuritySessionManager,
} from "./security-session";

export interface ListProjectsOptions {
  readonly limit?: number;
  readonly cursor?: string;
  readonly signal?: AbortSignal;
}
export interface CreateProjectOptions {
  readonly signal?: AbortSignal;
}
export interface GetProjectOptions {
  readonly signal?: AbortSignal;
}
export interface ReviseProjectInput extends ReviseProjectRequest {
  readonly projectId: string;
  readonly etag: string;
}
export interface ReviseProjectOptions {
  readonly signal?: AbortSignal;
}
export interface DeleteProjectInput {
  readonly projectId: string;
  readonly etag: string;
}
export interface DeleteProjectOptions {
  readonly signal?: AbortSignal;
}
export interface ListProjectRevisionsOptions {
  readonly projectId: string;
  readonly limit?: number;
  readonly cursor?: string;
  readonly signal?: AbortSignal;
}
export interface GetProjectRevisionOptions {
  readonly projectId: string;
  readonly revisionNumber: number;
  readonly signal?: AbortSignal;
}

export interface ProjectApiClient {
  readonly listProjects: (
    options?: ListProjectsOptions,
  ) => Promise<ProjectListResponse>;
  readonly createProject: (
    input: CreateProjectRequest,
    options?: CreateProjectOptions,
  ) => Promise<ProjectResponse>;
}
export interface ProjectDetailApiClient {
  readonly getProject: (
    projectId: string,
    options?: GetProjectOptions,
  ) => Promise<VersionedProjectResource>;
}
export interface ProjectRevisionApiClient {
  readonly reviseProject: (
    input: ReviseProjectInput,
    options?: ReviseProjectOptions,
  ) => Promise<VersionedProjectResource>;
}
export interface ProjectDeleteApiClient {
  readonly deleteProject: (
    input: DeleteProjectInput,
    options?: DeleteProjectOptions,
  ) => Promise<void>;
}
export interface ProjectRevisionHistoryApiClient {
  readonly listProjectRevisions: (
    options: ListProjectRevisionsOptions,
  ) => Promise<ProjectRevisionHistoryResponse>;
  readonly getProjectRevision: (
    options: GetProjectRevisionOptions,
  ) => Promise<ProjectRevisionResponse>;
}
export type CompleteProjectApiClient = ProjectApiClient &
  ProjectDetailApiClient &
  ProjectRevisionApiClient &
  ProjectDeleteApiClient &
  ProjectRevisionHistoryApiClient;

function invalidProjectIdError(): ProjectApiError {
  return new ProjectApiError({
    kind: "validation",
    code: "INVALID_PROJECT_ID",
    message: "小说地址中的编号无效。",
  });
}

function validateRevisionInput(input: ReviseProjectInput): {
  readonly etag: string;
  readonly version: number;
} {
  if (
    typeof input.title !== "string" ||
    typeof input.description !== "string"
  ) {
    throw new ProjectApiError({
      kind: "validation",
      code: "INVALID_REVISE_PROJECT_INPUT",
      message: "书名和简介必须是文本。",
    });
  }
  const fieldErrors = validateProjectInput(input.title, input.description);
  if (fieldErrors.length > 0) {
    throw new ProjectApiError({
      kind: "validation",
      code: "INVALID_REVISE_PROJECT_INPUT",
      message: "书名或简介未通过验证。",
      fieldErrors,
    });
  }
  return parseProjectEtag(input.etag);
}

function decodeDeleteResponse(value: unknown): { readonly deleted: true } {
  if (
    typeof value !== "object" ||
    value === null ||
    !("deleted" in value) ||
    value.deleted !== true
  ) {
    throw new Error("invalid delete response");
  }
  return { deleted: true };
}

export function createProjectApiClient(
  securitySession: ProjectSecuritySessionManager = projectSecuritySession,
): CompleteProjectApiClient {
  const listProjects = async (
    options: ListProjectsOptions = {},
  ): Promise<ProjectListResponse> => {
    try {
      const limit = options.limit ?? PROJECT_LIST_PAGE_SIZE;
      if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
        throw new ProjectApiError({
          kind: "validation",
          code: "INVALID_PROJECT_LIST_LIMIT",
          message: "列表页大小必须是1至100的整数。",
        });
      }
      const parameters = new URLSearchParams({ limit: String(limit) });
      if (options.cursor !== undefined) {
        if (typeof options.cursor !== "string" || options.cursor.length === 0) {
          throw new ProjectApiError({
            kind: "validation",
            code: "INVALID_PROJECT_LIST_CURSOR",
            message: "列表分页位置无效，请重新加载列表。",
          });
        }
        parameters.set("cursor", options.cursor);
      }
      const response = await getJson(
        `projects?${parameters.toString()}`,
        parseProjectListResponse,
        { signal: options.signal },
      );
      return response.data;
    } catch (error) {
      throw normalizeProjectApiError(error);
    }
  };

  const createProject = async (
    input: CreateProjectRequest,
    options: CreateProjectOptions = {},
  ): Promise<ProjectResponse> => {
    if (
      typeof input.title !== "string" ||
      typeof input.description !== "string"
    ) {
      throw new ProjectApiError({
        kind: "validation",
        code: "INVALID_CREATE_PROJECT_INPUT",
        message: "书名和简介必须是文本。",
      });
    }
    try {
      const session = await securitySession.getValidSession(options.signal);
      const response = await postJson("projects", input, parseProjectResponse, {
        signal: options.signal,
        headers: { "X-CSRF-Token": session.csrfToken },
      });
      return response.data;
    } catch (error) {
      if (shouldClearProjectSecuritySession(error)) securitySession.clear();
      throw normalizeProjectApiError(error);
    }
  };

  const getProject = async (
    projectId: string,
    options: GetProjectOptions = {},
  ): Promise<VersionedProjectResource> => {
    if (!isCanonicalProjectId(projectId)) throw invalidProjectIdError();
    try {
      const response = await getJson(
        `projects/${encodeURIComponent(projectId)}`,
        parseProjectResponse,
        { signal: options.signal },
      );
      if (response.data.project_id !== projectId) {
        throw new ProjectApiError({
          kind: "contract",
          code: "PROJECT_API_CONTRACT_ERROR",
          message: "小说服务返回了无法安全读取的数据。",
        });
      }
      return createVersionedProjectResource(
        response.data,
        response.etag ?? null,
      );
    } catch (error) {
      throw normalizeProjectApiError(error);
    }
  };

  const reviseProject = async (
    input: ReviseProjectInput,
    options: ReviseProjectOptions = {},
  ): Promise<VersionedProjectResource> => {
    if (!isCanonicalProjectId(input.projectId)) throw invalidProjectIdError();
    let submitted: { readonly etag: string; readonly version: number };
    try {
      submitted = validateRevisionInput(input);
    } catch (error) {
      throw normalizeProjectApiError(error);
    }
    let putStarted = false;
    try {
      const session = await securitySession.getValidSession(options.signal);
      putStarted = true;
      const response = await putJson(
        `projects/${encodeURIComponent(input.projectId)}`,
        { title: input.title, description: input.description },
        parseProjectResponse,
        {
          signal: options.signal,
          headers: {
            "X-CSRF-Token": session.csrfToken,
            "If-Match": submitted.etag,
          },
        },
      );
      const resource = createVersionedProjectResource(
        response.data,
        response.etag ?? null,
      );
      if (
        resource.project.project_id !== input.projectId ||
        resource.version <= submitted.version
      ) {
        throw new ProjectApiError({
          kind: "contract",
          code: "PROJECT_API_CONTRACT_ERROR",
          message: "小说服务返回了无法安全读取的数据。",
        });
      }
      return resource;
    } catch (error) {
      if (shouldClearProjectSecuritySession(error)) securitySession.clear();
      if (
        putStarted &&
        ((error instanceof DOMException && error.name === "AbortError") ||
          error instanceof TypeError)
      ) {
        throw projectOutcomeUnknownError(error);
      }
      throw normalizeProjectApiError(error, submitted.version);
    }
  };

  const deleteProject = async (
    input: DeleteProjectInput,
    options: DeleteProjectOptions = {},
  ): Promise<void> => {
    if (!isCanonicalProjectId(input.projectId)) throw invalidProjectIdError();
    const submitted = parseProjectEtag(input.etag);
    try {
      const session = await securitySession.getValidSession(options.signal);
      await postJson(
        `projects/${encodeURIComponent(input.projectId)}/delete`,
        {},
        decodeDeleteResponse,
        {
          signal: options.signal,
          headers: {
            "X-CSRF-Token": session.csrfToken,
            "If-Match": submitted.etag,
          },
        },
      );
    } catch (error) {
      if (shouldClearProjectSecuritySession(error)) securitySession.clear();
      throw normalizeProjectApiError(error, submitted.version);
    }
  };

  const listProjectRevisions = async (
    options: ListProjectRevisionsOptions,
  ): Promise<ProjectRevisionHistoryResponse> => {
    if (!isCanonicalProjectId(options.projectId)) throw invalidProjectIdError();
    try {
      const limit = options.limit ?? PROJECT_REVISION_HISTORY_PAGE_SIZE;
      if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
        throw new ProjectApiError({
          kind: "validation",
          code: "INVALID_PROJECT_REVISION_HISTORY_LIMIT",
          message: "历史版本页大小必须是1至100的整数。",
        });
      }
      const parameters = new URLSearchParams({ limit: String(limit) });
      if (options.cursor !== undefined) {
        if (typeof options.cursor !== "string" || options.cursor.length === 0) {
          throw new ProjectApiError({
            kind: "validation",
            code: "INVALID_PROJECT_REVISION_CURSOR",
            message: "历史版本分页位置无效，请重新加载。",
          });
        }
        parameters.set("cursor", options.cursor);
      }
      const response = await getJson(
        `projects/${encodeURIComponent(options.projectId)}/revisions?${parameters.toString()}`,
        (value) =>
          parseProjectRevisionHistoryResponse(value, options.projectId),
        { signal: options.signal },
      );
      return response.data;
    } catch (error) {
      throw normalizeProjectApiError(error);
    }
  };

  const getProjectRevision = async (
    options: GetProjectRevisionOptions,
  ): Promise<ProjectRevisionResponse> => {
    if (!isCanonicalProjectId(options.projectId)) throw invalidProjectIdError();
    if (
      !Number.isSafeInteger(options.revisionNumber) ||
      options.revisionNumber < 1
    ) {
      throw new ProjectApiError({
        kind: "validation",
        code: "INVALID_REVISION_NUMBER",
        message: "版本号必须是正整数。",
      });
    }
    try {
      const response = await getJson(
        `projects/${encodeURIComponent(options.projectId)}/revisions/${String(options.revisionNumber)}`,
        (value) =>
          parseProjectRevisionResponse(
            value,
            options.projectId,
            options.revisionNumber,
          ),
        { signal: options.signal },
      );
      return response.data;
    } catch (error) {
      throw normalizeProjectApiError(error);
    }
  };

  return {
    listProjects,
    createProject,
    getProject,
    reviseProject,
    deleteProject,
    listProjectRevisions,
    getProjectRevision,
  };
}

export const projectApiClient = createProjectApiClient();
