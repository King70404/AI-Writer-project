import { getJson, postJson } from "../../../api/client";
import { PROJECT_LIST_PAGE_SIZE } from "../constants";

import type {
  CreateProjectRequest,
  ProjectListResponse,
  ProjectResponse,
} from "./contracts";
import {
  normalizeProjectApiError,
  ProjectApiError,
  shouldClearProjectSecuritySession,
} from "./errors";
import { parseProjectListResponse, parseProjectResponse } from "./parsers";
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

export interface ProjectApiClient {
  readonly listProjects: (
    options?: ListProjectsOptions,
  ) => Promise<ProjectListResponse>;
  readonly createProject: (
    input: CreateProjectRequest,
    options?: CreateProjectOptions,
  ) => Promise<ProjectResponse>;
}

export function createProjectApiClient(
  securitySession: ProjectSecuritySessionManager = projectSecuritySession,
): ProjectApiClient {
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
        message: "项目标题和简介必须是文本。",
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
      if (shouldClearProjectSecuritySession(error)) {
        securitySession.clear();
      }
      throw normalizeProjectApiError(error);
    }
  };

  return { listProjects, createProject };
}

export const projectApiClient = createProjectApiClient();
