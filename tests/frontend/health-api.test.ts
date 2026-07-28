import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../frontend/src/api/errors";
import {
  checkBackendHealth,
  getLiveHealth,
  getReadyHealth,
  HealthCheckTimeoutError,
} from "../../frontend/src/api/health";

function response(body: unknown, status = 200, requestId = "req_health_test") {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": requestId,
    },
  });
}

function liveBody() {
  return { status: "ok", service: "AIWebNovel", version: "0.0.0" };
}

function readyBody(
  status: "ready" | "not_ready" = "ready",
  database: "ok" | "failed" = "ok",
) {
  return {
    status,
    checks: {
      configuration: "ok",
      application: "ok",
      database,
      frontend: "not_required",
    },
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("frontend health API", () => {
  it("parses live health, preserves the request ID, and passes AbortSignal", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(response(liveBody(), 200, "req_live"));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    const result = await getLiveHealth(controller.signal);

    expect(result).toEqual({
      data: liveBody(),
      requestId: "req_live",
      status: 200,
    });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/health/live");
    expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  it("parses ready success and normalizes the legacy missing frontend check", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(
      response({
        status: "ready",
        checks: {
          configuration: "ok",
          application: "ok",
          database: "ok",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await getReadyHealth();

    expect(result.data.checks.frontend).toBe("not_required");
    expect(result.data.status).toBe("ready");
  });

  it("decodes a valid 503 not-ready response without pretending it is ready", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(
      response(readyBody("not_ready", "failed"), 503, "req_not_ready"),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await getReadyHealth();

    expect(result.requestId).toBe("req_not_ready");
    expect(result.data).toMatchObject({
      status: "not_ready",
      checks: { database: "failed" },
    });
  });

  it("keeps a standard 503 error envelope as ApiError", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockResolvedValue(
      response(
        {
          error: {
            code: "SERVICE_UNAVAILABLE",
            message: "服务尚未就绪。",
            details: {},
            retryable: true,
            suggested_action: "稍后重新检查。",
          },
          request_id: "req_error_body",
        },
        503,
        "req_error_header",
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const error = await getReadyHealth().catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 503,
      code: "SERVICE_UNAVAILABLE",
      requestId: "req_error_header",
    });
  });

  it("uses one controlled signal for live and ready and returns real readiness", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock
      .mockResolvedValueOnce(response(liveBody(), 200, "req_live_probe"))
      .mockResolvedValueOnce(response(readyBody(), 200, "req_ready_probe"));
    vi.stubGlobal("fetch", fetchMock);

    const result = await checkBackendHealth({ timeoutMs: 1_000 });

    expect(result.kind).toBe("ready");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const liveSignal = fetchMock.mock.calls[0][1]?.signal;
    const readySignal = fetchMock.mock.calls[1][1]?.signal;
    expect(liveSignal).toBeInstanceOf(AbortSignal);
    expect(readySignal).toBe(liveSignal);
  });

  it("classifies a database failure as backend_not_ready", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock
      .mockResolvedValueOnce(response(liveBody()))
      .mockResolvedValueOnce(response(readyBody("not_ready", "failed"), 503));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      checkBackendHealth({ timeoutMs: 1_000 }),
    ).resolves.toMatchObject({
      kind: "backend_not_ready",
      reason: "database",
    });
  });

  it("preserves a live network failure for unavailable-state handling", async () => {
    const networkError = new TypeError("Failed to fetch");
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockRejectedValue(networkError);
    vi.stubGlobal("fetch", fetchMock);

    await expect(checkBackendHealth({ timeoutMs: 1_000 })).rejects.toBe(
      networkError,
    );
  });

  it("aborts a stalled request at the controlled timeout", async () => {
    vi.useFakeTimers();
    const requestSignals: AbortSignal[] = [];
    const fetchMock = vi.fn<typeof fetch>((_input, init) => {
      const requestSignal = init?.signal;
      if (requestSignal !== null && requestSignal !== undefined) {
        requestSignals.push(requestSignal);
      }
      return new Promise<Response>((_resolve, reject) => {
        requestSignal?.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const probe = checkBackendHealth({ timeoutMs: 50 });
    const rejection = probe.catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(50);

    await expect(rejection).resolves.toBeInstanceOf(HealthCheckTimeoutError);
    expect(requestSignals).toHaveLength(1);
    expect(requestSignals[0]?.aborted).toBe(true);
  });
});
