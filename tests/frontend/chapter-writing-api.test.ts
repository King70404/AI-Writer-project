import { afterEach, describe, expect, it, vi } from "vitest";

import type { SecuritySessionManager } from "../../frontend/src/api/security-session";
import { createNovelStructureApiClient } from "../../frontend/src/features/novel-structure/api/client";
import {
  isManuscript,
  normalizeManuscript,
  parseChapterContent,
} from "../../frontend/src/features/novel-structure/api/content";
import {
  chapterId,
  chapterResponse,
  structureJsonResponse,
  structureProjectId,
  structureErrorEnvelope,
} from "./novel-structure-support";
import { contentResponse } from "./chapter-writing-support";

const session = (): SecuritySessionManager => ({
  getValidSession: vi.fn().mockResolvedValue({
    csrfToken: "chapter-writing-test-proof",
    expiresAtMilliseconds: 100_000,
  }),
  clear: vi.fn(),
});
afterEach(() => vi.unstubAllGlobals());

describe("Chapter manuscript client", () => {
  it("reads structure without a known volume and uses real ETags for complete content writes", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        structureJsonResponse(chapterResponse(), { etag: '"1"' }),
      )
      .mockResolvedValueOnce(
        structureJsonResponse(contentResponse(), { etag: '"1"' }),
      )
      .mockResolvedValueOnce(
        structureJsonResponse(contentResponse("甲\n\t乙", 2), { etag: '"2"' }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const client = createNovelStructureApiClient(session());
    expect(
      (await client.getChapter(chapterId, structureProjectId)).resource
        .chapter_id,
    ).toBe(chapterId);
    const initial = await client.getChapterContent(
      chapterId,
      structureProjectId,
    );
    expect(initial.etag).toBe('"1"');
    const next = await client.updateChapterContent(
      chapterId,
      structureProjectId,
      "甲\r\n\t乙",
      initial.etag,
    );
    expect(next.etag).toBe('"2"');
    expect(next.resource.content).toBe("甲\n\t乙");
    expect(Object.isFrozen(next.resource)).toBe(true);
    expect(fetchMock.mock.calls[2][0]).toBe(
      `/api/v1/chapters/${chapterId}/content`,
    );
    const init = fetchMock.mock.calls[2][1]!;
    expect(init.method).toBe("PUT");
    expect((init.headers as Headers).get("If-Match")).toBe('"1"');
    expect((init.headers as Headers).get("X-CSRF-Token")).toBe(
      "chapter-writing-test-proof",
    );
    expect(JSON.parse(init.body as string)).toEqual({ content: "甲\n\t乙" });
  });

  it.each([
    [412, "CHAPTER_VERSION_CONFLICT", "conflict"],
    [404, "CHAPTER_NOT_FOUND", "not_found"],
    [400, "INVALID_IF_MATCH", "validation"],
    [428, "IF_MATCH_REQUIRED", "validation"],
    [422, "INVALID_MANUSCRIPT_CONTENT", "validation"],
    [503, "UNAVAILABLE", "unavailable"],
  ] as const)(
    "safely identifies HTTP %s on both reads and writes",
    async (status, code, kind) => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn<typeof fetch>()
          .mockImplementation(() =>
            Promise.resolve(
              structureJsonResponse(structureErrorEnvelope(code), { status }),
            ),
          ),
      );
      const client = createNovelStructureApiClient(session());
      await expect(
        client.getChapterContent(chapterId, structureProjectId),
      ).rejects.toMatchObject({ kind });
      await expect(
        client.updateChapterContent(
          chapterId,
          structureProjectId,
          "本地稿",
          '"1"',
        ),
      ).rejects.toMatchObject({ kind });
    },
  );

  it("keeps network failure distinguishable from a conflict without retry", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new TypeError("WRITING_PRIVATE_CANARY"));
    vi.stubGlobal("fetch", request);
    const client = createNovelStructureApiClient(session());
    await expect(
      client.getChapterContent(chapterId, structureProjectId),
    ).rejects.toMatchObject({ kind: "unknown" });
    await expect(
      client.updateChapterContent(chapterId, structureProjectId, "稿", '"1"'),
    ).rejects.toMatchObject({ kind: "outcome_unknown" });
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("rejects invalid input before transport", async () => {
    const request = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", request);
    const client = createNovelStructureApiClient(session());
    await expect(
      client.getChapterContent("bad", structureProjectId),
    ).rejects.toMatchObject({ kind: "validation" });
    await expect(
      client.getChapterContent(chapterId, "bad"),
    ).rejects.toMatchObject({ kind: "validation" });
    await expect(
      client.updateChapterContent("bad", structureProjectId, "", '"1"'),
    ).rejects.toMatchObject({ kind: "validation" });
    await expect(
      client.updateChapterContent(chapterId, "bad", "", '"1"'),
    ).rejects.toMatchObject({ kind: "validation" });
    await expect(
      client.updateChapterContent(
        chapterId,
        structureProjectId,
        "\u0000",
        '"1"',
      ),
    ).rejects.toMatchObject({ kind: "validation" });
    await expect(
      client.updateChapterContent(chapterId, structureProjectId, "", 'W/"1"'),
    ).rejects.toMatchObject({ kind: "validation" });
    expect(request).not.toHaveBeenCalled();
  });

  it.each([
    null,
    [],
    1,
    {},
    { ...contentResponse(), extra: true },
    { ...contentResponse(), content: undefined },
    { ...contentResponse(), chapter_id: "bad" },
    { ...contentResponse(), project_id: "bad" },
    { ...contentResponse(), volume_id: "bad" },
    { ...contentResponse(), current_revision_id: "bad" },
    { ...contentResponse(), revision_number: true },
    { ...contentResponse(), revision_number: 1.5 },
    { ...contentResponse(), revision_number: 0 },
    { ...contentResponse(), concurrency_version: 2 },
    { ...contentResponse(), content: "甲\r乙" },
    { ...contentResponse(), updated_at: null },
    { ...contentResponse(), updated_at: "bad" },
    { ...contentResponse(), updated_at: "2026-99-01T00:00:00Z" },
    { ...contentResponse(), revision_created_at: null },
    { ...contentResponse(), revision_created_at: "bad" },
    { ...contentResponse(), revision_created_at: "2026-08-23T09:00:00Z" },
  ])("rejects malformed snapshots without echoing content", (value) => {
    expect(() =>
      parseChapterContent(value, chapterId, structureProjectId),
    ).toThrow("Invalid Chapter content response.");
  });

  it.each([undefined, 'W/"1"', '"2"'])(
    "requires an exact matching strong response ETag",
    async (etag) => {
      vi.stubGlobal(
        "fetch",
        vi
          .fn<typeof fetch>()
          .mockImplementation(() =>
            Promise.resolve(structureJsonResponse(contentResponse(), { etag })),
          ),
      );
      const client = createNovelStructureApiClient(session());
      await expect(
        client.getChapterContent(chapterId, structureProjectId),
      ).rejects.toMatchObject({ kind: "contract" });
      await expect(
        client.updateChapterContent(chapterId, structureProjectId, "", '"1"'),
      ).rejects.toMatchObject({ kind: "contract" });
    },
  );

  it("accepts long plain text and rejects control characters without trimming", () => {
    expect(isManuscript("正文".repeat(50_000))).toBe(true);
    expect(isManuscript(" ")).toBe(true);
    expect(isManuscript("甲\n乙\t丙\r丁")).toBe(true);
    expect(normalizeManuscript(" 甲\r\n乙\r ")).toBe(" 甲\n乙\n ");
    for (const value of [
      null,
      "\u0000",
      "\u007f",
      "\u009f",
      "\u2028",
      "\u2029",
      "x".repeat(2_000_001),
    ])
      expect(isManuscript(value)).toBe(false);
  });
});
