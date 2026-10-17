import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "../../frontend/src/api/errors";
import { securitySession } from "../../frontend/src/api/security-session";
import {
  memoryError,
  parseMemoryFact,
  parseMemoryReview,
  parseMemoryWorkspace,
  storyMemoryClient,
} from "../../frontend/src/features/novel-structure/api/story-memory";
import { chapterId, structureProjectId } from "./novel-structure-support";
import {
  memoryFact,
  memoryReview,
  memoryWorkspace,
} from "./story-memory-support";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
});
function rawFact() {
  return { ...memoryFact(), kind: "fact", updated_at: "2026-10-17T00:00:00Z" };
}
function rawReview() {
  return {
    ...memoryReview(),
    project_id: structureProjectId,
    kind: "review",
    revision_id: "review-revision",
    updated_at: "2026-10-17T00:00:00Z",
  };
}
function rawWorkspace() {
  return { ...memoryWorkspace(), facts: [rawFact()], reviews: [rawReview()] };
}
it("decodes persisted source-anchored facts and frozen review data", () => {
  expect(parseMemoryFact(rawFact(), structureProjectId)).toEqual(memoryFact());
  expect(parseMemoryReview(rawReview(), structureProjectId, chapterId)).toEqual(
    memoryReview(),
  );
  expect(
    parseMemoryWorkspace(rawWorkspace(), structureProjectId, chapterId),
  ).toEqual(memoryWorkspace());
});
it.each([
  { project_id: "other" },
  { kind: "other" },
  { id: "../escape" },
  { version: -1 },
  { stale: "false" },
  { status: "auto" },
  { quote: null },
])("rejects malformed fact ownership and status: %j", (patch) => {
  expect(() =>
    parseMemoryFact({ ...rawFact(), ...patch }, structureProjectId),
  ).toThrow("无法安全读取");
});
it.each([
  { project_id: "other" },
  { chapter_id: "other" },
  { status: "unknown" },
  { model: { ...memoryReview().model, kind: "other" } },
  { attempts: false },
  { last_error: [] },
])("rejects malformed review snapshots: %j", (patch) => {
  expect(() =>
    parseMemoryReview(
      { ...rawReview(), ...patch },
      structureProjectId,
      chapterId,
    ),
  ).toThrow("无法安全读取");
});
it("rejects fabricated review quotations and fact references", () => {
  const result = {
    summary: "x",
    facts: [],
    findings: [
      {
        quote: "编造",
        explanation: "x",
        instruction: "x",
        fact_ids: [] as string[],
      },
    ],
  };
  expect(() =>
    parseMemoryReview(
      { ...rawReview(), result },
      structureProjectId,
      chapterId,
    ),
  ).toThrow();
  result.findings = [
    {
      quote: "下雨",
      explanation: "x",
      instruction: "x",
      fact_ids: ["unknown"],
    },
  ];
  expect(() =>
    parseMemoryReview(
      { ...rawReview(), result },
      structureProjectId,
      chapterId,
    ),
  ).toThrow();
  expect(() =>
    parseMemoryWorkspace(
      { ...rawWorkspace(), facts: null },
      structureProjectId,
      chapterId,
    ),
  ).toThrow();
});
it("sends same-origin CSRF guarded mutations with exact versions and explicit consent", async () => {
  vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
    csrfToken: "test-proof",
    expiresAtMilliseconds: Date.now() + 60000,
  });
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json(rawFact()))
    .mockResolvedValueOnce(Response.json(rawFact()))
    .mockResolvedValueOnce(Response.json(rawReview()))
    .mockResolvedValueOnce(Response.json(rawReview()))
    .mockResolvedValueOnce(Response.json(rawWorkspace()));
  vi.stubGlobal("fetch", fetcher);
  const input = { ...memoryFact(), expected_version: 0 };
  await storyMemoryClient.fact(structureProjectId, chapterId, input);
  await storyMemoryClient.fact(
    structureProjectId,
    chapterId,
    input,
    "fact-one",
  );
  await storyMemoryClient.prepare(
    structureProjectId,
    chapterId,
    "chapter-revision-one",
    "profile-one",
  );
  await storyMemoryClient.send(
    structureProjectId,
    chapterId,
    memoryReview(),
    true,
  );
  await storyMemoryClient.workspace(structureProjectId, chapterId);
  const options = fetcher.mock.calls.map((call) => call[1] as RequestInit);
  expect(
    options
      .slice(0, 4)
      .every(
        (item) =>
          new Headers(item.headers).get("X-CSRF-Token") === "test-proof" &&
          item.credentials === "same-origin",
      ),
  ).toBe(true);
  expect(options[1].method).toBe("PUT");
  expect(JSON.parse(options[3].body as string)).toEqual({
    expected_version: 1,
    cloud_consent: true,
  });
  expect(options[4].method).toBe("GET");
});
it("does not retry network errors or display transport data and preserves consent session", async () => {
  const fetcher = vi.fn().mockRejectedValue(new Error("private details"));
  vi.stubGlobal("fetch", fetcher);
  await expect(
    storyMemoryClient.workspace(structureProjectId, chapterId),
  ).rejects.toThrow("不会自动重发");
  expect(fetcher).toHaveBeenCalledOnce();
  const error = new ApiError({
    code: "MEMORY_CONFLICT",
    status: 409,
    message: "private",
    details: {},
    retryable: false,
    suggestedAction: null,
    requestId: null,
  });
  expect(memoryError(error).message).toContain("草稿已保留");
  const clear = vi.spyOn(securitySession, "clear");
  memoryError(
    new ApiError({ ...error, status: 403, code: "MEMORY_CONSENT_REQUIRED" }),
  );
  expect(clear).not.toHaveBeenCalled();
  memoryError(new ApiError({ ...error, status: 401, code: "SESSION" }));
  expect(clear).toHaveBeenCalledOnce();
});
