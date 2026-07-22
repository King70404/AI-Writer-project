import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../frontend/src/api/errors";
import { createProjectApiClient } from "../../frontend/src/features/projects/api/client";
import type { CreateProjectRequest } from "../../frontend/src/features/projects/api/contracts";
import {
  normalizeProjectApiError,
  ProjectApiError,
  shouldClearProjectSecuritySession,
} from "../../frontend/src/features/projects/api/errors";
import { ProjectContractError } from "../../frontend/src/features/projects/api/parsers";
import { projectSecuritySession } from "../../frontend/src/features/projects/api/security-session";

const projectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const revisionId = "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const timestamp = "2026-07-22T08:30:00Z";
const csrfToken = "csrf-token-private-project-api-client-fixture";

function listItem() {
  return {
    project_id: projectId,
    current_revision_id: revisionId,
    revision_number: 1,
    concurrency_version: 1,
    title: "真实项目",
    created_at: timestamp,
    updated_at: timestamp,
    revision_created_at: timestamp,
  };
}

function projectResponse() {
  return {
    ...listItem(),
    description: "不应出现在列表",
    head_updated_at: timestamp,
  };
}

function jsonResponse(value: unknown, status = 200, requestId = "req_project") {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json", "X-Request-ID": requestId },
  });
}

function securityManager() {
  return {
    getValidSession: vi.fn().mockResolvedValue({
      csrfToken,
      expiresAtMilliseconds: Date.now() + 60_000,
    }),
    clear: vi.fn<() => void>(),
  };
}

afterEach(() => {
  projectSecuritySession.clear();
  vi.unstubAllGlobals();
});

describe("Project API client", () => {
  it("lists with default limit, opaque cursor encoding, and no write proof", async () => {
    const session = securityManager();
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({
        items: [listItem()],
        next_cursor: null,
        has_more: false,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const page = await createProjectApiClient(session).listProjects({
      cursor: "opaque+/= cursor",
    });

    expect(page.items).toHaveLength(1);
    expect(session.getValidSession).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/projects?limit=20&cursor=opaque%2B%2F%3D+cursor");
    expect(init?.method).toBe("GET");
    expect(init).not.toHaveProperty("body");
    expect(new Headers(init?.headers).has("X-CSRF-Token")).toBe(false);
    expect(init?.credentials).toBe("same-origin");
  });

  it("rejects invalid list options and invalid or duplicate response pages", async () => {
    const session = securityManager();
    const client = createProjectApiClient(session);
    await expect(client.listProjects({ limit: 0 })).rejects.toMatchObject({
      kind: "validation",
    });
    await expect(client.listProjects({ cursor: "" })).rejects.toMatchObject({
      kind: "validation",
    });

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({ items: "bad", next_cursor: null, has_more: false }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          items: [listItem(), listItem()],
          next_cursor: null,
          has_more: false,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    await expect(client.listProjects()).rejects.toMatchObject({
      kind: "contract",
    });
    await expect(client.listProjects()).rejects.toMatchObject({
      kind: "contract",
    });
  });

  it("obtains a session before exactly one JSON POST with only contract fields", async () => {
    const events: string[] = [];
    const session = securityManager();
    session.getValidSession.mockImplementation(() => {
      events.push("session");
      return Promise.resolve({
        csrfToken,
        expiresAtMilliseconds: Date.now() + 60_000,
      });
    });
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(() => {
      events.push("post");
      return Promise.resolve(jsonResponse(projectResponse(), 201));
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await createProjectApiClient(session).createProject({
      title: "真实项目",
      description: "真实简介",
    });

    expect(result.project_id).toBe(projectId);
    expect(events).toEqual(["session", "post"]);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/projects");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("same-origin");
    expect(new Headers(init?.headers).get("Content-Type")).toBe(
      "application/json",
    );
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe(csrfToken);
    expect(init?.body).toBe(
      JSON.stringify({ title: "真实项目", description: "真实简介" }),
    );
  });

  it("does not POST when session acquisition fails", async () => {
    const session = securityManager();
    session.getValidSession.mockRejectedValue(new TypeError("offline"));
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      createProjectApiClient(session).createProject({
        title: "项目",
        description: "",
      }),
    ).rejects.toMatchObject({ kind: "network" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not retry a failed POST and safely retains its request ID", async () => {
    const session = securityManager();
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "SERVICE_UNAVAILABLE",
            message: "private server details",
            details: { private_body: "must-not-survive" },
            retryable: true,
            suggested_action: "retry",
          },
          request_id: "req_body",
        },
        503,
        "req_header",
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const error = await createProjectApiClient(session)
      .createProject({ title: "项目", description: "secret body" })
      .catch((reason: unknown) => reason);

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(error).toBeInstanceOf(ProjectApiError);
    expect(error).toMatchObject({
      kind: "unavailable",
      requestId: "req_header",
    });
    expect(JSON.stringify(error)).not.toContain("private server details");
    expect(JSON.stringify(error)).not.toContain("secret body");
    expect(JSON.stringify(error)).not.toContain(csrfToken);
  });

  it("clears the session after a POST security error", async () => {
    const session = securityManager();
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "CSRF_TOKEN_INVALID",
              message: "invalid",
              details: {},
              retryable: false,
              suggested_action: null,
            },
            request_id: "req_security",
          },
          403,
        ),
      ),
    );

    await expect(
      createProjectApiClient(session).createProject({
        title: "项目",
        description: "",
      }),
    ).rejects.toMatchObject({ kind: "security" });
    expect(session.clear).toHaveBeenCalledOnce();
  });

  it("classifies cancellation, network, validation, 413 and 415 safely", () => {
    expect(
      normalizeProjectApiError(new DOMException("cancelled", "AbortError")),
    ).toMatchObject({ kind: "aborted" });
    expect(normalizeProjectApiError(new TypeError("offline"))).toMatchObject({
      kind: "network",
    });
    expect(normalizeProjectApiError(new Error("unknown"))).toMatchObject({
      kind: "unknown",
    });
    expect(
      normalizeProjectApiError(
        new ApiError({
          status: 413,
          code: "REQUEST_TOO_LARGE",
          message: "private",
          details: {},
          retryable: false,
          suggestedAction: null,
          requestId: "unsafe request id with spaces",
        }),
      ),
    ).toMatchObject({ kind: "validation", requestId: null });
    expect(
      normalizeProjectApiError(
        new ApiError({
          status: 415,
          code: "UNSUPPORTED_MEDIA_TYPE",
          message: "private",
          details: {},
          retryable: false,
          suggestedAction: null,
          requestId: "req_415",
        }),
      ),
    ).toMatchObject({ kind: "contract", requestId: "req_415" });
  });

  it("maps every supported HTTP class and sanitizes validation fields", () => {
    const makeError = (
      status: number,
      code: string,
      details: Readonly<Record<string, unknown>> = {},
    ) =>
      new ApiError({
        status,
        code,
        message: "private backend message",
        details,
        retryable: false,
        suggestedAction: null,
        requestId: "req_safe",
      });

    expect(
      normalizeProjectApiError(makeError(403, "ORIGIN_NOT_ALLOWED")),
    ).toMatchObject({
      kind: "security",
      message: "当前页面来源未通过安全验证。",
    });
    expect(normalizeProjectApiError(makeError(401, "OTHER"))).toMatchObject({
      kind: "security",
    });
    expect(
      normalizeProjectApiError(makeError(404, "PROJECT_NOT_FOUND")),
    ).toMatchObject({
      kind: "not_found",
    });
    for (const status of [409, 412, 428]) {
      expect(
        normalizeProjectApiError(makeError(status, "CONFLICT")),
      ).toMatchObject({
        kind: "conflict",
      });
    }
    expect(
      normalizeProjectApiError(makeError(400, "INVALID_PROJECT_ID")),
    ).toMatchObject({
      kind: "validation",
    });
    expect(
      normalizeProjectApiError(makeError(200, "INVALID_RESPONSE")),
    ).toMatchObject({
      kind: "contract",
    });
    expect(normalizeProjectApiError(makeError(500, "UNKNOWN"))).toMatchObject({
      kind: "unknown",
    });

    const validation = normalizeProjectApiError(
      makeError(422, "VALIDATION_ERROR", {
        errors: [
          null,
          [],
          "bad",
          { field: "body.title" },
          { field: "title" },
          { field: "body.description" },
          { field: "description" },
          { field: "query.limit" },
          { field: "limit" },
          { field: "unknown" },
        ],
      }),
    );
    expect(validation.fieldErrors).toEqual([
      { field: "title", message: "项目标题未通过服务端验证。" },
      { field: "description", message: "项目简介未通过服务端验证。" },
      { field: "limit", message: "列表页大小未通过服务端验证。" },
    ]);
    expect(
      normalizeProjectApiError(makeError(422, "VALID", {})).fieldErrors,
    ).toEqual([]);
  });

  it("preserves normalized errors, maps contract errors and tests session clearing rules", () => {
    const normalized = new ProjectApiError({
      kind: "unknown",
      code: "ALREADY_SAFE",
      message: "safe",
    });
    expect(normalizeProjectApiError(normalized)).toBe(normalized);
    expect(normalizeProjectApiError(new ProjectContractError())).toMatchObject({
      kind: "contract",
    });
    const apiError = (status: number, code: string) =>
      new ApiError({
        status,
        code,
        message: "private",
        details: {},
        retryable: false,
        suggestedAction: null,
        requestId: null,
      });
    expect(shouldClearProjectSecuritySession(apiError(401, "OTHER"))).toBe(
      true,
    );
    expect(shouldClearProjectSecuritySession(apiError(403, "OTHER"))).toBe(
      true,
    );
    expect(
      shouldClearProjectSecuritySession(apiError(400, "SESSION_EXPIRED")),
    ).toBe(true);
    expect(shouldClearProjectSecuritySession(apiError(500, "OTHER"))).toBe(
      false,
    );
    expect(shouldClearProjectSecuritySession(new Error("other"))).toBe(false);
  });

  it("rejects non-text create input before session acquisition", async () => {
    const session = securityManager();
    const invalid = {
      title: 42,
      description: "",
    } as unknown as CreateProjectRequest;
    await expect(
      createProjectApiClient(session).createProject(invalid),
    ).rejects.toMatchObject({
      kind: "validation",
      code: "INVALID_CREATE_PROJECT_INPUT",
    });
    expect(session.getValidSession).not.toHaveBeenCalled();
  });
});
