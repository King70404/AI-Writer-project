import { describe, expect, it } from "vitest";

import { isCanonicalPrefixedUlid } from "../../frontend/src/api/identifiers";
import {
  createVersionedStoryBibleResource,
  parseStoryBibleEtag,
} from "../../frontend/src/features/story-bible/api/etags";
import {
  parseStoryBibleResponse,
  StoryBibleContractError,
} from "../../frontend/src/features/story-bible/api/parsers";
import {
  normalizeStoryBibleContent,
  validateStoryBibleInput,
} from "../../frontend/src/features/story-bible/validation";
import {
  secondStoryProjectId,
  storyBibleId,
  storyBibleResponse,
  storyProjectId,
} from "./story-bible-support";

describe("Story Bible runtime contracts", () => {
  it("accepts the exact response and freezes a matching versioned resource", () => {
    const parsed = parseStoryBibleResponse(storyBibleResponse(), {
      expectedProjectId: storyProjectId,
      expectedStoryBibleId: storyBibleId,
    });
    const resource = createVersionedStoryBibleResource(parsed, '"1"');
    expect(resource).toMatchObject({ version: 1, etag: '"1"' });
    expect(Object.isFrozen(resource)).toBe(true);
    expect(Object.isFrozen(resource.storyBible)).toBe(true);
  });

  it("rejects a resource whose RevisionNumber differs from its ETag version", () => {
    expect(() =>
      createVersionedStoryBibleResource(storyBibleResponse(2), '"1"'),
    ).toThrow(StoryBibleContractError);
  });

  it.each([
    { extra: "field" },
    { story_bible_id: storyProjectId },
    { project_id: storyBibleId },
    { current_revision_id: "sbl_01ARZ3NDEKTSV4RRFFQ69G5FAV" },
    { revision_number: true },
    { revision_number: 1.5 },
    { concurrency_version: 0 },
    { concurrency_version: Number.MAX_SAFE_INTEGER + 1 },
    { revision_number: 2 },
    { title: "   " },
    { title: "标题\n注入" },
    { title: "😀".repeat(121) },
    { content: "正文\u0000" },
    { content: "界".repeat(50_001) },
    { content: "非规范\r换行" },
    { created_at: "2026-07-27T08:30:00" },
    { updated_at: "2026-07-27T08:29:59Z" },
    { revision_created_at: "2026-07-27T08:30:01Z" },
    { head_updated_at: "2026-07-27T08:30:01Z" },
  ])("rejects malformed or inconsistent response %#", (overrides) => {
    expect(() =>
      parseStoryBibleResponse(
        { ...storyBibleResponse(), ...overrides },
        { expectedProjectId: storyProjectId },
      ),
    ).toThrow(StoryBibleContractError);
  });

  it("rejects missing keys and context ownership mismatches", () => {
    const missing = { ...storyBibleResponse() } as Record<string, unknown>;
    delete missing.content;
    expect(() => parseStoryBibleResponse(missing)).toThrow(
      StoryBibleContractError,
    );
    expect(() =>
      parseStoryBibleResponse(storyBibleResponse(), {
        expectedProjectId: secondStoryProjectId,
      }),
    ).toThrow(StoryBibleContractError);
    expect(() =>
      parseStoryBibleResponse(storyBibleResponse(), {
        expectedStoryBibleId: "sbl_01ARZ3NDEKTSV4RRFFQ69G5FAW",
      }),
    ).toThrow(StoryBibleContractError);
  });

  it.each([
    null,
    "",
    "1",
    'W/"1"',
    "*",
    '"0"',
    '"-1"',
    '"1.0"',
    '"1e2"',
    '"01"',
    '"1", "2"',
    ' "1"',
    '"1" ',
    '"9223372036854775808"',
    '"9007199254740992"',
  ])("rejects unsafe ETag %s without echoing it", (etag) => {
    let thrown: unknown;
    try {
      parseStoryBibleEtag(etag);
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(StoryBibleContractError);
    expect(String(thrown)).toBe(
      "StoryBibleContractError: Story Bible API response did not match its contract.",
    );
  });

  it("reuses one prefixed ULID grammar for all four known prefixes", () => {
    expect(isCanonicalPrefixedUlid(storyProjectId, "prj")).toBe(true);
    expect(
      isCanonicalPrefixedUlid("prv_01ARZ3NDEKTSV4RRFFQ69G5FAV", "prv"),
    ).toBe(true);
    expect(isCanonicalPrefixedUlid(storyBibleId, "sbl")).toBe(true);
    expect(
      isCanonicalPrefixedUlid("sbr_01ARZ3NDEKTSV4RRFFQ69G5FAV", "sbr"),
    ).toBe(true);
    expect(
      isCanonicalPrefixedUlid({ toString: () => storyProjectId }, "prj"),
    ).toBe(false);
    expect(isCanonicalPrefixedUlid(storyProjectId.toLowerCase(), "prj")).toBe(
      false,
    );
  });

  it("validates code points, controls, and canonical LF without trimming content", () => {
    expect(validateStoryBibleInput(" 标题 ", "")).toEqual([]);
    expect(validateStoryBibleInput("😀".repeat(120), "\t正文\n")).toEqual([]);
    expect(validateStoryBibleInput(42, "")).toEqual([
      {
        field: "title",
        message: "Story Bible标题和正文必须是文本。",
      },
    ]);
    expect(validateStoryBibleInput("标题", null)[0]?.field).toBe("content");
    expect(validateStoryBibleInput("标题\u2028", "")[0]?.field).toBe("title");
    expect(validateStoryBibleInput("标题", "正文\u0085")[0]?.field).toBe(
      "content",
    );
    expect(normalizeStoryBibleContent(" a \r\n\tb\rc ")).toBe(" a \n\tb\nc ");
  });
});
