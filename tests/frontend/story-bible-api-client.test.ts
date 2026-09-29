import { afterEach, describe, expect, it, vi } from "vitest";

import { createStoryBibleApiClient } from "../../frontend/src/features/story-bible/api/client";
import { securitySession } from "../../frontend/src/api/security-session";
import {
  csrfToken,
  secondStoryProjectId,
  storyBibleErrorEnvelope,
  storyBibleId,
  storyBibleJsonResponse,
  storyBibleResponse,
  storyProjectId,
} from "./story-bible-support";

function sessionManager() {
  return {
    getValidSession: vi.fn().mockResolvedValue({
      csrfToken,
      expiresAtMilliseconds: Date.now() + 60_000,
    }),
    clear: vi.fn<() => void>(),
  };
}

afterEach(() => {
  securitySession.clear();
  vi.unstubAllGlobals();
});

describe("Story Bible read clients", () => {
  it("uses one same-origin Project GET with no write context", async () => {
    const session = sessionManager();
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        storyBibleJsonResponse(storyBibleResponse(), { etag: '"1"' }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const resource = await createStoryBibleApiClient(
      session,
    ).getStoryBibleForProject({ projectId: storyProjectId });

    expect(resource).toMatchObject({ version: 1, etag: '"1"' });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(session.getValidSession).not.toHaveBeenCalled();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `/api/v1/projects/${encodeURIComponent(storyProjectId)}/story-bible`,
    );
    expect(init?.method).toBe("GET");
    expect(init).not.toHaveProperty("body");
    const headers = new Headers(init?.headers);
    expect(headers.has("X-CSRF-Token")).toBe(false);
    expect(headers.has("If-Match")).toBe(false);
  });

  it("reads by stable ID, validates both contexts, and passes AbortSignal", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        storyBibleJsonResponse(storyBibleResponse(2), { etag: '"2"' }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const resource = await createStoryBibleApiClient(
      sessionManager(),
    ).getStoryBible({
      storyBibleId,
      expectedProjectId: storyProjectId,
      signal: controller.signal,
    });
    expect(resource.version).toBe(2);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/v1/story-bibles/${encodeURIComponent(storyBibleId)}`,
    );
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  });

  it.each([
    ["PROJECT_NOT_FOUND", "project_not_found"],
    ["STORY_BIBLE_FOR_PROJECT_NOT_FOUND", "story_bible_for_project_not_found"],
    ["STORY_BIBLE_NOT_FOUND", "story_bible_not_found"],
    ["STORY_BIBLE_PERSISTENCE_UNAVAILABLE", "unavailable"],
  ] as const)("classifies safe read error %s", async (code, kind) => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        storyBibleJsonResponse(storyBibleErrorEnvelope(code), {
          status: code.includes("NOT_FOUND") ? 404 : 503,
          requestId: "req_read_safe",
        }),
      ),
    );
    const error = await createStoryBibleApiClient(sessionManager())
      .getStoryBibleForProject({ projectId: storyProjectId })
      .catch((reason: unknown) => reason);
    expect(error).toMatchObject({ kind, requestId: "req_read_safe" });
    expect(JSON.stringify(error)).not.toContain(
      "STORY_BIBLE_FRONTEND_SECRET_CANARY",
    );
  });

  it("rejects invalid identifiers before Session or fetch", async () => {
    const session = sessionManager();
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    const client = createStoryBibleApiClient(session);
    await expect(
      client.getStoryBibleForProject({ projectId: "bad/\ncanary" }),
    ).rejects.toMatchObject({ kind: "validation" });
    await expect(
      client.getStoryBible({ storyBibleId: storyProjectId }),
    ).rejects.toMatchObject({ kind: "validation" });
    await expect(
      client.getStoryBible({
        storyBibleId,
        expectedProjectId: "bad-project",
      }),
    ).rejects.toMatchObject({ kind: "validation" });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(session.getValidSession).not.toHaveBeenCalled();
  });

  it("never retries network or aborted GET failures", async () => {
    for (const [failure, kind] of [
      [new TypeError("network private"), "network"],
      [new DOMException("abort private", "AbortError"), "aborted"],
    ] as const) {
      const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(failure);
      vi.stubGlobal("fetch", fetchMock);
      await expect(
        createStoryBibleApiClient(sessionManager()).getStoryBibleForProject({
          projectId: storyProjectId,
        }),
      ).rejects.toMatchObject({ kind });
      expect(fetchMock).toHaveBeenCalledOnce();
    }
  });
});

describe("Story Bible create client", () => {
  it("validates, gets one Session, and sends one normalized POST", async () => {
    const events: string[] = [];
    const session = sessionManager();
    session.getValidSession.mockImplementation(() => {
      events.push("session");
      return Promise.resolve({
        csrfToken,
        expiresAtMilliseconds: Date.now() + 60_000,
      });
    });
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(() => {
      events.push("post");
      return Promise.resolve(
        storyBibleJsonResponse(
          storyBibleResponse(1, {
            title: "创建标题",
            content: "第一行\n第二行",
          }),
          {
            status: 201,
            etag: '"1"',
            location: `/api/v1/story-bibles/${storyBibleId}`,
          },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const resource = await createStoryBibleApiClient(session).createStoryBible({
      projectId: storyProjectId,
      title: "  创建标题  ",
      content: "第一行\r\n第二行",
    });

    expect(events).toEqual(["session", "post"]);
    expect(resource.storyBible.title).toBe("创建标题");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `/api/v1/projects/${encodeURIComponent(storyProjectId)}/story-bible`,
    );
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe(csrfToken);
    expect(init?.body).toBe(
      JSON.stringify({ title: "创建标题", content: "第一行\n第二行" }),
    );
  });

  it.each([
    { projectId: "invalid", title: "标题", content: "" },
    { projectId: storyProjectId, title: "   ", content: "" },
    { projectId: storyProjectId, title: "标题", content: "坏\u0000正文" },
    {
      projectId: storyProjectId,
      title: 42,
      content: "",
    },
  ])(
    "rejects invalid create input before any side effect %#",
    async (input) => {
      const session = sessionManager();
      const fetchMock = vi.fn<typeof fetch>();
      vi.stubGlobal("fetch", fetchMock);
      await expect(
        createStoryBibleApiClient(session).createStoryBible(input as never),
      ).rejects.toMatchObject({ kind: "validation" });
      expect(session.getValidSession).not.toHaveBeenCalled();
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("keeps deterministic 409 and 422 failures distinct without retry", async () => {
    for (const [status, code, kind] of [
      [409, "STORY_BIBLE_ALREADY_EXISTS_FOR_PROJECT", "already_exists"],
      [422, "INVALID_STORY_BIBLE_TITLE", "validation"],
    ] as const) {
      const fetchMock = vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          storyBibleJsonResponse(
            storyBibleErrorEnvelope(code, { field: "title" }),
            { status, requestId: "req_create_safe" },
          ),
        );
      vi.stubGlobal("fetch", fetchMock);
      const error = await createStoryBibleApiClient(sessionManager())
        .createStoryBible({
          projectId: storyProjectId,
          title: "标题",
          content: "",
        })
        .catch((reason: unknown) => reason);
      expect(error).toMatchObject(
        kind === "validation"
          ? {
              kind,
              fieldErrors: [
                {
                  field: "title",
                  message: "小说设定标题未通过服务端验证。",
                },
              ],
            }
          : { kind },
      );
      expect(fetchMock).toHaveBeenCalledOnce();
    }
  });

  it.each([
    new TypeError("network response lost"),
    new DOMException("cancelled", "AbortError"),
  ])(
    "classifies transport failure after POST as unknown outcome",
    async (failure) => {
      const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(failure);
      vi.stubGlobal("fetch", fetchMock);
      await expect(
        createStoryBibleApiClient(sessionManager()).createStoryBible({
          projectId: storyProjectId,
          title: "标题",
          content: "",
        }),
      ).rejects.toMatchObject({
        kind: "outcome_unknown",
        message: "创建结果未确认，请重新读取小说设定核实。",
      });
      expect(fetchMock).toHaveBeenCalledOnce();
    },
  );

  it.each([
    [
      storyBibleJsonResponse(
        storyBibleErrorEnvelope("STORY_BIBLE_PERSISTENCE_UNAVAILABLE"),
        { status: 503 },
      ),
    ],
    [
      storyBibleJsonResponse(storyBibleResponse(), {
        status: 201,
        etag: '"1"',
      }),
    ],
    [
      storyBibleJsonResponse(
        { unsafe: true },
        {
          status: 201,
          etag: '"1"',
          location: `/api/v1/story-bibles/${storyBibleId}`,
        },
      ),
    ],
  ])("classifies unconfirmed POST response %# as unknown", async (response) => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(response));
    await expect(
      createStoryBibleApiClient(sessionManager()).createStoryBible({
        projectId: storyProjectId,
        title: "标题",
        content: "",
      }),
    ).rejects.toMatchObject({ kind: "outcome_unknown" });
  });
});

describe("Story Bible revision client", () => {
  it("sends one complete PUT with the supplied baseline ETag", async () => {
    const session = sessionManager();
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        storyBibleJsonResponse(storyBibleResponse(2), { etag: '"2"' }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const resource = await createStoryBibleApiClient(session).reviseStoryBible({
      storyBibleId,
      expectedProjectId: storyProjectId,
      etag: '"1"',
      title: "修订标题",
      content: "修订正文",
    });
    expect(resource.version).toBe(2);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `/api/v1/story-bibles/${encodeURIComponent(storyBibleId)}`,
    );
    expect(init?.method).toBe("PUT");
    const headers = new Headers(init?.headers);
    expect(headers.get("If-Match")).toBe('"1"');
    expect(headers.get("X-CSRF-Token")).toBe(csrfToken);
    expect(init?.body).toBe(
      JSON.stringify({ title: "修订标题", content: "修订正文" }),
    );
  });

  it("parses strict 412 once and never performs GET or PUT replay", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      storyBibleJsonResponse(
        storyBibleErrorEnvelope("STORY_BIBLE_VERSION_CONFLICT", {
          expected_version: 1,
          actual_version: 2,
        }),
        { status: 412, requestId: "req_conflict_safe" },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const error = await createStoryBibleApiClient(sessionManager())
      .reviseStoryBible({
        storyBibleId,
        expectedProjectId: storyProjectId,
        etag: '"1"',
        title: "草稿标题",
        content: "草稿正文",
      })
      .catch((reason: unknown) => reason);
    expect(error).toMatchObject({
      kind: "conflict",
      requestId: "req_conflict_safe",
      conflict: { expectedVersion: 1, actualVersion: 2 },
    });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    expect(JSON.stringify(error)).not.toContain(
      "STORY_BIBLE_FRONTEND_SECRET_CANARY",
    );
  });

  it.each([
    {},
    { expected_version: 2, actual_version: 3 },
    { expected_version: 1, actual_version: 1 },
    { expected_version: true, actual_version: 2 },
    { expected_version: 1, actual_version: 2, content: "canary" },
  ])("rejects malformed 412 details as contract %#", async (details) => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          storyBibleJsonResponse(
            storyBibleErrorEnvelope("STORY_BIBLE_VERSION_CONFLICT", details),
            { status: 412 },
          ),
        ),
    );
    await expect(
      createStoryBibleApiClient(sessionManager()).reviseStoryBible({
        storyBibleId,
        expectedProjectId: storyProjectId,
        etag: '"1"',
        title: "标题",
        content: "",
      }),
    ).rejects.toMatchObject({ kind: "contract" });
  });

  it("rejects invalid ETag, IDs, or text before Session", async () => {
    const session = sessionManager();
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    for (const overrides of [
      { storyBibleId: storyProjectId },
      { expectedProjectId: secondStoryProjectId.toLowerCase() },
      { etag: 'W/"1"' },
      { content: "坏\u0000正文" },
    ]) {
      await expect(
        createStoryBibleApiClient(session).reviseStoryBible({
          storyBibleId,
          expectedProjectId: storyProjectId,
          etag: '"1"',
          title: "标题",
          content: "",
          ...overrides,
        }),
      ).rejects.toBeInstanceOf(Error);
    }
    expect(session.getValidSession).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("clears a failed Session once and never replays the PUT", async () => {
    const session = sessionManager();
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      storyBibleJsonResponse(storyBibleErrorEnvelope("CSRF_TOKEN_INVALID"), {
        status: 403,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      createStoryBibleApiClient(session).reviseStoryBible({
        storyBibleId,
        expectedProjectId: storyProjectId,
        etag: '"1"',
        title: "标题",
        content: "",
      }),
    ).rejects.toMatchObject({ kind: "security" });
    expect(session.clear).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it.each([new TypeError("lost"), new DOMException("cancelled", "AbortError")])(
    "classifies a transport failure after PUT as unknown %#",
    async (failure) => {
      vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(failure));
      await expect(
        createStoryBibleApiClient(sessionManager()).reviseStoryBible({
          storyBibleId,
          expectedProjectId: storyProjectId,
          etag: '"1"',
          title: "标题",
          content: "",
        }),
      ).rejects.toMatchObject({
        kind: "outcome_unknown",
        message: "保存结果未确认，请重新读取小说设定核实。",
      });
    },
  );
});
