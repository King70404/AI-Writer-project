import { afterEach, describe, expect, it, vi } from "vitest";

import { createProjectApiClient } from "../../frontend/src/features/projects/api/client";
import { projectSecuritySession } from "../../frontend/src/features/projects/api/security-session";
import { jsonResponse, projectId, timestamp } from "./project-detail-support";

const revisionId = "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV";

function securityManager() {
  return {
    getValidSession: vi.fn(),
    clear: vi.fn<() => void>(),
  };
}

function page() {
  return {
    project_id: projectId,
    current_revision_number: 1,
    items: [
      {
        revision_id: revisionId,
        revision_number: 1,
        title: "初始修订",
        created_at: timestamp,
        is_current: true,
      },
    ],
    next_cursor: null,
    has_more: false,
  };
}

function snapshot() {
  return {
    project_id: projectId,
    revision_id: revisionId,
    revision_number: 1,
    title: "初始修订",
    description: "只读内容",
    created_at: timestamp,
    is_current: true,
    current_revision_number: 1,
  };
}

afterEach(() => {
  projectSecuritySession.clear();
  vi.unstubAllGlobals();
});

describe("Project revision history GET client", () => {
  it("lists with an opaque encoded cursor and no write security material", async () => {
    const security = securityManager();
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(page()));
    vi.stubGlobal("fetch", fetchMock);

    await createProjectApiClient(security).listProjectRevisions({
      projectId,
      limit: 20,
      cursor: "opaque+/=cursor",
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      `/api/v1/projects/${projectId}/revisions?limit=20&cursor=opaque%2B%2F%3Dcursor`,
    );
    expect(init?.method).toBe("GET");
    expect(init).not.toHaveProperty("body");
    expect(new Headers(init?.headers).has("X-CSRF-Token")).toBe(false);
    expect(new Headers(init?.headers).has("If-Match")).toBe(false);
    expect(security.getValidSession).not.toHaveBeenCalled();
  });

  it("gets one exact revision with GET and forwards cancellation", async () => {
    const security = securityManager();
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(snapshot()));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    const result = await createProjectApiClient(security).getProjectRevision({
      projectId,
      revisionNumber: 1,
      signal: controller.signal,
    });

    expect(result.description).toBe("只读内容");
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/v1/projects/${projectId}/revisions/1`,
    );
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
    expect(security.getValidSession).not.toHaveBeenCalled();
  });

  it.each([
    ["bad-id", 20, undefined],
    [projectId, 0, undefined],
    [projectId, 101, undefined],
    [projectId, 20, ""],
  ])(
    "rejects invalid history list input before fetch %#",
    async (candidateId, limit, cursor) => {
      const fetchMock = vi.fn<typeof fetch>();
      vi.stubGlobal("fetch", fetchMock);
      await expect(
        createProjectApiClient(securityManager()).listProjectRevisions({
          projectId: candidateId,
          limit,
          ...(cursor === undefined ? {} : { cursor }),
        }),
      ).rejects.toMatchObject({ kind: "validation" });
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it.each([0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1])(
    "rejects revision number %s before fetch",
    async (revisionNumber) => {
      const fetchMock = vi.fn<typeof fetch>();
      vi.stubGlobal("fetch", fetchMock);
      await expect(
        createProjectApiClient(securityManager()).getProjectRevision({
          projectId,
          revisionNumber,
        }),
      ).rejects.toMatchObject({
        kind: "validation",
        code: "INVALID_REVISION_NUMBER",
      });
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("normalizes revision-not-found without exposing backend text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "PROJECT_REVISION_NOT_FOUND",
              message: "private database message",
              details: {},
              retryable: false,
              suggested_action: null,
            },
            request_id: "req_history_safe",
          },
          { status: 404, requestId: "req_history_safe" },
        ),
      ),
    );
    const error = await createProjectApiClient(securityManager())
      .getProjectRevision({ projectId, revisionNumber: 1 })
      .catch((reason: unknown) => reason);
    expect(error).toMatchObject({
      kind: "not_found",
      requestId: "req_history_safe",
    });
    expect(JSON.stringify(error)).not.toContain("private database message");
  });
});
