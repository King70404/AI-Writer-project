import { afterEach, describe, expect, it, vi } from "vitest";

import { createProjectApiClient } from "../../frontend/src/features/projects/api/client";
import type { ReviseProjectInput } from "../../frontend/src/features/projects/api/client";
import { projectSecuritySession } from "../../frontend/src/features/projects/api/security-session";
import {
  csrfToken,
  jsonResponse,
  projectId,
  projectResponse,
} from "./project-detail-support";

function securityManager() {
  return {
    getValidSession: vi.fn().mockResolvedValue({
      csrfToken,
      expiresAtMilliseconds: Date.now() + 60_000,
    }),
    clear: vi.fn<() => void>(),
  };
}

function input(
  overrides: Partial<ReviseProjectInput> = {},
): ReviseProjectInput {
  return {
    projectId,
    etag: '"1"',
    title: "修订标题",
    description: "修订简介",
    ...overrides,
  };
}

const invalidRevisionCases: ReadonlyArray<
  readonly [ReviseProjectInput, "validation" | "contract"]
> = [
  [input({ projectId: "prj_invalid" }), "validation"],
  [input({ etag: 'W/"1"' }), "contract"],
  [input({ title: "   " }), "validation"],
  [input({ title: "😀".repeat(121) }), "validation"],
  [input({ description: "界".repeat(2_001) }), "validation"],
  [{ ...input(), title: 42 } as unknown as ReviseProjectInput, "validation"],
];

function errorEnvelope(
  code: string,
  details: Readonly<Record<string, unknown>> = {},
) {
  return {
    error: {
      code,
      message: "private response canary",
      details,
      retryable: true,
      suggested_action: "private suggestion",
    },
    request_id: "req_body",
  };
}

afterEach(() => {
  projectSecuritySession.clear();
  vi.unstubAllGlobals();
});

describe("Project complete revision PUT client", () => {
  it("validates, gets Session, and sends exactly one complete PUT", async () => {
    const events: string[] = [];
    const security = securityManager();
    security.getValidSession.mockImplementation(() => {
      events.push("session");
      return Promise.resolve({
        csrfToken,
        expiresAtMilliseconds: Date.now() + 60_000,
      });
    });
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(() => {
      events.push("put");
      return Promise.resolve(
        jsonResponse(
          projectResponse(2, {
            title: "服务端规范标题",
            description: "服务端规范简介",
          }),
          { etag: '"2"' },
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    const resource =
      await createProjectApiClient(security).reviseProject(input());

    expect(events).toEqual(["session", "put"]);
    expect(resource).toMatchObject({ etag: '"2"', version: 2 });
    expect(resource.project.title).toBe("服务端规范标题");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/v1/projects/${encodeURIComponent(projectId)}`);
    expect(init?.method).toBe("PUT");
    const headers = new Headers(init?.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-CSRF-Token")).toBe(csrfToken);
    expect(headers.get("If-Match")).toBe('"1"');
    const requestBody = init?.body;
    if (typeof requestBody !== "string") {
      throw new TypeError("Expected a serialized JSON request body.");
    }
    expect(requestBody).toBe(
      JSON.stringify({ title: "修订标题", description: "修订简介" }),
    );
    expect(requestBody).not.toContain("projectId");
    expect(requestBody).not.toContain("version");
    expect(requestBody).not.toContain("revision");
  });

  it.each(invalidRevisionCases)(
    "rejects invalid input before Session or PUT: %#",
    async (invalid, kind) => {
      const security = securityManager();
      const fetchMock = vi.fn<typeof fetch>();
      vi.stubGlobal("fetch", fetchMock);
      await expect(
        createProjectApiClient(security).reviseProject(invalid),
      ).rejects.toMatchObject({ kind });
      expect(security.getValidSession).not.toHaveBeenCalled();
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("does not PUT when Session acquisition fails", async () => {
    const security = securityManager();
    security.getValidSession.mockRejectedValue(new TypeError("offline"));
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      createProjectApiClient(security).reviseProject(input()),
    ).rejects.toMatchObject({ kind: "network" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("parses a strict 412 conflict and never GETs or replays PUT", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse(
        errorEnvelope("PROJECT_VERSION_CONFLICT", {
          expected_version: 1,
          actual_version: 2,
        }),
        { status: 412, requestId: "req_conflict" },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const error = await createProjectApiClient(securityManager())
      .reviseProject(input())
      .catch((reason: unknown) => reason);

    expect(error).toMatchObject({
      kind: "conflict",
      requestId: "req_conflict",
      conflict: { expectedVersion: 1, actualVersion: 2 },
    });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("PUT");
    expect(JSON.stringify(error)).not.toContain("private response canary");
  });

  it.each([
    {},
    { expected_version: 2, actual_version: 3 },
    { expected_version: 1, actual_version: 1 },
    { expected_version: 1, actual_version: 2, project: "body-canary" },
    { expected_version: true, actual_version: 2 },
    { expected_version: 1, actual_version: 0 },
  ])(
    "rejects malformed 412 details as a contract error: %#",
    async (details) => {
      vi.stubGlobal(
        "fetch",
        vi.fn<typeof fetch>().mockResolvedValue(
          jsonResponse(errorEnvelope("PROJECT_VERSION_CONFLICT", details), {
            status: 412,
          }),
        ),
      );
      await expect(
        createProjectApiClient(securityManager()).reviseProject(input()),
      ).rejects.toMatchObject({ kind: "contract" });
    },
  );

  it("treats network loss or cancellation after PUT starts as unknown outcome", async () => {
    for (const failure of [
      new TypeError("network response lost"),
      new DOMException("cancelled", "AbortError"),
    ]) {
      const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(failure);
      vi.stubGlobal("fetch", fetchMock);
      await expect(
        createProjectApiClient(securityManager()).reviseProject(input()),
      ).rejects.toMatchObject({
        kind: "outcome_unknown",
        message: "保存结果未确认，请重新加载项目核实。",
      });
      expect(fetchMock).toHaveBeenCalledOnce();
    }
  });

  it("does not replay a security failure and clears only the memory Session", async () => {
    const security = securityManager();
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse(errorEnvelope("CSRF_TOKEN_INVALID"), {
        status: 403,
        requestId: "req_security",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      createProjectApiClient(security).reviseProject(input()),
    ).rejects.toMatchObject({ kind: "security" });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(security.clear).toHaveBeenCalledOnce();
  });

  it.each([
    [projectResponse(1), '"1"'],
    [projectResponse(2), '"1"'],
    [
      projectResponse(2, { project_id: "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW" }),
      '"2"',
    ],
  ])(
    "rejects a non-advancing or inconsistent success response %#",
    async (body, etag) => {
      vi.stubGlobal(
        "fetch",
        vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(body, { etag })),
      );
      await expect(
        createProjectApiClient(securityManager()).reviseProject(input()),
      ).rejects.toMatchObject({ kind: "contract" });
    },
  );
});
