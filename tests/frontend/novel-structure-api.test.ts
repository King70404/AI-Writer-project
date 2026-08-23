import { afterEach, describe, expect, it, vi } from "vitest";

import type { SecuritySessionManager } from "../../frontend/src/api/security-session";
import {
  createNovelStructureApiClient,
  NovelStructureApiError,
} from "../../frontend/src/features/novel-structure/api/client";
import {
  fieldError,
  normalizeStructureSummary,
  normalizeStructureTitle,
  validateStructureInput,
} from "../../frontend/src/features/novel-structure/validation";
import {
  chapterId,
  chapterResponse,
  outlineId,
  outlineResponse,
  secondChapterId,
  secondVolumeId,
  structureErrorEnvelope,
  structureJsonResponse,
  structureProjectId,
  volumeId,
  volumeResponse,
} from "./novel-structure-support";

function session(): SecuritySessionManager {
  return {
    getValidSession: vi.fn().mockResolvedValue({
      csrfToken: "csrf-token-for-novel-structure-tests",
      expiresAtMilliseconds: Date.now() + 60_000,
    }),
    clear: vi.fn(),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("Novel Structure validation", () => {
  it("normalizes bounded text and reports precise fields", () => {
    expect(normalizeStructureTitle("  标题  ")).toBe("标题");
    expect(normalizeStructureSummary("甲\r\n乙\r丙")).toBe("甲\n乙\n丙");
    expect(validateStructureInput("标题", "梗概", 1)).toEqual([]);
    const errors = validateStructureInput("\u0000", "\u2028", 0);
    expect(errors.map((error) => error.field)).toEqual([
      "title",
      "summary",
      "position",
    ]);
    expect(fieldError(errors, "position")).toBe("顺序必须是正整数。");
    expect(fieldError(errors, "title")).toContain("120");
    expect(fieldError([], "summary")).toBeNull();
  });

  it("rejects non-text, oversized text, and unsafe positions", () => {
    expect(validateStructureInput(null, null, Number.NaN)).toHaveLength(3);
    expect(
      validateStructureInput("x".repeat(121), "x".repeat(2_001), 1.5),
    ).toHaveLength(3);
    expect(
      validateStructureInput("标题", "", Number.MAX_SAFE_INTEGER + 1),
    ).toHaveLength(1);
  });
});

describe("Novel Structure API client", () => {
  it("executes all read and write contracts with CSRF, Location, and strong ETags", async () => {
    const responses = [
      structureJsonResponse(outlineResponse(), { etag: '"1"' }),
      structureJsonResponse(
        outlineResponse(1, { title: "新标题", summary: "甲\n乙" }),
        { status: 201, etag: '"1"' },
      ),
      structureJsonResponse(outlineResponse(2), { etag: '"2"' }),
      structureJsonResponse([
        volumeResponse(),
        volumeResponse(1, {
          volume_id: secondVolumeId,
          position: 2,
          title: "第二卷",
        }),
      ]),
      structureJsonResponse(volumeResponse(), { etag: '"1"' }),
      structureJsonResponse(volumeResponse(), {
        status: 201,
        etag: '"1"',
        location: `/api/v1/volumes/${volumeId}`,
      }),
      structureJsonResponse(volumeResponse(2), { etag: '"2"' }),
      structureJsonResponse([
        chapterResponse(),
        chapterResponse(1, {
          chapter_id: secondChapterId,
          position: 2,
          title: "第二章",
        }),
      ]),
      structureJsonResponse(chapterResponse(), { etag: '"1"' }),
      structureJsonResponse(chapterResponse(), {
        status: 201,
        etag: '"1"',
        location: `/api/v1/chapters/${chapterId}`,
      }),
      structureJsonResponse(chapterResponse(2), { etag: '"2"' }),
    ];
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockImplementation(() => Promise.resolve(responses.shift()!));
    vi.stubGlobal("fetch", fetchMock);
    const security = session();
    const client = createNovelStructureApiClient(security);
    const text = { title: "  新标题  ", summary: "甲\r\n乙" };
    const positioned = { ...text, position: 2 };

    expect((await client.getOutline(structureProjectId)).etag).toBe('"1"');
    expect(
      (await client.createOutline(structureProjectId, text)).resource.title,
    ).toBe("新标题");
    expect(
      (await client.updateOutline(outlineId, structureProjectId, text, '"1"'))
        .version,
    ).toBe(2);
    expect(
      (await client.listVolumes(structureProjectId)).map(
        (item) => item.position,
      ),
    ).toEqual([1, 2]);
    expect(
      (await client.getVolume(volumeId, structureProjectId)).resource.volume_id,
    ).toBe(volumeId);
    await client.createVolume(structureProjectId, positioned);
    await client.updateVolume(volumeId, structureProjectId, positioned, '"1"');
    expect(
      (await client.listChapters(structureProjectId, volumeId)).map(
        (item) => item.position,
      ),
    ).toEqual([1, 2]);
    expect(
      (await client.getChapter(chapterId, structureProjectId, volumeId))
        .resource.chapter_id,
    ).toBe(chapterId);
    await client.createChapter(structureProjectId, volumeId, positioned);
    await client.updateChapter(
      chapterId,
      structureProjectId,
      volumeId,
      positioned,
      '"1"',
    );

    expect(fetchMock).toHaveBeenCalledTimes(11);
    const requests = fetchMock.mock.calls.map((call) => call[1]);
    expect(
      requests.filter(
        (init) => init?.method === "POST" || init?.method === "PUT",
      ),
    ).toHaveLength(6);
    expect(requests.at(-1)?.headers).toEqual(expect.any(Headers));
    expect((requests.at(-1)?.headers as Headers).get("If-Match")).toBe('"1"');
    expect(security.getValidSession).toHaveBeenCalledTimes(6);
  });

  it.each([
    ["getOutline", ["bad"]],
    ["getVolume", ["bad", structureProjectId]],
    ["getChapter", ["bad", structureProjectId, volumeId]],
    ["listChapters", [structureProjectId, "bad"]],
  ] as const)(
    "rejects invalid identities before %s sends a request",
    async (method, args) => {
      const fetchMock = vi.fn<typeof fetch>();
      vi.stubGlobal("fetch", fetchMock);
      const client = createNovelStructureApiClient(session());
      await expect(
        Promise.resolve().then(() =>
          (
            client[method] as unknown as (
              ...values: string[]
            ) => Promise<unknown>
          )(...args),
        ),
      ).rejects.toMatchObject({ kind: "validation" });
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("rejects invalid input without acquiring a security session", async () => {
    const security = session();
    const client = createNovelStructureApiClient(security);
    const error: unknown = await client
      .createVolume(structureProjectId, {
        title: "",
        summary: "",
        position: 0,
      })
      .catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(NovelStructureApiError);
    expect(error).toMatchObject({ kind: "validation" });
    expect(
      (error as NovelStructureApiError).fieldErrors.length,
    ).toBeGreaterThan(0);
    expect(security.getValidSession).not.toHaveBeenCalled();
  });

  it.each([
    [structureJsonResponse({}), "contract"],
    [structureJsonResponse(outlineResponse(), { etag: 'W/"1"' }), "contract"],
    [structureJsonResponse(outlineResponse(2), { etag: '"1"' }), "contract"],
    [
      structureJsonResponse([
        volumeResponse(1, { position: 2 }),
        volumeResponse(1, { volume_id: secondVolumeId, position: 1 }),
      ]),
      "contract",
    ],
  ] as const)(
    "fails closed for malformed response contracts",
    async (response, kind) => {
      vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(response));
      const client = createNovelStructureApiClient(session());
      const operation = Array.isArray(JSON.parse(await response.clone().text()))
        ? client.listVolumes(structureProjectId)
        : client.getOutline(structureProjectId);
      await expect(operation).rejects.toMatchObject({ kind });
    },
  );

  it.each([
    ["PROJECT_NOT_FOUND", 404, "project_not_found"],
    ["OUTLINE_NOT_FOUND", 404, "outline_not_found"],
    ["VOLUME_NOT_FOUND", 404, "not_found"],
    ["OUTLINE_ALREADY_EXISTS", 409, "already_exists"],
    ["VOLUME_POSITION_CONFLICT", 409, "position_conflict"],
    ["CHAPTER_VOLUME_OWNERSHIP_MISMATCH", 409, "ownership_conflict"],
    ["OUTLINE_VERSION_CONFLICT", 412, "conflict"],
    ["SESSION_EXPIRED", 401, "security"],
    ["INVALID_NOVEL_STRUCTURE_TITLE", 422, "validation"],
    ["NOVEL_STRUCTURE_PERSISTENCE_UNAVAILABLE", 503, "unavailable"],
  ] as const)("maps %s to a safe %s error", async (code, status, kind) => {
    const security = session();
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          structureJsonResponse(structureErrorEnvelope(code), { status }),
        ),
    );
    const client = createNovelStructureApiClient(security);
    const operation =
      status === 401
        ? client.createOutline(structureProjectId, {
            title: "标题",
            summary: "",
          })
        : client.getOutline(structureProjectId);
    const error: unknown = await operation.catch((reason: unknown) => reason);
    expect(error).toMatchObject({ kind });
    expect(error).not.toHaveProperty(
      "message",
      expect.stringMatching(/SECRET_CANARY/u),
    );
    expect(security.clear).toHaveBeenCalledTimes(status === 401 ? 1 : 0);
  });

  it("marks transport failure after submission as outcome unknown", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockRejectedValue(new TypeError("private transport")),
    );
    const client = createNovelStructureApiClient(session());
    await expect(
      client.createOutline(structureProjectId, { title: "标题", summary: "" }),
    ).rejects.toMatchObject({ kind: "outcome_unknown" });
  });

  it("preserves already-normalized safe errors and maps aborts and hostile failures", async () => {
    const client = createNovelStructureApiClient(session());
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockRejectedValue(new DOMException("private", "AbortError")),
    );
    await expect(client.getOutline(structureProjectId)).rejects.toMatchObject({
      kind: "aborted",
    });
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockRejectedValue({
        toString: () => {
          throw new Error("must not run");
        },
      }),
    );
    await expect(client.getOutline(structureProjectId)).rejects.toMatchObject({
      kind: "unknown",
    });
    const existing = new NovelStructureApiError({
      kind: "not_found",
      code: "SAFE",
      message: "安全",
    });
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(existing));
    await expect(client.getOutline(structureProjectId)).rejects.toBe(existing);
  });
});
