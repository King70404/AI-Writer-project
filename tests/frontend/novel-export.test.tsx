import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../frontend/src/api/errors";
import { ExportManuscriptButton } from "../../frontend/src/features/projects/components/ExportManuscriptButton";
import {
  downloadManuscript,
  exportProjectManuscript,
  manuscriptFilename,
} from "../../frontend/src/features/projects/export";
import { ProjectDetailsPage } from "../../frontend/src/features/projects/pages/ProjectDetailsPage";
import {
  detailClient,
  jsonResponse,
  projectId,
} from "./project-detail-support";

const createUrl = vi.fn<(blob: Blob) => string>();
const revokeUrl = vi.fn<(url: string) => void>();

beforeEach(() => {
  createUrl.mockReset().mockReturnValue("blob:novel-export");
  revokeUrl.mockReset();
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = createUrl;
      static revokeObjectURL = revokeUrl;
    },
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function textResponse(text = "《归途》\n") {
  return new Response(text, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

describe("novel text export", () => {
  it("uses the shared same-origin transport with GET text/plain", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(textResponse());
    vi.stubGlobal("fetch", fetchMock);
    await expect(exportProjectManuscript(projectId)).resolves.toBe(
      "《归途》\n",
    );
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/v1/projects/${projectId}/export.txt`);
    expect(options?.method).toBe("GET");
    expect(options?.credentials).toBe("same-origin");
    expect(new Headers(options?.headers).get("Accept")).toBe("text/plain");
    expect(options?.body).toBeUndefined();
  });

  it("rejects invalid IDs without a request", () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    expect(() => exportProjectManuscript("invalid")).toThrow("项目编号无效。");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects JSON masquerading as a successful text download", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(jsonResponse({ content: "not text" })),
    );
    await expect(exportProjectManuscript(projectId)).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
  });

  it.each([
    ["  归途  ", "归途.txt"],
    ['<>:"/\\|?*', "_________.txt"],
    ["正文\u0000\u001f\u007f", "正文___.txt"],
    ["   ", "novel.txt"],
    ["", "novel.txt"],
  ])("cleans filename %j", (input, expected) => {
    expect(manuscriptFilename(input)).toBe(expected);
  });

  it("downloads a real UTF-8 Blob and releases the anchor and object URL", async () => {
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        expect(this.download).toBe("归途.txt");
        expect(this.href).toBe("blob:novel-export");
        expect(this.isConnected).toBe(true);
      });
    downloadManuscript("《归途》\n", "归途");
    expect(click).toHaveBeenCalledOnce();
    const blob = createUrl.mock.calls[0][0];
    expect(blob.type).toBe("text/plain;charset=utf-8");
    const text = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsText(blob);
    });
    expect(text).toBe("《归途》\n");
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith("blob:novel-export");
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("releases the object URL even if browser download fails", () => {
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      throw new Error("download failed");
    });
    expect(() => downloadManuscript("text", "title")).toThrow(
      "download failed",
    );
    expect(revokeUrl).toHaveBeenCalledOnce();
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("shows the detail-page entry, disables duplicate requests, and returns to idle", async () => {
    let complete!: (response: Response) => void;
    const fetchMock = vi.fn<typeof fetch>().mockReturnValue(
      new Promise<Response>((resolve) => {
        complete = resolve;
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      () => undefined,
    );
    render(
      <MemoryRouter initialEntries={[`/projects/${projectId}`]}>
        <Routes>
          <Route
            path="/projects/:projectId"
            element={<ProjectDetailsPage client={detailClient()} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    const button = await screen.findByRole("button", { name: "导出小说" });
    act(() => {
      fireEvent.click(button);
      fireEvent.click(button);
    });
    expect(screen.getByRole("button", { name: "正在导出…" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledOnce();
    await act(async () => {
      complete(textResponse());
      await Promise.resolve();
    });
    expect(screen.getByRole("button", { name: "导出小说" })).toBeEnabled();
    expect(revokeUrl).toHaveBeenCalledOnce();
    expect(screen.getByRole("heading", { name: "项目版本1" })).toBeVisible();
  });

  it.each([404, 500, "network"])(
    "shows a safe %s failure and allows retry without losing the page",
    async (failure) => {
      const fetchMock = vi.fn<typeof fetch>();
      if (failure === "network")
        fetchMock.mockRejectedValueOnce(
          new TypeError("private network detail"),
        );
      else
        fetchMock.mockResolvedValueOnce(
          jsonResponse(
            {
              error: {
                code: "EXPORT_ERROR",
                message: "private internal detail",
                details: {},
                retryable: false,
                suggested_action: null,
              },
              request_id: "export-test",
            },
            { status: Number(failure) },
          ),
        );
      fetchMock.mockResolvedValueOnce(textResponse());
      vi.stubGlobal("fetch", fetchMock);
      vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
        () => undefined,
      );
      render(
        <>
          <h2>保留项目详情</h2>
          <ExportManuscriptButton projectId={projectId} title="归途" />
        </>,
      );
      const user = userEvent.setup();
      await user.click(screen.getByRole("button", { name: "导出小说" }));
      const alert = await screen.findByRole("alert");
      expect(alert.textContent).toBe(
        failure === 404
          ? "项目不存在，无法导出小说。"
          : "导出失败，请检查连接后重试。",
      );
      expect(alert).not.toHaveTextContent("private");
      expect(
        screen.getByRole("heading", { name: "保留项目详情" }),
      ).toBeVisible();
      await user.click(screen.getByRole("button", { name: "导出小说" }));
      await waitFor(() => expect(revokeUrl).toHaveBeenCalledOnce());
      expect(screen.queryByRole("alert")).toBeNull();
    },
  );

  it("preserves existing safe error envelope semantics", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("unavailable", { status: 503 })),
    );
    await expect(exportProjectManuscript(projectId)).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});
