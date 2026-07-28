import { getJson, postJson, putJson } from "../../../api/client";
import {
  securitySession,
  type SecuritySessionManager,
} from "../../../api/security-session";
import {
  normalizeStoryBibleContent,
  normalizeStoryBibleTitle,
  validateStoryBibleInput,
} from "../validation";

import type {
  CreateStoryBibleRequest,
  ReviseStoryBibleRequest,
  VersionedStoryBibleResource,
} from "./contracts";
import {
  createVersionedStoryBibleResource,
  parseStoryBibleEtag,
} from "./etags";
import {
  isIndeterminateWriteFailure,
  normalizeStoryBibleApiError,
  shouldClearStoryBibleSecuritySession,
  StoryBibleApiError,
  storyBibleOutcomeUnknownError,
} from "./errors";
import {
  isCanonicalStoryBibleId,
  isCanonicalStoryBibleProjectId,
  parseStoryBibleResponse,
  StoryBibleContractError,
} from "./parsers";

export interface GetStoryBibleForProjectOptions {
  readonly projectId: string;
  readonly signal?: AbortSignal;
}

export interface GetStoryBibleOptions {
  readonly storyBibleId: string;
  readonly expectedProjectId?: string;
  readonly signal?: AbortSignal;
}

export interface CreateStoryBibleInput extends CreateStoryBibleRequest {
  readonly projectId: string;
  readonly signal?: AbortSignal;
}

export interface ReviseStoryBibleInput extends ReviseStoryBibleRequest {
  readonly storyBibleId: string;
  readonly expectedProjectId: string;
  readonly etag: string;
  readonly signal?: AbortSignal;
}

export interface StoryBibleApiClient {
  readonly getStoryBibleForProject: (
    options: GetStoryBibleForProjectOptions,
  ) => Promise<VersionedStoryBibleResource>;
  readonly getStoryBible: (
    options: GetStoryBibleOptions,
  ) => Promise<VersionedStoryBibleResource>;
  readonly createStoryBible: (
    input: CreateStoryBibleInput,
  ) => Promise<VersionedStoryBibleResource>;
  readonly reviseStoryBible: (
    input: ReviseStoryBibleInput,
  ) => Promise<VersionedStoryBibleResource>;
}

function invalidProjectIdError(): StoryBibleApiError {
  return new StoryBibleApiError({
    kind: "validation",
    code: "INVALID_PROJECT_ID",
    message: "项目地址中的编号无效。",
  });
}

function invalidStoryBibleIdError(): StoryBibleApiError {
  return new StoryBibleApiError({
    kind: "validation",
    code: "INVALID_STORY_BIBLE_ID",
    message: "Story Bible编号无效。",
  });
}

function validatedText(input: {
  readonly title: unknown;
  readonly content: unknown;
}): CreateStoryBibleRequest {
  const fieldErrors = validateStoryBibleInput(input.title, input.content);
  if (
    typeof input.title !== "string" ||
    typeof input.content !== "string" ||
    fieldErrors.length > 0
  ) {
    throw new StoryBibleApiError({
      kind: "validation",
      code: "INVALID_STORY_BIBLE_INPUT",
      message: "Story Bible标题或正文未通过验证。",
      fieldErrors,
    });
  }
  return {
    title: normalizeStoryBibleTitle(input.title),
    content: normalizeStoryBibleContent(input.content),
  };
}

function requireStatus(status: number | undefined, expected: number): void {
  if (status !== expected) {
    throw new StoryBibleContractError();
  }
}

export function createStoryBibleApiClient(
  sessionManager: SecuritySessionManager = securitySession,
): StoryBibleApiClient {
  const getStoryBibleForProject = async (
    options: GetStoryBibleForProjectOptions,
  ): Promise<VersionedStoryBibleResource> => {
    if (!isCanonicalStoryBibleProjectId(options.projectId)) {
      throw invalidProjectIdError();
    }
    try {
      const response = await getJson(
        `projects/${encodeURIComponent(options.projectId)}/story-bible`,
        (value) =>
          parseStoryBibleResponse(value, {
            expectedProjectId: options.projectId,
          }),
        { signal: options.signal },
      );
      requireStatus(response.status, 200);
      return createVersionedStoryBibleResource(
        response.data,
        response.etag ?? null,
      );
    } catch (error) {
      throw normalizeStoryBibleApiError(error);
    }
  };

  const getStoryBible = async (
    options: GetStoryBibleOptions,
  ): Promise<VersionedStoryBibleResource> => {
    if (!isCanonicalStoryBibleId(options.storyBibleId)) {
      throw invalidStoryBibleIdError();
    }
    if (
      options.expectedProjectId !== undefined &&
      !isCanonicalStoryBibleProjectId(options.expectedProjectId)
    ) {
      throw invalidProjectIdError();
    }
    try {
      const response = await getJson(
        `story-bibles/${encodeURIComponent(options.storyBibleId)}`,
        (value) =>
          parseStoryBibleResponse(value, {
            expectedStoryBibleId: options.storyBibleId,
            ...(options.expectedProjectId === undefined
              ? {}
              : { expectedProjectId: options.expectedProjectId }),
          }),
        { signal: options.signal },
      );
      requireStatus(response.status, 200);
      return createVersionedStoryBibleResource(
        response.data,
        response.etag ?? null,
      );
    } catch (error) {
      throw normalizeStoryBibleApiError(error);
    }
  };

  const createStoryBible = async (
    input: CreateStoryBibleInput,
  ): Promise<VersionedStoryBibleResource> => {
    if (!isCanonicalStoryBibleProjectId(input.projectId)) {
      throw invalidProjectIdError();
    }
    const body = validatedText(input);
    let postStarted = false;
    try {
      const session = await sessionManager.getValidSession(input.signal);
      postStarted = true;
      const response = await postJson(
        `projects/${encodeURIComponent(input.projectId)}/story-bible`,
        body,
        (value) =>
          parseStoryBibleResponse(value, {
            expectedProjectId: input.projectId,
          }),
        {
          signal: input.signal,
          headers: { "X-CSRF-Token": session.csrfToken },
        },
      );
      requireStatus(response.status, 201);
      const resource = createVersionedStoryBibleResource(
        response.data,
        response.etag ?? null,
      );
      const expectedLocation = `/api/v1/story-bibles/${resource.storyBible.story_bible_id}`;
      if (response.location !== expectedLocation) {
        throw new StoryBibleContractError();
      }
      return resource;
    } catch (error) {
      if (shouldClearStoryBibleSecuritySession(error)) {
        sessionManager.clear();
      }
      if (postStarted && isIndeterminateWriteFailure(error)) {
        throw storyBibleOutcomeUnknownError("create");
      }
      throw normalizeStoryBibleApiError(error);
    }
  };

  const reviseStoryBible = async (
    input: ReviseStoryBibleInput,
  ): Promise<VersionedStoryBibleResource> => {
    if (!isCanonicalStoryBibleId(input.storyBibleId)) {
      throw invalidStoryBibleIdError();
    }
    if (!isCanonicalStoryBibleProjectId(input.expectedProjectId)) {
      throw invalidProjectIdError();
    }
    const body: ReviseStoryBibleRequest = validatedText(input);
    let submitted;
    try {
      submitted = parseStoryBibleEtag(input.etag);
    } catch (error) {
      throw normalizeStoryBibleApiError(error);
    }
    let putStarted = false;
    try {
      const session = await sessionManager.getValidSession(input.signal);
      putStarted = true;
      const response = await putJson(
        `story-bibles/${encodeURIComponent(input.storyBibleId)}`,
        body,
        (value) =>
          parseStoryBibleResponse(value, {
            expectedStoryBibleId: input.storyBibleId,
            expectedProjectId: input.expectedProjectId,
          }),
        {
          signal: input.signal,
          headers: {
            "X-CSRF-Token": session.csrfToken,
            "If-Match": submitted.etag,
          },
        },
      );
      requireStatus(response.status, 200);
      const resource = createVersionedStoryBibleResource(
        response.data,
        response.etag ?? null,
      );
      if (resource.version <= submitted.version) {
        throw new StoryBibleContractError();
      }
      return resource;
    } catch (error) {
      if (shouldClearStoryBibleSecuritySession(error)) {
        sessionManager.clear();
      }
      if (putStarted && isIndeterminateWriteFailure(error)) {
        throw storyBibleOutcomeUnknownError("save");
      }
      throw normalizeStoryBibleApiError(error, submitted.version);
    }
  };

  return {
    getStoryBibleForProject,
    getStoryBible,
    createStoryBible,
    reviseStoryBible,
  };
}

export const storyBibleApiClient = createStoryBibleApiClient();
