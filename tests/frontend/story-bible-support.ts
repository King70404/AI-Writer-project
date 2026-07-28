import { vi } from "vitest";

import type { StoryBibleApiClient } from "../../frontend/src/features/story-bible/api/client";
import type {
  StoryBibleResponse,
  VersionedStoryBibleResource,
} from "../../frontend/src/features/story-bible/api/contracts";
import { StoryBibleApiError } from "../../frontend/src/features/story-bible/api/errors";

export const storyProjectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const secondStoryProjectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW";
export const storyBibleId = "sbl_01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const csrfToken = "csrf-story-bible-private-fixture-token";
export const storyTimestamp = "2026-07-27T08:30:00Z";

const revisionIds = [
  "sbr_01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "sbr_01ARZ3NDEKTSV4RRFFQ69G5FAW",
  "sbr_01ARZ3NDEKTSV4RRFFQ69G5FAX",
  "sbr_01ARZ3NDEKTSV4RRFFQ69G5FAY",
] as const;

export function storyBibleResponse(
  version = 1,
  overrides: Partial<StoryBibleResponse> = {},
): StoryBibleResponse {
  return {
    story_bible_id: storyBibleId,
    project_id: storyProjectId,
    current_revision_id:
      revisionIds[Math.min(version, revisionIds.length) - 1] ?? revisionIds[0],
    revision_number: version,
    concurrency_version: version,
    title: `设定集版本${version}`,
    content: `设定正文版本${version}\n第二行`,
    created_at: storyTimestamp,
    updated_at: storyTimestamp,
    revision_created_at: storyTimestamp,
    head_updated_at: storyTimestamp,
    ...overrides,
  };
}

export function versionedStoryBible(
  version = 1,
  overrides: Partial<StoryBibleResponse> = {},
): VersionedStoryBibleResource {
  return {
    storyBible: storyBibleResponse(version, overrides),
    etag: `"${version}"`,
    version,
  };
}

export function storyBibleClient(
  overrides: Partial<StoryBibleApiClient> = {},
): StoryBibleApiClient {
  return {
    getStoryBibleForProject: vi.fn().mockResolvedValue(versionedStoryBible()),
    getStoryBible: vi.fn().mockResolvedValue(versionedStoryBible(2)),
    createStoryBible: vi.fn().mockResolvedValue(versionedStoryBible()),
    reviseStoryBible: vi.fn().mockResolvedValue(versionedStoryBible(2)),
    ...overrides,
  };
}

export function storyBibleError(
  kind: ConstructorParameters<typeof StoryBibleApiError>[0]["kind"],
  overrides: Partial<ConstructorParameters<typeof StoryBibleApiError>[0]> = {},
): StoryBibleApiError {
  return new StoryBibleApiError({
    kind,
    code: "SAFE_STORY_BIBLE_ERROR",
    message: "Story Bible安全错误。",
    ...overrides,
  });
}

export function storyBibleJsonResponse(
  value: unknown,
  options: {
    readonly status?: number;
    readonly etag?: string;
    readonly location?: string;
    readonly requestId?: string;
  } = {},
) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (options.etag !== undefined) {
    headers.set("ETag", options.etag);
  }
  if (options.location !== undefined) {
    headers.set("Location", options.location);
  }
  headers.set("X-Request-ID", options.requestId ?? "req_story_bible");
  return new Response(JSON.stringify(value), {
    status: options.status ?? 200,
    headers,
  });
}

export function storyBibleErrorEnvelope(
  code: string,
  details: Readonly<Record<string, unknown>> = {},
) {
  return {
    error: {
      code,
      message: "STORY_BIBLE_FRONTEND_SECRET_CANARY",
      details,
      retryable: false,
      suggested_action: "private suggestion",
    },
    request_id: "req_body_private",
  };
}
