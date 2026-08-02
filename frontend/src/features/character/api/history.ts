import { getJson } from "../../../api/client";

import type {
  CharacterRevisionHistoryPageResponse,
  CharacterRevisionResponse,
} from "./contracts";
import { CharacterApiError, normalizeCharacterApiError } from "./errors";
import {
  CharacterContractError,
  isCanonicalCharacterId,
  isCanonicalCharacterProjectId,
  parseCharacterRevisionHistoryPageResponse,
  parseCharacterRevisionResponse,
} from "./parsers";

export interface ListCharacterRevisionsOptions {
  readonly characterId: string;
  readonly expectedProjectId: string;
  readonly limit: number;
  readonly cursor?: string;
  readonly signal?: AbortSignal;
}

export interface GetCharacterRevisionOptions {
  readonly characterId: string;
  readonly expectedProjectId: string;
  readonly revisionNumber: number;
  readonly signal?: AbortSignal;
}

export interface CharacterRevisionHistoryApiClient {
  readonly listCharacterRevisions: (
    options: ListCharacterRevisionsOptions,
  ) => Promise<CharacterRevisionHistoryPageResponse>;
  readonly getCharacterRevision: (
    options: GetCharacterRevisionOptions,
  ) => Promise<CharacterRevisionResponse>;
}

function validationError(code: string, message: string): CharacterApiError {
  return new CharacterApiError({ kind: "validation", code, message });
}

function validateIdentity(characterId: string, projectId: string): void {
  if (!isCanonicalCharacterId(characterId)) {
    throw validationError("INVALID_CHARACTER_ID", "角色编号无效。");
  }
  if (!isCanonicalCharacterProjectId(projectId)) {
    throw validationError("INVALID_PROJECT_ID", "Project编号无效。");
  }
}

function requireStatus(actual: number | undefined, expected: number): void {
  if (actual !== expected) throw new CharacterContractError();
}

export const characterRevisionHistoryApiClient: CharacterRevisionHistoryApiClient =
  {
    async listCharacterRevisions(options) {
      validateIdentity(options.characterId, options.expectedProjectId);
      if (
        !Number.isSafeInteger(options.limit) ||
        options.limit < 1 ||
        options.limit > 100
      ) {
        throw validationError(
          "INVALID_HISTORY_LIMIT",
          "修订历史页大小必须是1至100的整数。",
        );
      }
      if (
        options.cursor !== undefined &&
        (typeof options.cursor !== "string" ||
          options.cursor.length === 0 ||
          options.cursor.length > 256)
      ) {
        throw validationError(
          "INVALID_CHARACTER_REVISION_CURSOR",
          "修订历史分页位置无效，请重新加载。",
        );
      }
      const query = new URLSearchParams({ limit: String(options.limit) });
      if (options.cursor !== undefined) query.set("cursor", options.cursor);
      try {
        const response = await getJson(
          `characters/${encodeURIComponent(options.characterId)}/revisions?${query.toString()}`,
          (value) =>
            parseCharacterRevisionHistoryPageResponse(
              value,
              options.characterId,
              options.expectedProjectId,
            ),
          { signal: options.signal },
        );
        requireStatus(response.status, 200);
        return response.data;
      } catch (error) {
        throw normalizeCharacterApiError(error);
      }
    },

    async getCharacterRevision(options) {
      validateIdentity(options.characterId, options.expectedProjectId);
      if (
        !Number.isSafeInteger(options.revisionNumber) ||
        options.revisionNumber < 1
      ) {
        throw validationError(
          "INVALID_CHARACTER_REVISION_NUMBER",
          "修订编号无效。",
        );
      }
      try {
        const response = await getJson(
          `characters/${encodeURIComponent(options.characterId)}/revisions/${options.revisionNumber}`,
          (value) =>
            parseCharacterRevisionResponse(
              value,
              options.characterId,
              options.expectedProjectId,
              options.revisionNumber,
            ),
          { signal: options.signal },
        );
        requireStatus(response.status, 200);
        return response.data;
      } catch (error) {
        throw normalizeCharacterApiError(error);
      }
    },
  };
