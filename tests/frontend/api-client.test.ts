import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getJson,
  joinApiPath,
} from "../../frontend/src/api/client";
import { ApiError } from "../../frontend/src/api/errors";

interface ExamplePayload {
  readonly value: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function decodeExample(value: unknown): ExamplePayload {
  if (!isRecord(value) || typeof value.value !== "string") {
    throw new Error("Unexpected example payload.");
  }

  return { value: value.value };
}

function mockFetchResponse(response: Response) {
  const fetchMock = vi.fn<typeof fetch>();
  fetchMock.mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("typed API client", () => {
  it("joins relative API paths without producing duplicate separators", () => {
    expect(joinApiPath("/api/v1/", "/health/live")).toBe(
      "/api/v1/health/live",
    );
    expect(() => joinApiPath("/api/v1", "https://example.invalid/data")).toThrow(
      "API 请求路径必须是相对路径。",
    );
    expect(() => joinApiPath("/api/v1", "//example.invalid/data")).toThrow(
      "API 请求路径必须是相对路径。",
    );
    expect(() => joinApiPath("/api/v1", "../outside")).toThrow(
      "API 请求路径不能包含相对目录段。",
    );
  });

  it("returns decoded JSON and reads the response request ID", async () => {
    const fetchMock = mockFetchResponse(
      new Response(JSON.stringify({ value: "ready" }), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "req_success",
        },
      }),
    );
    const controller = new AbortController();

    const result = await getJson("/status", decodeExample, {
      signal: controller.signal,
    });

    expect(result).toEqual({
      data: { value: "ready" },
      requestId: "req_success",
    });
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/status");
    expect(init?.method).toBe("GET");
    expect(init?.signal).toBe(controller.signal);
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  it("maps the frozen backend error envelope", async () => {
    mockFetchResponse(
      new Response(
        JSON.stringify({
          error: {
            code: "VALIDATION_ERROR",
            message: "请求参数无效。",
            details: { errors: [] },
            retryable: false,
            suggested_action: null,
          },
          request_id: "req_body",
        }),
        {
          status: 422,
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": "req_body",
          },
        },
      ),
    );

    const error = await getJson("validation", decodeExample).catch(
      (reason: unknown) => reason,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "VALIDATION_ERROR",
      message: "请求参数无效。",
      details: { errors: [] },
      retryable: false,
      suggestedAction: null,
      requestId: "req_body",
    });
  });

  it("converts a non-JSON failure without exposing its response body", async () => {
    mockFetchResponse(
      new Response("<html>private gateway detail</html>", {
        status: 503,
        headers: {
          "Content-Type": "text/html",
          "X-Request-ID": "req_non_json",
        },
      }),
    );

    const error = await getJson("readiness", decodeExample).catch(
      (reason: unknown) => reason,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 503,
      code: "HTTP_ERROR",
      requestId: "req_non_json",
      retryable: false,
    });
    expect(error).not.toHaveProperty(
      "message",
      expect.stringContaining("private gateway detail"),
    );
  });

  it("falls back safely for a JSON error outside the frozen envelope", async () => {
    mockFetchResponse(
      new Response(JSON.stringify({ status: "not_ready", checks: {} }), {
        status: 503,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "req_readiness",
        },
      }),
    );

    await expect(getJson("readiness", decodeExample)).rejects.toMatchObject({
      status: 503,
      code: "HTTP_ERROR",
      requestId: "req_readiness",
    });
  });

  it("converts a structurally invalid success response without leaking decoder details", async () => {
    mockFetchResponse(
      new Response(JSON.stringify({ unexpected: "shape" }), {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": "req_invalid_shape",
        },
      }),
    );

    const error = await getJson("invalid-shape", decodeExample).catch(
      (reason: unknown) => reason,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 200,
      code: "INVALID_RESPONSE",
      requestId: "req_invalid_shape",
    });
    expect(error).not.toHaveProperty(
      "message",
      expect.stringContaining("Unexpected example payload"),
    );
  });

  it("preserves cancellation errors from fetch", async () => {
    const abortError = new DOMException("The operation was aborted.", "AbortError");
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockRejectedValue(abortError);
    vi.stubGlobal("fetch", fetchMock);

    await expect(getJson("cancelled", decodeExample)).rejects.toBe(abortError);
  });
});
