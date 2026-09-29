import { describe, expect, it } from "vitest";

import { ApiError } from "../../frontend/src/api/errors";
import {
  isIndeterminateWriteFailure,
  normalizeStoryBibleApiError,
  shouldClearStoryBibleSecuritySession,
  StoryBibleApiError,
  storyBibleContractError,
  storyBibleOutcomeUnknownError,
} from "../../frontend/src/features/story-bible/api/errors";
import { StoryBibleContractError } from "../../frontend/src/features/story-bible/api/parsers";

function apiError(
  status: number,
  code: string,
  details: Readonly<Record<string, unknown>> = {},
  requestId: string | null = "req_safe",
): ApiError {
  return new ApiError({
    status,
    code,
    message: "STORY_BIBLE_FRONTEND_SECRET_CANARY",
    details,
    retryable: false,
    suggestedAction: "private",
    requestId,
  });
}

describe("Story Bible safe error normalization", () => {
  it.each([
    [403, "ORIGIN_NOT_ALLOWED", "security", "当前页面来源未通过安全验证。"],
    [401, "OTHER_SECURITY", "security", "安全会话无效，请检查后手动重新提交。"],
    [404, "PROJECT_NOT_FOUND", "project_not_found", "指定项目不存在。"],
    [
      404,
      "STORY_BIBLE_NOT_FOUND",
      "story_bible_not_found",
      "指定小说设定不存在。",
    ],
    [
      404,
      "STORY_BIBLE_FOR_PROJECT_NOT_FOUND",
      "story_bible_for_project_not_found",
      "该项目尚未创建小说设定。",
    ],
    [
      409,
      "STORY_BIBLE_ALREADY_EXISTS_FOR_PROJECT",
      "already_exists",
      "该项目已经存在小说设定，请重新读取。",
    ],
    [413, "REQUEST_TOO_LARGE", "validation", "提交内容超过服务允许的大小。"],
    [
      422,
      "REQUEST_VALIDATION_ERROR",
      "validation",
      "小说设定内容未通过服务端验证。",
    ],
    [
      503,
      "STORY_BIBLE_SERVICE_UNAVAILABLE",
      "unavailable",
      "小说设定服务暂时不可用，请稍后手动重试。",
    ],
    [
      415,
      "UNSUPPORTED_MEDIA_TYPE",
      "contract",
      "小说设定服务返回了无法安全读取的数据。",
    ],
    [
      428,
      "PRECONDITION_REQUIRED",
      "contract",
      "小说设定服务返回了无法安全读取的数据。",
    ],
    [
      500,
      "UNCLASSIFIED_ERROR",
      "unknown",
      "小说设定请求未能完成，请稍后手动重试。",
    ],
  ] as const)(
    "maps %s %s without exposing the source message",
    (status, code, kind, message) => {
      const normalized = normalizeStoryBibleApiError(apiError(status, code));
      expect(normalized).toMatchObject({
        kind,
        code,
        message,
        requestId: "req_safe",
      });
      expect(String(normalized)).not.toContain(
        "STORY_BIBLE_FRONTEND_SECRET_CANARY",
      );
    },
  );

  it("normalizes safe field aliases, ignores hostile shapes, and deduplicates", () => {
    const normalized = normalizeStoryBibleApiError(
      apiError(422, "REQUEST_VALIDATION_ERROR", {
        field: "body.title",
        errors: [
          { field: "title" },
          { field: "body.content" },
          { field: "other" },
          null,
          [],
          "content",
        ],
      }),
    );
    expect(normalized.fieldErrors).toEqual([
      {
        field: "title",
        message: "小说设定标题未通过服务端验证。",
      },
      {
        field: "content",
        message: "小说设定正文未通过服务端验证。",
      },
    ]);
  });

  it.each([null, "bad request id\ncanary", "x".repeat(129)])(
    "drops an unsafe request ID %#",
    (requestId) => {
      expect(
        normalizeStoryBibleApiError(
          apiError(503, "STORY_BIBLE_SERVICE_UNAVAILABLE", {}, requestId),
        ).requestId,
      ).toBeNull();
    },
  );

  it("preserves an existing safe Story Bible error and classifies local failures", () => {
    const existing = new StoryBibleApiError({
      kind: "validation",
      code: "LOCAL",
      message: "safe",
    });
    expect(normalizeStoryBibleApiError(existing)).toBe(existing);
    expect(
      normalizeStoryBibleApiError(new DOMException("private", "AbortError")),
    ).toMatchObject({ kind: "aborted", code: "REQUEST_ABORTED" });
    expect(
      normalizeStoryBibleApiError(new StoryBibleContractError()),
    ).toMatchObject({ kind: "contract" });
    expect(normalizeStoryBibleApiError(new TypeError("private"))).toMatchObject(
      { kind: "network" },
    );
    expect(normalizeStoryBibleApiError({ hostile: true })).toMatchObject({
      kind: "unknown",
      code: "UNKNOWN_STORY_BIBLE_ERROR",
    });
  });

  it("builds both outcome-unknown operations with stable messages", () => {
    expect(storyBibleOutcomeUnknownError("create")).toMatchObject({
      kind: "outcome_unknown",
      code: "STORY_BIBLE_CREATE_OUTCOME_UNKNOWN",
      message: "创建结果未确认，请重新读取小说设定核实。",
    });
    expect(storyBibleOutcomeUnknownError("save")).toMatchObject({
      kind: "outcome_unknown",
      code: "STORY_BIBLE_SAVE_OUTCOME_UNKNOWN",
      message: "保存结果未确认，请重新读取小说设定核实。",
    });
    expect(storyBibleContractError()).toMatchObject({ kind: "contract" });
  });

  it("identifies every indeterminate write category without widening it", () => {
    const candidates: readonly [unknown, boolean][] = [
      [new StoryBibleContractError(), true],
      [storyBibleContractError(), true],
      [new DOMException("private", "AbortError"), true],
      [new TypeError("private"), true],
      [apiError(500, "SERVER_ERROR"), true],
      [apiError(400, "INVALID_RESPONSE"), true],
      [apiError(422, "REQUEST_VALIDATION_ERROR"), false],
      [new Error("ordinary"), false],
    ];
    expect(
      candidates.map(([candidate]) => isIndeterminateWriteFailure(candidate)),
    ).toEqual(candidates.map(([, expected]) => expected));
  });

  it("clears only server-declared security failures", () => {
    const candidates: readonly [unknown, boolean][] = [
      [apiError(403, "CSRF_TOKEN_INVALID"), true],
      [apiError(401, "OTHER"), true],
      [apiError(403, "OTHER"), true],
      [apiError(422, "REQUEST_VALIDATION_ERROR"), false],
      [new TypeError("private"), false],
    ];
    expect(
      candidates.map(([candidate]) =>
        shouldClearStoryBibleSecuritySession(candidate),
      ),
    ).toEqual(candidates.map(([, expected]) => expected));
  });
});
