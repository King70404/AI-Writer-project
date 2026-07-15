import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearLocalSecuritySession,
  establishLocalSecuritySession,
  localCsrfHeaders,
} from "../src/api/security";

const FIRST_CSRF_FIXTURE = "first-csrf-fixture-value-with-safe-length";
const SECOND_CSRF_FIXTURE = "second-csrf-fixture-value-with-safe-length";

function sessionResponse(csrfToken: string): Response {
  return new Response(
    JSON.stringify({
      csrf_token: csrfToken,
      expires_in_seconds: 28_800,
    }),
    {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": "req_security_session",
      },
    },
  );
}

afterEach(() => {
  clearLocalSecuritySession();
  vi.unstubAllGlobals();
});

describe("local security session", () => {
  it("keeps the CSRF token only in module memory", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(sessionResponse(FIRST_CSRF_FIXTURE));
    vi.stubGlobal("fetch", fetchMock);

    const result = await establishLocalSecuritySession();

    expect(result.data.expires_in_seconds).toBe(28_800);
    expect(localCsrfHeaders()).toEqual({
      "X-CSRF-Token": FIRST_CSRF_FIXTURE,
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/security/session");
    expect(init?.credentials).toBe("same-origin");
  });

  it("replaces and explicitly clears the in-memory proof", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock
      .mockResolvedValueOnce(sessionResponse(FIRST_CSRF_FIXTURE))
      .mockResolvedValueOnce(sessionResponse(SECOND_CSRF_FIXTURE));
    vi.stubGlobal("fetch", fetchMock);

    await establishLocalSecuritySession();
    await establishLocalSecuritySession();
    expect(localCsrfHeaders()).toEqual({
      "X-CSRF-Token": SECOND_CSRF_FIXTURE,
    });

    clearLocalSecuritySession();
    expect(localCsrfHeaders()).toEqual({});
  });

  it("does not retain an invalid response", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock
      .mockResolvedValueOnce(sessionResponse(FIRST_CSRF_FIXTURE))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: "short" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await establishLocalSecuritySession();
    await expect(establishLocalSecuritySession()).rejects.toThrow();
    expect(localCsrfHeaders()).toEqual({});
  });
});
