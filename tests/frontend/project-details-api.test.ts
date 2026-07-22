import { afterEach, describe, expect, it, vi } from "vitest";

import { createProjectApiClient } from "../../frontend/src/features/projects/api/client";
import { projectSecuritySession } from "../../frontend/src/features/projects/api/security-session";
import {
  jsonResponse,
  projectId,
  projectResponse,
} from "./project-detail-support";

function securityManager() {
  return {
    getValidSession: vi.fn(),
    clear: vi.fn<() => void>(),
  };
}

function errorEnvelope(code: string) {
  return {
    error: {
      code,
      message: "private backend message",
      details: {},
      retryable: false,
      suggested_action: null,
    },
    request_id: "req_body_private",
  };
}

afterEach(() => {
  projectSecuritySession.clear();
  vi.unstubAllGlobals();
});

describe("Project details GET client", () => {
  it("uses one relative encoded GET without Session, CSRF, body, or If-Match", async () => {
    const security = securityManager();
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(projectResponse(), { etag: '"1"' }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await createProjectApiClient(security).getProject(projectId);

    expect(result).toMatchObject({ etag: '"1"', version: 1 });
    expect(result.project.project_id).toBe(projectId);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(security.getValidSession).not.toHaveBeenCalled();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/v1/projects/${encodeURIComponent(projectId)}`);
    expect(init?.method).toBe("GET");
    expect(init).not.toHaveProperty("body");
    const headers = new Headers(init?.headers);
    expect(headers.has("X-CSRF-Token")).toBe(false);
    expect(headers.has("If-Match")).toBe(false);
  });

  it("rejects invalid route IDs before any observable side effect", async () => {
    const security = securityManager();
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      createProjectApiClient(security).getProject("prj_bad/\ncanary"),
    ).rejects.toMatchObject({
      kind: "validation",
      code: "INVALID_PROJECT_ID",
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(security.getValidSession).not.toHaveBeenCalled();
  });

  it.each([
    [undefined, projectResponse()],
    ['W/"1"', projectResponse()],
    ['"2"', projectResponse(1)],
    [
      '"1"',
      projectResponse(1, { project_id: "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW" }),
    ],
  ])("rejects unsafe success metadata %#", async (etag, body) => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(body, {
          ...(etag === undefined ? {} : { etag }),
        }),
      ),
    );
    await expect(
      createProjectApiClient(securityManager()).getProject(projectId),
    ).rejects.toMatchObject({
      kind: "contract",
    });
  });

  it.each([
    [404, "PROJECT_NOT_FOUND", "not_found"],
    [503, "PROJECT_PERSISTENCE_UNAVAILABLE", "unavailable"],
  ] as const)("classifies HTTP %i safely", async (status, code, kind) => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse(errorEnvelope(code), {
          status,
          requestId: "req_details_safe",
        }),
      ),
    );
    const error = await createProjectApiClient(securityManager())
      .getProject(projectId)
      .catch((reason: unknown) => reason);
    expect(error).toMatchObject({ kind, requestId: "req_details_safe" });
    expect(JSON.stringify(error)).not.toContain("private backend message");
  });

  it("passes AbortSignal through and never retries a rejected GET", async () => {
    const abort = new DOMException("private abort", "AbortError");
    const fetchMock = vi.fn<typeof fetch>().mockRejectedValue(abort);
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    await expect(
      createProjectApiClient(securityManager()).getProject(projectId, {
        signal: controller.signal,
      }),
    ).rejects.toMatchObject({ kind: "aborted" });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  });
});
