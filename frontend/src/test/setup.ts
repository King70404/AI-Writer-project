import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

beforeEach(() => {
  const fetchMock = vi.fn<typeof fetch>((_input, init) => {
    return new Promise<Response>((_resolve, reject) => {
      const signal = init?.signal;
      const rejectAsAborted = () => {
        reject(new DOMException("The operation was aborted.", "AbortError"));
      };

      if (signal?.aborted === true) {
        rejectAsAborted();
      } else {
        signal?.addEventListener("abort", rejectAsAborted, { once: true });
      }
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});
