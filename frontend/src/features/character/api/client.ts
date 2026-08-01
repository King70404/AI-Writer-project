import { getJson, postJson, putJson } from "../../../api/client";
import {
  securitySession,
  type SecuritySessionManager,
} from "../../../api/security-session";
import {
  normalizeCharacterName,
  normalizeCharacterProfile,
  normalizeCharacterRole,
  validateCharacterInput,
} from "../validation";

import type {
  CharacterListPageResponse,
  CreateCharacterRequest,
  ReviseCharacterRequest,
  VersionedCharacterResource,
} from "./contracts";
import {
  characterWriteOutcomeUnknown,
  isIndeterminateCharacterWrite,
  normalizeCharacterApiError,
  shouldClearCharacterSession,
  CharacterApiError,
} from "./errors";
import { parseCharacterEtag, versionedCharacter } from "./etags";
import {
  CharacterContractError,
  isCanonicalCharacterId,
  isCanonicalCharacterProjectId,
  parseCharacterListPageResponse,
  parseCharacterResponse,
} from "./parsers";

export interface ListCharactersOptions {
  readonly projectId: string;
  readonly limit?: number;
  readonly cursor?: string;
  readonly signal?: AbortSignal;
}
export interface CreateCharacterInput extends CreateCharacterRequest {
  readonly projectId: string;
  readonly signal?: AbortSignal;
}
export interface GetCharacterOptions {
  readonly projectId: string;
  readonly characterId: string;
  readonly signal?: AbortSignal;
}
export interface ReviseCharacterInput extends ReviseCharacterRequest {
  readonly projectId: string;
  readonly characterId: string;
  readonly etag: string;
  readonly signal?: AbortSignal;
}

export interface CharacterApiClient {
  readonly listCharacters: (
    options: ListCharactersOptions,
  ) => Promise<CharacterListPageResponse>;
  readonly createCharacter: (
    input: CreateCharacterInput,
  ) => Promise<VersionedCharacterResource>;
  readonly getCharacter: (
    options: GetCharacterOptions,
  ) => Promise<VersionedCharacterResource>;
  readonly reviseCharacter: (
    input: ReviseCharacterInput,
  ) => Promise<VersionedCharacterResource>;
}

function validationError(
  code: string,
  message: string,
  fieldErrors = [] as ConstructorParameters<
    typeof CharacterApiError
  >[0]["fieldErrors"],
): CharacterApiError {
  return new CharacterApiError({
    kind: "validation",
    code,
    message,
    fieldErrors,
  });
}

function validateProject(projectId: string): void {
  if (!isCanonicalCharacterProjectId(projectId)) {
    throw validationError("INVALID_PROJECT_ID", "Project编号无效。");
  }
}

function validateIdentity(projectId: string, characterId: string): void {
  validateProject(projectId);
  if (!isCanonicalCharacterId(characterId)) {
    throw validationError("INVALID_CHARACTER_ID", "角色编号无效。");
  }
}

function validatedText(input: {
  readonly name: unknown;
  readonly role: unknown;
  readonly profile: unknown;
}): CreateCharacterRequest {
  const fieldErrors = validateCharacterInput(
    input.name,
    input.role,
    input.profile,
  );
  if (
    typeof input.name !== "string" ||
    typeof input.role !== "string" ||
    typeof input.profile !== "string" ||
    fieldErrors.length > 0
  ) {
    throw validationError(
      "INVALID_CHARACTER_INPUT",
      "角色字段未通过验证。",
      fieldErrors,
    );
  }
  return {
    name: normalizeCharacterName(input.name),
    role: normalizeCharacterRole(input.role),
    profile: normalizeCharacterProfile(input.profile),
  };
}

function status(actual: number | undefined, expected: number): void {
  if (actual !== expected) throw new CharacterContractError();
}

export function createCharacterApiClient(
  session: SecuritySessionManager = securitySession,
): CharacterApiClient {
  return {
    async listCharacters(options) {
      validateProject(options.projectId);
      const limit = options.limit ?? 20;
      if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
        throw validationError(
          "INVALID_CHARACTER_LIST_LIMIT",
          "角色列表页大小必须为1至100的整数。",
        );
      }
      if (
        options.cursor !== undefined &&
        (typeof options.cursor !== "string" ||
          options.cursor.length < 1 ||
          options.cursor.length > 512)
      ) {
        throw validationError(
          "INVALID_CHARACTER_CURSOR",
          "角色列表分页位置无效。",
        );
      }
      const query = new URLSearchParams({ limit: String(limit) });
      if (options.cursor !== undefined) query.set("cursor", options.cursor);
      try {
        const response = await getJson(
          `projects/${encodeURIComponent(options.projectId)}/characters?${query.toString()}`,
          (value) => parseCharacterListPageResponse(value, options.projectId),
          { signal: options.signal },
        );
        status(response.status, 200);
        return response.data;
      } catch (error) {
        throw normalizeCharacterApiError(error);
      }
    },

    async createCharacter(input) {
      validateProject(input.projectId);
      const body = validatedText(input);
      let started = false;
      try {
        const proof = await session.getValidSession(input.signal);
        started = true;
        const response = await postJson(
          `projects/${encodeURIComponent(input.projectId)}/characters`,
          body,
          (value) => parseCharacterResponse(value, input.projectId),
          {
            signal: input.signal,
            headers: { "X-CSRF-Token": proof.csrfToken },
          },
        );
        status(response.status, 201);
        const resource = versionedCharacter(
          response.data,
          response.etag ?? null,
        );
        if (
          response.location !==
          `/api/v1/characters/${resource.character.character_id}`
        ) {
          throw new CharacterContractError();
        }
        return resource;
      } catch (error) {
        if (shouldClearCharacterSession(error)) session.clear();
        if (started && isIndeterminateCharacterWrite(error)) {
          throw characterWriteOutcomeUnknown("create");
        }
        throw normalizeCharacterApiError(error);
      }
    },

    async getCharacter(options) {
      validateIdentity(options.projectId, options.characterId);
      try {
        const response = await getJson(
          `characters/${encodeURIComponent(options.characterId)}`,
          (value) =>
            parseCharacterResponse(
              value,
              options.projectId,
              options.characterId,
            ),
          { signal: options.signal },
        );
        status(response.status, 200);
        return versionedCharacter(response.data, response.etag ?? null);
      } catch (error) {
        throw normalizeCharacterApiError(error);
      }
    },

    async reviseCharacter(input) {
      validateIdentity(input.projectId, input.characterId);
      const body = validatedText(input);
      let submitted;
      try {
        submitted = parseCharacterEtag(input.etag);
      } catch (error) {
        throw normalizeCharacterApiError(error);
      }
      let started = false;
      try {
        const proof = await session.getValidSession(input.signal);
        started = true;
        const response = await putJson(
          `characters/${encodeURIComponent(input.characterId)}`,
          body,
          (value) =>
            parseCharacterResponse(value, input.projectId, input.characterId),
          {
            signal: input.signal,
            headers: {
              "X-CSRF-Token": proof.csrfToken,
              "If-Match": submitted.etag,
            },
          },
        );
        status(response.status, 200);
        const resource = versionedCharacter(
          response.data,
          response.etag ?? null,
        );
        if (resource.version <= submitted.version) {
          throw new CharacterContractError();
        }
        return resource;
      } catch (error) {
        if (shouldClearCharacterSession(error)) session.clear();
        if (started && isIndeterminateCharacterWrite(error)) {
          throw characterWriteOutcomeUnknown("save");
        }
        throw normalizeCharacterApiError(error, submitted.version);
      }
    },
  };
}

export const characterApiClient = createCharacterApiClient();
