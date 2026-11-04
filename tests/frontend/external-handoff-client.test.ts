import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { securitySession } from "../../frontend/src/api/security-session";
import { handoffClient } from "../../frontend/src/features/external-handoff/client";

const preview = {
  handoff_id: null,
  chapter_id: "ch 1",
  base_version: 2,
  context_sha256: "a".repeat(64),
  context: "本章原文",
};
const candidate = {
  candidate_id: "c1",
  text: "外部候选",
  status: "pending",
  base_version: 2,
};
const stored = { ...preview, handoff_id: "h1", candidates: [candidate] };

function json(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

let fetcher: ReturnType<typeof vi.fn<typeof fetch>>;

beforeEach(() => {
  vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
    csrfToken: "fake-csrf-proof".repeat(3),
    expiresAtMilliseconds: Date.now() + 60_000,
  });
  fetcher = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetcher);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
});

function call(index: number): { url: string; init: RequestInit } {
  const [url, init] = fetcher.mock.calls[index]!;
  return { url: String(url), init: init ?? {} };
}

function header(init: RequestInit, name: string): string | null {
  return new Headers(init.headers).get(name);
}

describe("外部交接 API 客户端", () => {
  it("预览与确认带 CSRF 证明，并按章节编码路径", async () => {
    fetcher.mockImplementation(() => Promise.resolve(json(preview)));
    const input = { instruction: "续写", include_manuscript: true };
    await expect(handoffClient.preview("ch 1", input)).resolves.toEqual(
      preview,
    );
    fetcher.mockImplementation(() =>
      Promise.resolve(json({ ...preview, handoff_id: "h1" })),
    );
    const created = await handoffClient.create("ch 1", input);
    expect(created.handoff_id).toBe("h1");
    const first = call(0);
    expect(first.url).toContain("/chapters/ch%201/handoffs/preview");
    expect(first.init.method).toBe("POST");
    expect(header(first.init, "X-CSRF-Token")).toBe(
      "fake-csrf-proof".repeat(3),
    );
    expect(JSON.parse(first.init.body as string)).toEqual(input);
    expect(call(1).url).toMatch(/\/chapters\/ch%201\/handoffs$/u);
  });

  it("读取交接列表并解析候选", async () => {
    fetcher.mockResolvedValue(json([stored]));
    const list = await handoffClient.list("ch1");
    expect(list).toHaveLength(1);
    expect(list[0]!.candidates[0]!.status).toBe("pending");
  });

  it.each([
    ["不是数组", { items: [] }],
    ["缺少交接编号", [{ ...stored, handoff_id: null }]],
    ["候选不是数组", [{ ...stored, candidates: "x" }]],
    [
      "候选状态未知",
      [{ ...stored, candidates: [{ ...candidate, status: "x" }] }],
    ],
    ["版本为负数", [{ ...stored, base_version: -1 }]],
    ["版本不是整数", [{ ...stored, base_version: 1.5 }]],
    ["文本不是字符串", [{ ...stored, context: 1 }]],
    ["条目不是对象", [null]],
    ["条目是数组", [[]]],
  ])("拒绝无法读取的列表：%s", async (_name, body) => {
    fetcher.mockResolvedValue(json(body));
    await expect(handoffClient.list("ch1")).rejects.toThrow();
  });

  it("下载交接包只读取，不带写入证明", async () => {
    fetcher.mockResolvedValue(new Response("zip"));
    const blob = await handoffClient.download("ch1", "h/1");
    expect(blob.size).toBe(3);
    const { url, init } = call(0);
    expect(url).toContain("/chapters/ch1/handoffs/h%2F1/download");
    expect(init.method).toBeUndefined();
    expect(init.credentials).toBe("same-origin");
  });

  it("下载失败给出可读提示", async () => {
    fetcher.mockResolvedValue(new Response("", { status: 404 }));
    await expect(handoffClient.download("ch1", "h1")).rejects.toThrow(
      "交接包下载失败",
    );
  });

  it("导入返回文件原样发送并解析候选", async () => {
    fetcher.mockResolvedValue(json(candidate));
    const raw = '{"format_version":1}';
    await expect(handoffClient.candidate("ch1", "h1", raw)).resolves.toEqual(
      candidate,
    );
    const { url, init } = call(0);
    expect(url).toContain("/chapters/ch1/handoffs/h1/candidates");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(raw);
    expect(header(init, "Content-Type")).toBe("application/json");
    expect(header(init, "X-CSRF-Token")).toBe("fake-csrf-proof".repeat(3));
  });

  it("导入被拒绝时不显示服务端原文", async () => {
    fetcher.mockResolvedValue(json({ detail: "secret" }, 422));
    await expect(handoffClient.candidate("ch1", "h1", "{}")).rejects.toThrow(
      "导入失败：请检查文件格式、任务归属、长度及正文版本。",
    );
  });

  it("采用候选带版本前提与幂等键", async () => {
    fetcher.mockResolvedValue(json({ ...candidate, status: "adopted" }));
    await handoffClient.adopt("ch1", "h1", "c/1", '"3"', "key-1");
    const { url, init } = call(0);
    expect(url).toContain("/chapters/ch1/handoffs/h1/candidates/c%2F1/adopt");
    expect(header(init, "If-Match")).toBe('"3"');
    expect(JSON.parse(init.body as string)).toEqual({
      idempotency_key: "key-1",
    });
  });
});
