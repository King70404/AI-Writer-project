import { vi } from "vitest";

import type {
  ProjectDetailApiClient,
  ProjectRevisionApiClient,
} from "../../frontend/src/features/projects/api/client";
import type {
  ProjectResponse,
  VersionedProjectResource,
} from "../../frontend/src/features/projects/api/contracts";

export const projectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const secondProjectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW";
export const timestamp = "2026-07-22T08:30:00Z";
export const csrfToken = "csrf-project-detail-private-fixture-token";

export function projectResponse(
  version = 1,
  overrides: Partial<ProjectResponse> = {},
): ProjectResponse {
  return {
    project_id: projectId,
    current_revision_id:
      version === 1
        ? "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        : version === 2
          ? "prv_01ARZ3NDEKTSV4RRFFQ69G5FAW"
          : "prv_01ARZ3NDEKTSV4RRFFQ69G5FAX",
    revision_number: version,
    concurrency_version: version,
    title: `项目版本${version}`,
    description: `简介版本${version}`,
    created_at: timestamp,
    updated_at: timestamp,
    revision_created_at: timestamp,
    head_updated_at: timestamp,
    ...overrides,
  };
}

export function versionedResource(
  version = 1,
  overrides: Partial<ProjectResponse> = {},
): VersionedProjectResource {
  return {
    project: projectResponse(version, overrides),
    etag: `"${version}"`,
    version,
  };
}

export function detailClient(
  getProject = vi.fn().mockResolvedValue(versionedResource()),
  reviseProject = vi.fn().mockResolvedValue(versionedResource(2)),
): ProjectDetailApiClient & ProjectRevisionApiClient {
  return { getProject, reviseProject };
}

export function jsonResponse(
  value: unknown,
  options: {
    readonly status?: number;
    readonly etag?: string;
    readonly requestId?: string;
  } = {},
) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (options.etag !== undefined) {
    headers.set("ETag", options.etag);
  }
  headers.set("X-Request-ID", options.requestId ?? "req_project_detail");
  return new Response(JSON.stringify(value), {
    status: options.status ?? 200,
    headers,
  });
}
