import { isCanonicalPrefixedUlid } from "../../../api/identifiers";
import {
  normalizeCharacterName,
  normalizeCharacterProfile,
  normalizeCharacterRole,
  validateCharacterInput,
} from "../validation";

import type {
  CharacterListItemResponse,
  CharacterListPageResponse,
  CharacterResponse,
} from "./contracts";

export class CharacterContractError extends Error {
  public constructor() {
    super("Character API response did not match its contract.");
    this.name = "CharacterContractError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return (
    actual.length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function positiveInteger(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value <= 0) {
    throw new CharacterContractError();
  }
  return value;
}

const AWARE_RFC3339 =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u;

function timestamp(value: unknown): string {
  if (
    typeof value !== "string" ||
    value.length > 64 ||
    !AWARE_RFC3339.test(value) ||
    !Number.isFinite(Date.parse(value))
  ) {
    throw new CharacterContractError();
  }
  return value;
}

function identifier(value: unknown, prefix: "prj" | "chr" | "crv"): string {
  if (!isCanonicalPrefixedUlid(value, prefix)) {
    throw new CharacterContractError();
  }
  return value;
}

export function isCanonicalCharacterProjectId(value: unknown): value is string {
  return isCanonicalPrefixedUlid(value, "prj");
}

export function isCanonicalCharacterId(value: unknown): value is string {
  return isCanonicalPrefixedUlid(value, "chr");
}

function canonicalText(
  name: unknown,
  role: unknown,
  profile: unknown,
): { readonly name: string; readonly role: string; readonly profile: string } {
  if (
    typeof name !== "string" ||
    typeof role !== "string" ||
    typeof profile !== "string" ||
    validateCharacterInput(name, role, profile).length > 0 ||
    normalizeCharacterName(name) !== name ||
    normalizeCharacterRole(role) !== role ||
    normalizeCharacterProfile(profile) !== profile
  ) {
    throw new CharacterContractError();
  }
  return { name, role, profile };
}

const CHARACTER_KEYS = [
  "character_id",
  "project_id",
  "current_revision_id",
  "revision_number",
  "concurrency_version",
  "name",
  "role",
  "profile",
  "created_at",
  "updated_at",
  "revision_created_at",
  "head_updated_at",
] as const;

export function parseCharacterResponse(
  value: unknown,
  expectedProjectId: string,
  expectedCharacterId?: string,
): CharacterResponse {
  if (!isRecord(value) || !exactKeys(value, CHARACTER_KEYS)) {
    throw new CharacterContractError();
  }
  const characterId = identifier(value.character_id, "chr");
  const projectId = identifier(value.project_id, "prj");
  const revision = positiveInteger(value.revision_number);
  const version = positiveInteger(value.concurrency_version);
  const text = canonicalText(value.name, value.role, value.profile);
  const createdAt = timestamp(value.created_at);
  const updatedAt = timestamp(value.updated_at);
  const revisionCreatedAt = timestamp(value.revision_created_at);
  const headUpdatedAt = timestamp(value.head_updated_at);
  if (
    projectId !== expectedProjectId ||
    (expectedCharacterId !== undefined &&
      characterId !== expectedCharacterId) ||
    revision !== version ||
    Date.parse(createdAt) > Date.parse(updatedAt) ||
    Date.parse(updatedAt) !== Date.parse(revisionCreatedAt) ||
    Date.parse(updatedAt) !== Date.parse(headUpdatedAt)
  ) {
    throw new CharacterContractError();
  }
  return {
    character_id: characterId,
    project_id: projectId,
    current_revision_id: identifier(value.current_revision_id, "crv"),
    revision_number: revision,
    concurrency_version: version,
    ...text,
    created_at: createdAt,
    updated_at: updatedAt,
    revision_created_at: revisionCreatedAt,
    head_updated_at: headUpdatedAt,
  };
}

const ITEM_KEYS = [
  "character_id",
  "current_revision_id",
  "revision_number",
  "concurrency_version",
  "name",
  "role",
  "created_at",
  "updated_at",
] as const;

function parseListItem(value: unknown): CharacterListItemResponse {
  if (!isRecord(value) || !exactKeys(value, ITEM_KEYS)) {
    throw new CharacterContractError();
  }
  const revision = positiveInteger(value.revision_number);
  const version = positiveInteger(value.concurrency_version);
  const text = canonicalText(value.name, value.role, "");
  const createdAt = timestamp(value.created_at);
  const updatedAt = timestamp(value.updated_at);
  if (revision !== version || Date.parse(createdAt) > Date.parse(updatedAt)) {
    throw new CharacterContractError();
  }
  return {
    character_id: identifier(value.character_id, "chr"),
    current_revision_id: identifier(value.current_revision_id, "crv"),
    revision_number: revision,
    concurrency_version: version,
    name: text.name,
    role: text.role,
    created_at: createdAt,
    updated_at: updatedAt,
  };
}

const PAGE_KEYS = ["project_id", "items", "next_cursor", "has_more"] as const;

function isDescending(
  previous: CharacterListItemResponse,
  current: CharacterListItemResponse,
): boolean {
  const timeOrder = previous.created_at.localeCompare(current.created_at);
  return (
    timeOrder > 0 ||
    (timeOrder === 0 &&
      previous.character_id.localeCompare(current.character_id) > 0)
  );
}

export function parseCharacterListPageResponse(
  value: unknown,
  expectedProjectId: string,
): CharacterListPageResponse {
  if (
    !isRecord(value) ||
    !exactKeys(value, PAGE_KEYS) ||
    !Array.isArray(value.items) ||
    typeof value.has_more !== "boolean" ||
    (value.next_cursor !== null &&
      (typeof value.next_cursor !== "string" ||
        value.next_cursor.length < 1 ||
        value.next_cursor.length > 512))
  ) {
    throw new CharacterContractError();
  }
  const projectId = identifier(value.project_id, "prj");
  const items = value.items.map(parseListItem);
  const ids = new Set<string>();
  for (const [index, item] of items.entries()) {
    if (
      ids.has(item.character_id) ||
      (index > 0 && !isDescending(items[index - 1], item))
    ) {
      throw new CharacterContractError();
    }
    ids.add(item.character_id);
  }
  if (
    projectId !== expectedProjectId ||
    value.has_more !== (value.next_cursor !== null) ||
    (items.length === 0 && value.has_more)
  ) {
    throw new CharacterContractError();
  }
  return {
    project_id: projectId,
    items,
    next_cursor: value.next_cursor,
    has_more: value.has_more,
  };
}

export function characterListItemFromResponse(
  character: CharacterResponse,
): CharacterListItemResponse {
  return parseListItem({
    character_id: character.character_id,
    current_revision_id: character.current_revision_id,
    revision_number: character.revision_number,
    concurrency_version: character.concurrency_version,
    name: character.name,
    role: character.role,
    created_at: character.created_at,
    updated_at: character.updated_at,
  });
}

export function characterItemsAreDescending(
  items: readonly CharacterListItemResponse[],
): boolean {
  return items.every(
    (item, index) => index === 0 || isDescending(items[index - 1], item),
  );
}
