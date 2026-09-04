import { afterEach, expect, it, vi } from "vitest";
import {
  createAIWritingClient,
  parseAICandidate,
} from "../../frontend/src/features/novel-structure/api/ai-writing";
import type { SecuritySessionManager } from "../../frontend/src/api/security-session";
import {
  chapterId,
  structureErrorEnvelope,
  structureJsonResponse,
} from "./novel-structure-support";

const candidate = (operation = "continue") => ({
  operation,
  text: "候选\n正文",
  model: "local-model",
  context: {
    included_sources: ["current_chapter"],
    omitted_sources: [],
    truncated: false,
    character_count: 10,
  },
});
const session = (): SecuritySessionManager => ({
  getValidSession: vi.fn().mockResolvedValue({
    csrfToken: "ai-test-proof",
    expiresAtMilliseconds: 10000,
  }),
  clear: vi.fn(),
});
afterEach(() => vi.unstubAllGlobals());

it.each(["continue", "rewrite"] as const)(
  "sends exact %s body through the shared client",
  async (operation) => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(structureJsonResponse(candidate(operation)));
    vi.stubGlobal("fetch", request);
    const client = createAIWritingClient(session());
    const signal = new AbortController().signal;
    const result =
      operation === "continue"
        ? await client.continueChapter(chapterId, "  克制  ", signal)
        : await client.rewriteChapterText(chapterId, "甲\n乙", "克制", signal);
    expect(result).toEqual(candidate(operation));
    expect(request).toHaveBeenCalledTimes(1);
    const [url, options] = request.mock.calls[0];
    expect(url).toBe(`/api/v1/chapters/${chapterId}/ai/${operation}`);
    expect(options?.method).toBe("POST");
    expect(options?.signal).toBe(signal);
    expect(new Headers(options?.headers).get("X-CSRF-Token")).toBe(
      "ai-test-proof",
    );
    expect(JSON.parse(options?.body as string)).toEqual(
      operation === "continue"
        ? { instruction: "克制" }
        : { instruction: "克制", text: "甲\n乙" },
    );
  },
);
it("allows empty instruction and drops unknown response fields", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof fetch>().mockResolvedValue(
      structureJsonResponse({
        ...candidate(),
        private_field: "not displayed",
      }),
    ),
  );
  expect(
    await createAIWritingClient(session()).continueChapter(chapterId, ""),
  ).toEqual(candidate());
});
it.each([
  [503, "尚未配置"],
  [502, "无法连接"],
  [504, "超时"],
  [404, "不存在"],
  [422, "输入无效"],
  [409, "上下文已更新"],
  [401, "未能完成"],
  [403, "未能完成"],
  [500, "未能完成"],
] as const)(
  "maps %s without private upstream body",
  async (status, message) => {
    const proof = session();
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      structureJsonResponse(structureErrorEnvelope("PRIVATE_AI_FAILURE"), {
        status,
      }),
    );
    vi.stubGlobal("fetch", request);
    const client = createAIWritingClient(proof);
    await expect(client.continueChapter(chapterId, "")).rejects.toThrow(
      message,
    );
    await expect(
      client.rewriteChapterText(chapterId, "正文", ""),
    ).rejects.not.toThrow("PRIVATE_AI_FAILURE");
    expect(request).toHaveBeenCalledTimes(2);
    expect(proof.clear).toHaveBeenCalledTimes(
      status === 401 || status === 403 ? 2 : 0,
    );
  },
);
it("handles network and session errors safely without retries", async () => {
  const request = vi
    .fn<typeof fetch>()
    .mockRejectedValue(new TypeError("PRIVATE_AI_FAILURE"));
  vi.stubGlobal("fetch", request);
  await expect(
    createAIWritingClient(session()).continueChapter(chapterId, ""),
  ).rejects.toThrow("本地连接");
  const proof = session();
  vi.mocked(proof.getValidSession).mockRejectedValue(
    new Error("PRIVATE_AI_FAILURE"),
  );
  await expect(
    createAIWritingClient(proof).continueChapter(chapterId, ""),
  ).rejects.toThrow("本地连接");
  expect(request).toHaveBeenCalledTimes(1);
});
it.each([
  null,
  [],
  {},
  { ...candidate(), operation: "rewrite" },
  { ...candidate(), text: null },
  { ...candidate(), text: " " },
  { ...candidate(), text: "x".repeat(50001) },
  { ...candidate(), model: null },
  { ...candidate(), model: "bad model" },
  { ...candidate(), context: null },
  ...[
    { included_sources: null },
    { included_sources: [1] },
    { included_sources: ["unknown"] },
    { omitted_sources: null },
    { truncated: null },
    { character_count: null },
    { character_count: 1.5 },
    { character_count: -1 },
    { character_count: 60001 },
  ].map((context) => ({
    ...candidate(),
    context: { ...candidate().context, ...context },
  })),
])("rejects malformed candidate %#", (value) => {
  expect(() => parseAICandidate(value, "continue")).toThrow("无法安全读取");
});
it("rejects invalid requests before transport", async () => {
  const request = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", request);
  const client = createAIWritingClient(session());
  for (const [id, instruction] of [
    ["bad", ""],
    [chapterId, "\u0000"],
    [chapterId, "x".repeat(4001)],
  ])
    await expect(client.continueChapter(id, instruction)).rejects.toThrow(
      "输入无效",
    );
  for (const text of ["", " ", "\u0000", "x".repeat(50001)])
    await expect(
      client.rewriteChapterText(chapterId, text, ""),
    ).rejects.toThrow("输入无效");
  expect(request).not.toHaveBeenCalled();
});
