import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type {
  BackendHealthResult,
} from "../../frontend/src/api/health";
import {
  SystemStatus,
  type SystemStatusProps,
} from "../../frontend/src/components/SystemStatus";


type CheckHealth = NonNullable<SystemStatusProps["checkHealth"]>;


function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}


function readyResult(): BackendHealthResult {
  return {
    kind: "ready",
    live: {
      data: { status: "ok", service: "AIWebNovel", version: "0.0.0" },
      requestId: "req_live",
    },
    ready: {
      data: {
        status: "ready",
        checks: {
          configuration: "ok",
          application: "ok",
          database: "ok",
          frontend: "not_required",
        },
      },
      requestId: "req_ready",
    },
  };
}


function notReadyResult(): BackendHealthResult {
  return {
    kind: "backend_not_ready",
    reason: "database",
    requestId: "req_not_ready",
  };
}


describe("SystemStatus", () => {
  it("starts in checking and shows ready only after the real probe resolves", async () => {
    const probe = deferred<BackendHealthResult>();
    const checkHealth = vi.fn<CheckHealth>();
    checkHealth.mockReturnValue(probe.promise);
    render(<SystemStatus checkHealth={checkHealth} />);

    const button = screen.getByRole("button", { name: "重新检查" });
    expect(screen.getByRole("status")).toHaveTextContent(
      "正在检查本地后端状态。",
    );
    expect(button).toBeDisabled();
    expect(checkHealth).toHaveBeenCalledOnce();

    await act(async () => {
      probe.resolve(readyResult());
      await probe.promise;
    });

    expect(screen.getByRole("status")).toHaveTextContent(
      "本地后端已连接，数据库基础检查通过。",
    );
    expect(button).toBeEnabled();
    expect(screen.queryByText(/Codex|模型|小说状态/)).not.toBeInTheDocument();
  });

  it("distinguishes backend_not_ready and shows only a safe reason", async () => {
    const checkHealth = vi.fn<CheckHealth>();
    checkHealth.mockResolvedValue(notReadyResult());
    render(<SystemStatus checkHealth={checkHealth} />);

    expect(
      await screen.findByText("本地后端可访问，但尚未就绪。"),
    ).toBeInTheDocument();
    expect(screen.getByText("数据库基础检查未通过。")).toBeInTheDocument();
    expect(screen.queryByText("当前无法连接本地后端。")).not.toBeInTheDocument();
    expect(screen.queryByText(/Traceback|\\Users\\|sqlite3/)).not.toBeInTheDocument();
  });

  it("maps network failure to backend_unavailable without blaming the database", async () => {
    const checkHealth = vi.fn<CheckHealth>();
    checkHealth.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<SystemStatus checkHealth={checkHealth} />);

    expect(
      await screen.findByText("当前无法连接本地后端。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("数据库基础检查未通过。")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新检查" })).toBeEnabled();
  });

  it("cancels the old attempt, disables duplicate clicks, and applies the new result", async () => {
    const user = userEvent.setup();
    const secondProbe = deferred<BackendHealthResult>();
    const signals: AbortSignal[] = [];
    const checkHealth = vi.fn<CheckHealth>((options) => {
      if (options.signal !== undefined) {
        signals.push(options.signal);
      }
      return signals.length === 1
        ? Promise.resolve(readyResult())
        : secondProbe.promise;
    });
    render(<SystemStatus checkHealth={checkHealth} />);

    expect(
      await screen.findByText("本地后端已连接，数据库基础检查通过。"),
    ).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "重新检查" });

    await user.click(button);

    expect(signals[0].aborted).toBe(true);
    expect(checkHealth).toHaveBeenCalledTimes(2);
    expect(button).toBeDisabled();
    await user.click(button);
    expect(checkHealth).toHaveBeenCalledTimes(2);

    await act(async () => {
      secondProbe.resolve(notReadyResult());
      await secondProbe.promise;
    });

    expect(screen.getByRole("status")).toHaveTextContent(
      "本地后端可访问，但尚未就绪。",
    );
    expect(button).toBeEnabled();
  });

  it("aborts a pending request on unmount without updating React state", async () => {
    const probe = deferred<BackendHealthResult>();
    let signal: AbortSignal | undefined;
    const checkHealth = vi.fn<CheckHealth>((options) => {
      signal = options.signal;
      return probe.promise;
    });
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const view = render(<SystemStatus checkHealth={checkHealth} />);

    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      probe.resolve(readyResult());
      await probe.promise;
    });

    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
