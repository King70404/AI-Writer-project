import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../frontend/src/api/errors";
import { securitySession } from "../../frontend/src/api/security-session";
import {
  importClient,
  type ImportClient,
  type ImportPreview,
} from "../../frontend/src/features/legacy-import/api/client";
import { ImportWorkbench } from "../../frontend/src/features/legacy-import/components/ImportWorkbench";

const preview: ImportPreview = {
  preview_id: "imp_test",
  version: 1,
  source_sha256: "hash",
  expires_at: "2026-11-01T00:00:00Z",
  original_line_endings_normalized: true,
  chapters: [
    { title: "开篇", start: 0, body_start: 0, end: 6, body: "甲😀乙\r\n末" },
  ],
};
const receipt = {
  project_id: "prj_01M3MGBAHPQSF6G3Q5XFVQ5NG1",
  first_chapter_id: "chp_01M3MGBAHPQSF6G3Q5XFVQ5NG1",
};
function client(): ImportClient {
  return {
    preview: vi.fn().mockResolvedValue(preview),
    getPreview: vi.fn().mockResolvedValue(preview),
    update: vi.fn().mockResolvedValue(preview),
    commit: vi.fn().mockResolvedValue(receipt),
    receipt: vi.fn().mockResolvedValue(receipt),
  };
}
const instanceA = "a".repeat(32);
const instanceB = "b".repeat(32);
const loadA = () => Promise.resolve(instanceA);
function show(instance: ImportClient) {
  render(
    <MemoryRouter>
      <ImportWorkbench client={instance} loadInstance={loadA} />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "导入旧稿" }));
}
async function makePreview() {
  fireEvent.change(screen.getByLabelText("或粘贴旧稿"), {
    target: { value: "甲😀乙\r\n末" },
  });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "预览分章" })).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "预览分章" }));
  await screen.findByLabelText("新小说书名");
}
beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("旧稿导入", () => {
  it("预览、提示换行、确认创建并打开第一章，不自动调用模型", async () => {
    const api = client();
    show(api);
    await makePreview();
    expect(screen.getByText(/换行会统一为/)).toBeVisible();
    expect(api.preview).toHaveBeenCalledOnce();
    expect(api.commit).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("新小说书名"), {
      target: { value: "旧稿" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认导入为新小说" }));
    expect(await screen.findByText("小说已创建，旧稿导入完成。")).toBeVisible();
    expect(screen.getByRole("link", { name: "打开第一章" })).toHaveAttribute(
      "href",
      `/projects/${receipt.project_id}/chapters/${receipt.first_chapter_id}/write`,
    );
    const [previewId, input] = vi.mocked(api.commit).mock.calls[0];
    expect(previewId).toBe("imp_test");
    expect(input.title).toBe("旧稿");
    expect(input.preview_version).toBe(1);
    expect(input.source_sha256).toBe("hash");
    expect(typeof input.idempotency_key).toBe("string");
  });
  it("在 emoji 后拆分时使用 Unicode 码点位置，且只有显式确认才创建小说", async () => {
    const api = client();
    show(api);
    await makePreview();
    const area =
      screen.getByLabelText<HTMLTextAreaElement>("第 1 章正文（选择拆分位置）");
    area.setSelectionRange(3, 3);
    fireEvent.select(area);
    fireEvent.click(screen.getByRole("button", { name: "从光标处拆分" }));
    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith("imp_test", 1, [
        { title: "开篇", start: 0, body_start: 0, end: 2 },
        { title: "新章节", start: 2, body_start: 2, end: 6 },
      ]),
    );
    expect(api.commit).not.toHaveBeenCalled();
  });
  it("正文中 CRLF 显示为 LF 后，仍按原文位置拆分，不丢失换行", async () => {
    const api = client();
    show(api);
    await makePreview();
    const area =
      screen.getByLabelText<HTMLTextAreaElement>("第 1 章正文（选择拆分位置）");
    expect(area.value).toBe("甲😀乙\n末");
    area.setSelectionRange(5, 5);
    fireEvent.select(area);
    fireEvent.click(screen.getByRole("button", { name: "从光标处拆分" }));
    await waitFor(() =>
      expect(api.update).toHaveBeenCalledWith("imp_test", 1, [
        { title: "开篇", start: 0, body_start: 0, end: 5 },
        { title: "新章节", start: 5, body_start: 5, end: 6 },
      ]),
    );
  });
  it("网络中断后复用同一幂等请求，不能更改书名导致重复创建", async () => {
    const api = client();
    vi.mocked(api.commit)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(receipt);
    show(api);
    await makePreview();
    fireEvent.change(screen.getByLabelText("新小说书名"), {
      target: { value: "旧稿" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认导入为新小说" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("同一请求");
    expect(screen.getByLabelText("新小说书名")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "再次确认导入" }));
    await screen.findByText("小说已创建，旧稿导入完成。");
    expect(vi.mocked(api.commit).mock.calls[0]).toEqual(
      vi.mocked(api.commit).mock.calls[1],
    );
  });
  it("重开后可恢复服务端预览，不存储原稿", async () => {
    const api = client();
    const view = render(
      <MemoryRouter>
        <ImportWorkbench client={api} loadInstance={loadA} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "导入旧稿" }));
    await makePreview();
    expect(
      localStorage.getItem(`aiwebnovel:legacy-import:v1:${instanceA}`),
    ).not.toContain("甲");
    view.unmount();
    show(api);
    fireEvent.click(
      await screen.findByRole("button", { name: "恢复上次导入预览" }),
    );
    await screen.findByLabelText("新小说书名");
    expect(api.getPreview).toHaveBeenCalledWith("imp_test");
    expect(api.commit).not.toHaveBeenCalled();
  });
  it("无权限覆盖作者原文件，非法编码在客户端拒绝", async () => {
    const api = client();
    show(api);
    const file = new File([new Uint8Array([0xff, 0xfe])], "坏文件.txt", {
      type: "text/plain",
    });
    Object.defineProperty(file, "arrayBuffer", {
      value: () => Promise.resolve(new Uint8Array([0xff, 0xfe]).buffer),
    });
    fireEvent.change(screen.getByLabelText("选择 TXT 或 Markdown 文件"), {
      target: { files: [file] },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "不是有效的 UTF-8",
    );
    expect(api.preview).not.toHaveBeenCalled();
  });
  it("服务器明确拒绝不合法书名后，允许作者修改并重新确认", async () => {
    const api = client();
    vi.mocked(api.commit)
      .mockRejectedValueOnce(
        new ApiError({
          status: 422,
          code: "IMPORT_INVALID",
          message: "Invalid project title",
          details: {},
          retryable: false,
          suggestedAction: null,
          requestId: null,
        }),
      )
      .mockResolvedValueOnce(receipt);
    show(api);
    await makePreview();
    fireEvent.change(screen.getByLabelText("新小说书名"), {
      target: { value: "无效书名" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认导入为新小说" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("检查书名");
    expect(screen.getByLabelText("新小说书名")).toBeEnabled();
    fireEvent.change(screen.getByLabelText("新小说书名"), {
      target: { value: "有效书名" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认导入为新小说" }));
    await screen.findByText("小说已创建，旧稿导入完成。");
    expect(vi.mocked(api.commit).mock.calls[0][1].idempotency_key).not.toBe(
      vi.mocked(api.commit).mock.calls[1][1].idempotency_key,
    );
  });
  it("不同数据根不显示或恢复另一数据根的导入", async () => {
    const api = client();
    const view = render(
      <MemoryRouter>
        <ImportWorkbench client={api} loadInstance={loadA} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "导入旧稿" }));
    await makePreview();
    view.unmount();
    render(
      <MemoryRouter>
        <ImportWorkbench
          client={api}
          loadInstance={() => Promise.resolve(instanceB)}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "导入旧稿" }));
    fireEvent.change(screen.getByLabelText("或粘贴旧稿"), {
      target: { value: "新数据根" },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "预览分章" })).toBeEnabled(),
    );
    expect(
      screen.queryByRole("button", { name: "恢复上次导入预览" }),
    ).not.toBeInTheDocument();
    expect(api.getPreview).not.toHaveBeenCalled();
  });
  it("无法确认数据根时不上传文本", async () => {
    const api = client();
    render(
      <MemoryRouter>
        <ImportWorkbench
          client={api}
          loadInstance={() => Promise.reject(new Error("offline"))}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "导入旧稿" }));
    fireEvent.change(screen.getByLabelText("或粘贴旧稿"), {
      target: { value: "原稿" },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "无法确认当前数据根",
    );
    expect(screen.getByRole("button", { name: "预览分章" })).toBeDisabled();
    expect(api.preview).not.toHaveBeenCalled();
  });
  it("导入错误显示中文和可执行操作", async () => {
    const api = client();
    vi.mocked(api.preview).mockRejectedValue(
      new ApiError({
        status: 422,
        code: "IMPORT_TOO_MANY_CHAPTERS",
        message: "English internal error",
        details: {},
        retryable: false,
        suggestedAction: null,
        requestId: null,
      }),
    );
    show(api);
    fireEvent.change(screen.getByLabelText("或粘贴旧稿"), {
      target: { value: "原稿" },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "预览分章" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "预览分章" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "章节超过 500 章，请分批导入",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent("English");
  });
  it("提交已成功但响应丢失时可从回执恢复", async () => {
    const api = client();
    localStorage.setItem(
      `aiwebnovel:legacy-import:v1:${instanceA}`,
      JSON.stringify({
        previewId: "imp_test",
        pending: {
          preview_version: 1,
          source_sha256: "hash",
          idempotency_key: "key",
          title: "旧稿",
        },
      }),
    );
    show(api);
    fireEvent.click(
      await screen.findByRole("button", { name: "恢复上次导入预览" }),
    );
    await screen.findByText("小说已创建，旧稿导入完成。");
    expect(api.receipt).toHaveBeenCalledWith("imp_test");
    expect(api.commit).not.toHaveBeenCalled();
  });
});

describe("旧稿上传 API", () => {
  it("以 Unicode 码点偏移分片并使用 CSRF，不向单请求发送超过 100000 个字符", async () => {
    vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
      csrfToken: "test-token",
      expiresAtMilliseconds: Date.now() + 60000,
    });
    const offsets: number[] = [];
    let current = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit) => {
        if (typeof init.body !== "string")
          throw new Error("Expected JSON body");
        const body = JSON.parse(init.body) as {
          offset?: number;
          text?: string;
        };
        let data: unknown;
        if (url.endsWith("/uploads")) data = { upload_id: "upload1" };
        else if (url.endsWith("/chunks")) {
          offsets.push(body.offset!);
          current += Array.from(body.text!).length;
          data = { next_offset: current };
        } else data = preview;
        expect(new Headers(init.headers).get("X-CSRF-Token")).toBe(
          "test-token",
        );
        return Promise.resolve(
          new Response(JSON.stringify(data), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }),
    );
    await expect(
      importClient.preview("😀".repeat(100001), "single"),
    ).resolves.toEqual(preview);
    expect(offsets).toEqual([0, 100000]);
  });
});
