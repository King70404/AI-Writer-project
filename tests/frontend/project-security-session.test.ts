import { afterEach, describe, expect, it, vi } from "vitest";

import { createProjectSecuritySessionManager } from "../../frontend/src/features/projects/api/security-session";

const token = "csrf-token-that-must-remain-only-in-module-memory";

afterEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  document.body.replaceChildren();
});

describe("Project security session manager", () => {
  it("uses the default relative session transport and forwards cancellation", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ csrf_token: token, expires_in_seconds: 120 }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const manager = createProjectSecuritySessionManager();

    expect(await manager.getValidSession(controller.signal)).toMatchObject({
      csrfToken: token,
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/security/session");
    expect(init?.signal).toBe(controller.signal);
  });

  it("fetches once, reuses a safe token and uses an injected time source", async () => {
    let now = 1_000;
    const requestSession = vi.fn().mockResolvedValue({
      csrf_token: token,
      expires_in_seconds: 120,
    });
    const manager = createProjectSecuritySessionManager({
      now: () => now,
      requestSession,
    });

    const first = await manager.getValidSession();
    now += 20_000;
    const second = await manager.getValidSession();

    expect(first).toEqual({
      csrfToken: token,
      expiresAtMilliseconds: 121_000,
    });
    expect(second).toBe(first);
    expect(requestSession).toHaveBeenCalledOnce();
  });

  it("refreshes expired and near-expiry tokens", async () => {
    let now = 0;
    const requestSession = vi
      .fn()
      .mockResolvedValueOnce({
        csrf_token: `${token}-one`,
        expires_in_seconds: 31,
      })
      .mockResolvedValueOnce({
        csrf_token: `${token}-two`,
        expires_in_seconds: 120,
      })
      .mockResolvedValueOnce({
        csrf_token: `${token}-three`,
        expires_in_seconds: 120,
      });
    const manager = createProjectSecuritySessionManager({
      now: () => now,
      requestSession,
    });

    await manager.getValidSession();
    now = 1_001;
    expect((await manager.getValidSession()).csrfToken).toBe(`${token}-two`);
    now = 200_000;
    expect((await manager.getValidSession()).csrfToken).toBe(`${token}-three`);
    expect(requestSession).toHaveBeenCalledTimes(3);
  });

  it("merges concurrent acquisition into one request", async () => {
    let resolveSession!: (value: {
      csrf_token: string;
      expires_in_seconds: number;
    }) => void;
    const requestSession = vi.fn(
      () =>
        new Promise<{
          csrf_token: string;
          expires_in_seconds: number;
        }>((resolve) => {
          resolveSession = resolve;
        }),
    );
    const manager = createProjectSecuritySessionManager({ requestSession });

    const first = manager.getValidSession();
    const second = manager.getValidSession();
    expect(first).toBe(second);
    resolveSession({ csrf_token: token, expires_in_seconds: 120 });

    await expect(Promise.all([first, second])).resolves.toHaveLength(2);
    expect(requestSession).toHaveBeenCalledOnce();
  });

  it("does not cache failure and clear invalidates both cached and in-flight values", async () => {
    const requestSession = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("network failed without token"))
      .mockResolvedValue({ csrf_token: token, expires_in_seconds: 120 });
    const manager = createProjectSecuritySessionManager({ requestSession });

    await expect(manager.getValidSession()).rejects.not.toThrow(token);
    await manager.getValidSession();
    manager.clear();
    await manager.getValidSession();

    expect(requestSession).toHaveBeenCalledTimes(3);
  });

  it("does not cache a response resolved after clear", async () => {
    let resolveSession!: (value: {
      csrf_token: string;
      expires_in_seconds: number;
    }) => void;
    const requestSession = vi.fn(
      () =>
        new Promise<{
          csrf_token: string;
          expires_in_seconds: number;
        }>((resolve) => {
          resolveSession = resolve;
        }),
    );
    const manager = createProjectSecuritySessionManager({ requestSession });
    const stale = manager.getValidSession();
    manager.clear();
    resolveSession({ csrf_token: `${token}-stale`, expires_in_seconds: 120 });
    await stale;

    const fresh = manager.getValidSession();
    expect(requestSession).toHaveBeenCalledTimes(2);
    resolveSession({ csrf_token: `${token}-fresh`, expires_in_seconds: 120 });
    await expect(fresh).resolves.toMatchObject({ csrfToken: `${token}-fresh` });
  });

  it("never persists or renders the CSRF token", async () => {
    const manager = createProjectSecuritySessionManager({
      requestSession: vi.fn().mockResolvedValue({
        csrf_token: token,
        expires_in_seconds: 120,
      }),
    });
    await manager.getValidSession();

    expect(JSON.stringify(localStorage)).not.toContain(token);
    expect(JSON.stringify(sessionStorage)).not.toContain(token);
    expect(document.body.textContent).not.toContain(token);
  });
});
