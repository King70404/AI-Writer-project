import { vi } from "vitest";

import type { CharacterApiClient } from "../../frontend/src/features/character/api/client";
import type {
  CharacterListItemResponse,
  CharacterListPageResponse,
  CharacterResponse,
  VersionedCharacterResource,
} from "../../frontend/src/features/character/api/contracts";
import { CharacterApiError } from "../../frontend/src/features/character/api/errors";

export const characterProjectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const secondCharacterProjectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW";
export const characterId = "chr_01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const secondCharacterId = "chr_01ARZ3NDEKTSV4RRFFQ69G5FAW";
export const characterTimestamp = "2026-07-30T08:30:00Z";
export const olderCharacterTimestamp = "2026-07-29T08:30:00Z";

export function characterResponse(
  version = 1,
  overrides: Partial<CharacterResponse> = {},
): CharacterResponse {
  return {
    character_id: characterId,
    project_id: characterProjectId,
    current_revision_id:
      version === 1
        ? "crv_01ARZ3NDEKTSV4RRFFQ69G5FAV"
        : "crv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
    revision_number: version,
    concurrency_version: version,
    name: "林砚",
    role: "主角",
    profile: "秘密档案\n第二行",
    created_at: characterTimestamp,
    updated_at: characterTimestamp,
    revision_created_at: characterTimestamp,
    head_updated_at: characterTimestamp,
    ...overrides,
  };
}

export function characterListItem(
  overrides: Partial<CharacterListItemResponse> = {},
): CharacterListItemResponse {
  const resource = characterResponse();
  return {
    character_id: resource.character_id,
    current_revision_id: resource.current_revision_id,
    revision_number: resource.revision_number,
    concurrency_version: resource.concurrency_version,
    name: resource.name,
    role: resource.role,
    created_at: resource.created_at,
    updated_at: resource.updated_at,
    ...overrides,
  };
}

export function characterPage(
  overrides: Partial<CharacterListPageResponse> = {},
): CharacterListPageResponse {
  return {
    project_id: characterProjectId,
    items: [characterListItem()],
    next_cursor: null,
    has_more: false,
    ...overrides,
  };
}

export function versionedCharacter(
  version = 1,
  overrides: Partial<CharacterResponse> = {},
): VersionedCharacterResource {
  return {
    character: characterResponse(version, overrides),
    etag: `"${version}"`,
    version,
  };
}

export function characterClient(
  overrides: Partial<CharacterApiClient> = {},
): CharacterApiClient {
  return {
    listCharacters: vi.fn().mockResolvedValue(characterPage()),
    createCharacter: vi.fn().mockResolvedValue(versionedCharacter()),
    getCharacter: vi.fn().mockResolvedValue(versionedCharacter()),
    reviseCharacter: vi.fn().mockResolvedValue(versionedCharacter(2)),
    ...overrides,
  };
}

export function characterError(
  kind: ConstructorParameters<typeof CharacterApiError>[0]["kind"],
  overrides: Partial<ConstructorParameters<typeof CharacterApiError>[0]> = {},
): CharacterApiError {
  return new CharacterApiError({
    kind,
    code: "SAFE_CHARACTER_ERROR",
    message: "角色安全错误。",
    ...overrides,
  });
}

export function characterJsonResponse(
  value: unknown,
  options: {
    readonly status?: number;
    readonly etag?: string;
    readonly location?: string;
  } = {},
) {
  const headers = new Headers({
    "Content-Type": "application/json",
    "X-Request-ID": "req_character",
  });
  if (options.etag !== undefined) headers.set("ETag", options.etag);
  if (options.location !== undefined) headers.set("Location", options.location);
  return new Response(JSON.stringify(value), {
    status: options.status ?? 200,
    headers,
  });
}

export function characterErrorEnvelope(
  code: string,
  details: Readonly<Record<string, unknown>> = {},
) {
  return {
    error: {
      code,
      message: "CHARACTER_FRONTEND_SECRET_CANARY",
      details,
      retryable: false,
      suggested_action: "private suggestion",
    },
    request_id: "private_body_request",
  };
}
