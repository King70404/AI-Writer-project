import { vi } from "vitest";

import type { NovelStructureApiClient } from "../../frontend/src/features/novel-structure/api/client";
import { NovelStructureApiError } from "../../frontend/src/features/novel-structure/api/client";
import type {
  ChapterResponse,
  OutlineResponse,
  VersionedChapter,
  VersionedOutline,
  VersionedVolume,
  VolumeResponse,
} from "../../frontend/src/features/novel-structure/api/contracts";

export const structureProjectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const outlineId = "out_01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const volumeId = "vol_01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const secondVolumeId = "vol_01ARZ3NDEKTSV4RRFFQ69G5FAW";
export const chapterId = "chp_01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const secondChapterId = "chp_01ARZ3NDEKTSV4RRFFQ69G5FAW";
export const structureTimestamp = "2026-08-23T08:00:00Z";

export function outlineResponse(
  version = 1,
  overrides: Partial<OutlineResponse> = {},
): OutlineResponse {
  return {
    outline_id: outlineId,
    project_id: structureProjectId,
    current_revision_id:
      version === 1
        ? "orv_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        : "orv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
    revision_number: version,
    concurrency_version: version,
    title: "总纲",
    summary: "故事总纲",
    created_at: structureTimestamp,
    updated_at: structureTimestamp,
    revision_created_at: structureTimestamp,
    ...overrides,
  };
}

export function volumeResponse(
  version = 1,
  overrides: Partial<VolumeResponse> = {},
): VolumeResponse {
  return {
    volume_id: volumeId,
    project_id: structureProjectId,
    current_revision_id:
      version === 1
        ? "vrv_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        : "vrv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
    revision_number: version,
    concurrency_version: version,
    title: "第一卷",
    summary: "卷梗概",
    position: 1,
    created_at: structureTimestamp,
    updated_at: structureTimestamp,
    revision_created_at: structureTimestamp,
    ...overrides,
  };
}

export function chapterResponse(
  version = 1,
  overrides: Partial<ChapterResponse> = {},
): ChapterResponse {
  return {
    chapter_id: chapterId,
    project_id: structureProjectId,
    volume_id: volumeId,
    current_revision_id:
      version === 1
        ? "chv_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        : "chv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
    revision_number: version,
    concurrency_version: version,
    title: "第一章",
    summary: "章梗概",
    position: 1,
    created_at: structureTimestamp,
    updated_at: structureTimestamp,
    revision_created_at: structureTimestamp,
    ...overrides,
  };
}

export const versionedOutline = (
  version = 1,
  overrides: Partial<OutlineResponse> = {},
): VersionedOutline => ({
  resource: outlineResponse(version, overrides),
  etag: `"${version}"`,
  version,
});

export const versionedVolume = (
  version = 1,
  overrides: Partial<VolumeResponse> = {},
): VersionedVolume => ({
  resource: volumeResponse(version, overrides),
  etag: `"${version}"`,
  version,
});

export const versionedChapter = (
  version = 1,
  overrides: Partial<ChapterResponse> = {},
): VersionedChapter => ({
  resource: chapterResponse(version, overrides),
  etag: `"${version}"`,
  version,
});

export function structureClient(
  overrides: Partial<NovelStructureApiClient> = {},
): NovelStructureApiClient {
  return {
    getOutline: vi.fn().mockResolvedValue(versionedOutline()),
    createOutline: vi.fn().mockResolvedValue(versionedOutline()),
    updateOutline: vi.fn().mockResolvedValue(versionedOutline(2)),
    listVolumes: vi.fn().mockResolvedValue([volumeResponse()]),
    getVolume: vi.fn().mockResolvedValue(versionedVolume()),
    createVolume: vi.fn().mockResolvedValue(versionedVolume()),
    updateVolume: vi.fn().mockResolvedValue(versionedVolume(2)),
    listChapters: vi.fn().mockResolvedValue([chapterResponse()]),
    getChapter: vi.fn().mockResolvedValue(versionedChapter()),
    createChapter: vi.fn().mockResolvedValue(versionedChapter()),
    updateChapter: vi.fn().mockResolvedValue(versionedChapter(2)),
    ...overrides,
  };
}

export function structureError(
  kind: ConstructorParameters<typeof NovelStructureApiError>[0]["kind"],
  message: string,
): NovelStructureApiError {
  return new NovelStructureApiError({ kind, code: "SAFE_ERROR", message });
}

export function structureJsonResponse(
  value: unknown,
  options: {
    readonly status?: number;
    readonly etag?: string;
    readonly location?: string;
  } = {},
): Response {
  const headers = new Headers({
    "Content-Type": "application/json",
    "X-Request-ID": "req_structure",
  });
  if (options.etag !== undefined) headers.set("ETag", options.etag);
  if (options.location !== undefined) headers.set("Location", options.location);
  return new Response(JSON.stringify(value), {
    status: options.status ?? 200,
    headers,
  });
}

export function structureErrorEnvelope(
  code: string,
  details: Readonly<Record<string, unknown>> = {},
) {
  return {
    error: {
      code,
      message: "NOVEL_STRUCTURE_FRONTEND_SECRET_CANARY",
      details,
      retryable: false,
      suggested_action: "private",
    },
    request_id: "private_request_id",
  };
}
