import { describe, expect, it } from "vitest";

import { parseStrongVersionEtag } from "../../frontend/src/api/etags";
import type { CharacterListItemResponse } from "../../frontend/src/features/character/api/contracts";
import {
  characterItemsAreDescending,
  characterListItemFromResponse,
  isCanonicalCharacterId,
  isCanonicalCharacterProjectId,
  parseCharacterListPageResponse,
  parseCharacterResponse,
} from "../../frontend/src/features/character/api/parsers";
import { versionedCharacter as wrapCharacter } from "../../frontend/src/features/character/api/etags";
import {
  normalizeCharacterName,
  normalizeCharacterProfile,
  normalizeCharacterRole,
  validateCharacterInput,
} from "../../frontend/src/features/character/validation";
import {
  characterId,
  characterListItem,
  characterPage,
  characterProjectId,
  characterResponse,
  olderCharacterTimestamp,
  secondCharacterId,
} from "./character-support";

describe("Character strict frontend contracts", () => {
  it("parses a complete resource, wraps a matching shared strong ETag, and maps a summary", () => {
    const parsed = parseCharacterResponse(
      characterResponse(),
      characterProjectId,
      characterId,
    );
    expect(parsed.profile).toContain("秘密档案");
    expect(wrapCharacter(parsed, '"1"')).toEqual({
      character: parsed,
      etag: '"1"',
      version: 1,
    });
    expect(characterListItemFromResponse(parsed)).not.toHaveProperty("profile");
  });

  it.each([
    ["extra key", { ...characterResponse(), extra: true }],
    ["missing key", (({ profile: _, ...rest }) => rest)(characterResponse())],
    ["bad project", characterResponse(1, { project_id: "bad" })],
    ["bad character", characterResponse(1, { character_id: "bad" })],
    ["bad revision", characterResponse(1, { current_revision_id: "bad" })],
    ["zero version", characterResponse(1, { concurrency_version: 0 })],
    ["float revision", characterResponse(1, { revision_number: 1.5 })],
    ["version mismatch", characterResponse(1, { concurrency_version: 2 })],
    ["noncanonical name", characterResponse(1, { name: " 林砚 " })],
    ["noncanonical role", characterResponse(1, { role: " 主角 " })],
    ["noncanonical profile", characterResponse(1, { profile: "a\r\nb" })],
    ["naive time", characterResponse(1, { updated_at: "2026-07-30T08:30:00" })],
    [
      "time mismatch",
      characterResponse(1, { head_updated_at: "2026-07-30T08:31:00Z" }),
    ],
    [
      "creation after update",
      characterResponse(1, {
        created_at: "2026-07-31T08:30:00Z",
      }),
    ],
  ])("rejects a current resource with %s", (_label, value) => {
    expect(() =>
      parseCharacterResponse(value, characterProjectId, characterId),
    ).toThrow("Character API response");
  });

  it("rejects identity mismatches without exposing response content", () => {
    expect(() =>
      parseCharacterResponse(
        characterResponse(),
        characterProjectId,
        secondCharacterId,
      ),
    ).toThrow();
  });

  it("parses a profile-free, Project-bound, descending page", () => {
    const page = parseCharacterListPageResponse(
      characterPage({
        items: [
          characterListItem(),
          characterListItem({
            character_id: secondCharacterId,
            current_revision_id: "crv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
            created_at: olderCharacterTimestamp,
            updated_at: olderCharacterTimestamp,
          }),
        ],
        next_cursor: "opaque-cursor",
        has_more: true,
      }),
      characterProjectId,
    );
    expect(page.items).toHaveLength(2);
    expect(page).not.toHaveProperty("total");
    expect(page.items[0]).not.toHaveProperty("profile");
    expect(characterItemsAreDescending(page.items)).toBe(true);
  });

  it.each([
    ["extra page key", { ...characterPage(), total: 1 }],
    [
      "project mismatch",
      characterPage({ project_id: "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW" }),
    ],
    ["cursor mismatch", characterPage({ next_cursor: "x", has_more: false })],
    [
      "empty continuation",
      characterPage({ items: [], next_cursor: "x", has_more: true }),
    ],
    [
      "profile leak",
      characterPage({
        items: [
          {
            ...characterListItem(),
            profile: "secret",
          } as CharacterListItemResponse,
        ],
      }),
    ],
    [
      "duplicate",
      characterPage({ items: [characterListItem(), characterListItem()] }),
    ],
    [
      "wrong order",
      characterPage({
        items: [
          characterListItem({
            created_at: olderCharacterTimestamp,
            updated_at: olderCharacterTimestamp,
          }),
          characterListItem({
            character_id: secondCharacterId,
            current_revision_id: "crv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
          }),
        ],
      }),
    ],
  ])("rejects a list page with %s", (_label, page) => {
    expect(() =>
      parseCharacterListPageResponse(page, characterProjectId),
    ).toThrow();
  });

  it("validates canonical IDs, fields, and LF normalization", () => {
    expect(isCanonicalCharacterProjectId(characterProjectId)).toBe(true);
    expect(isCanonicalCharacterId(characterId)).toBe(true);
    expect(isCanonicalCharacterId(characterId.toLowerCase())).toBe(false);
    expect(normalizeCharacterName("  林砚  ")).toBe("林砚");
    expect(normalizeCharacterRole(" 主角 ")).toBe("主角");
    expect(normalizeCharacterProfile("a\r\nb\rc")).toBe("a\nb\nc");
    expect(validateCharacterInput("林砚", "", "")).toEqual([]);
    expect(validateCharacterInput("", "a\u0000", "b\u0000")).toHaveLength(3);
    expect(validateCharacterInput("x".repeat(121), "", "")[0]?.field).toBe(
      "name",
    );
  });

  it.each([
    null,
    'W/"1"',
    "*",
    '"1", "2"',
    "1",
    '""',
    '"0"',
    '"-1"',
    '"1.0"',
    '"1e2"',
    '"01"',
    '"9007199254740992"',
  ])("keeps the shared strong ETag parser strict for %j", (etag) => {
    expect(() => parseStrongVersionEtag(etag)).toThrow();
  });

  it("rejects missing or mismatched Character ETags", () => {
    expect(() => wrapCharacter(characterResponse(), null)).toThrow();
    expect(() => wrapCharacter(characterResponse(), '"2"')).toThrow();
  });
});
