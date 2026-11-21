import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { securitySession } from "../../frontend/src/api/security-session";
import {
  chapterDraftClient,
  parseDraft,
  type ChapterDraftClient,
} from "../../frontend/src/features/novel-structure/api/chapter-draft";
import { ChapterDraftPanel } from "../../frontend/src/features/novel-structure/components/ChapterDraftPanel";
import { OPERATION_LABELS } from "../../frontend/src/features/usage/api/usage";
import { allowedAnalysisEstimate } from "./analysis-estimate-support";

const chapterId = "chp_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const baseRevision = "chv_base";
const SEG_A = "甲" + "风".repeat(219);
const SEG_B = "乙" + "风".repeat(219);

beforeEach(() => {
  vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
    csrfToken: "fake-csrf-proof".repeat(3),
    expiresAtMilliseconds: Date.now() + 60_000,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
});

function segment(index: number, text: string, status = "pending") {
  return {
    index,
    attempt: index + 1,
    text,
    characters: text.length,
    model: "fake",
    status,
    adopted_revision_id: status === "adopted" ? "chv_after" : null,
  };
}

function raw(overrides: Record<string, unknown> = {}) {
  return {
    id: "draft-1",
    project_id: "prj_x",
    chapter_id: chapterId,
    version: 1,
    status: "ready",
    model: {
      id: "default-local",
      name: "本机模型",
      kind: "local",
      base_url: "http://127.0.0.1:1",
      model: "fake",
      max_output_tokens: 100,
    },
    instruction: "",
    max_segments: 10,
    max_output_characters: 3000,
    attempts: 0,
    generated_characters: 0,
    remaining_requests: 10,
    remaining_characters: 3000,
    can_send: true,
    base_revision_id: baseRevision,
    current_revision_id: baseRevision,
    included_sources: ["current_chapter"],
    omitted_sources: [],
    context_truncated: false,
    segments: [],
    failures: [],
    receipts: [],
    last_error: null,
    writing_job_id: null,
    created_at: "t",
    updated_at: "t",
    next_request_preview: "[system]\n本次候选稿",
    ...overrides,
  };
}

const ready = parseDraft(raw(), chapterId);
const generated = parseDraft(
  raw({
    version: 4,
    attempts: 2,
    generated_characters: 440,
    remaining_requests: 8,
    remaining_characters: 2560,
    segments: [segment(0, SEG_A), segment(1, SEG_B)],
  }),
  chapterId,
);

function json(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

function fakeClient(overrides: Partial<ChapterDraftClient> = {}) {
  return {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue(generated),
    prepare: vi.fn().mockResolvedValue(ready),
    estimate: vi.fn().mockResolvedValue(allowedAnalysisEstimate()),
    send: vi.fn().mockResolvedValue(generated),
    adopt: vi.fn(),
    ...overrides,
  } as unknown as ChapterDraftClient & {
    list: ReturnType<typeof vi.fn>;
    get: ReturnType<typeof vi.fn>;
    prepare: ReturnType<typeof vi.fn>;
    send: ReturnType<typeof vi.fn>;
    adopt: ReturnType<typeof vi.fn>;
    estimate: ReturnType<typeof vi.fn>;
  };
}

describe("chapter draft API", () => {
  it("uses the chapter draft endpoints with CSRF and strict parsing", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockImplementation(() => Promise.resolve(json(raw(), 201)));
    await expect(
      chapterDraftClient.prepare(chapterId, {
        profileId: "default-local",
        instruction: "夜戏",
        maxSegments: 4,
        maxOutputCharacters: 900,
      }),
    ).resolves.toEqual(ready);
    fetcher.mockImplementation(() =>
      Promise.resolve(json(allowedAnalysisEstimate())),
    );
    await chapterDraftClient.estimate(chapterId, ready.id);
    fetcher.mockImplementation(() => Promise.resolve(json(raw())));
    await chapterDraftClient.send(chapterId, ready, 3, false);
    await chapterDraftClient.adopt(chapterId, ready.id, "key-12345678", [0]);
    await chapterDraftClient.adopt(chapterId, ready.id, "key-87654321", null);
    const calls = fetcher.mock.calls.map(([url, options]) => [
      options?.method,
      url,
      options?.body ?? null,
    ]);
    const root = `/api/v1/chapters/${chapterId}/ai/drafts`;
    expect(calls).toEqual([
      [
        "POST",
        root,
        JSON.stringify({
          profile_id: "default-local",
          instruction: "夜戏",
          max_segments: 4,
          max_output_characters: 900,
        }),
      ],
      ["GET", `${root}/draft-1/estimate`, null],
      [
        "POST",
        `${root}/draft-1/send`,
        JSON.stringify({
          expected_version: 1,
          cloud_consent: false,
          segments: 3,
        }),
      ],
      [
        "POST",
        `${root}/draft-1/adopt`,
        JSON.stringify({
          idempotency_key: "key-12345678",
          segment_indexes: [0],
        }),
      ],
      [
        "POST",
        `${root}/draft-1/adopt`,
        JSON.stringify({ idempotency_key: "key-87654321" }),
      ],
    ]);
    const headers = new Headers(fetcher.mock.calls[0][1]?.headers);
    expect(headers.get("X-CSRF-Token")).toBe("fake-csrf-proof".repeat(3));
  });

  it("rejects foreign or malformed drafts and maps a stale adoption", async () => {
    expect(() => parseDraft(raw(), "chp_other")).toThrow(/无法安全读取/u);
    expect(() =>
      parseDraft(raw({ segments: [segment(1, SEG_A)] }), chapterId),
    ).toThrow();
    expect(() => parseDraft(raw({ status: "done" }), chapterId)).toThrow();
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockImplementation(() =>
      Promise.resolve(
        json(
          {
            error: {
              code: "CHAPTER_DRAFT_STALE",
              message: "changed",
              details: {},
              retryable: false,
              suggested_action: null,
            },
            request_id: "req",
          },
          409,
        ),
      ),
    );
    await expect(
      chapterDraftClient.adopt(chapterId, ready.id, "key-12345678", [0]),
    ).rejects.toMatchObject({ code: "CHAPTER_DRAFT_STALE" });
    await expect(
      chapterDraftClient.adopt(chapterId, ready.id, "key-12345678", [0]),
    ).rejects.toThrow(/候选稿已保留/u);
    expect(OPERATION_LABELS.chapter_draft).toBe("章节候选稿");
  });
});

describe("chapter draft panel", () => {
  function renderPanel(
    client: ChapterDraftClient,
    {
      savedRevisionId = baseRevision,
      acceptExternal = vi.fn(async (commit: () => Promise<void>) => {
        await commit();
        return true;
      }),
    } = {},
  ) {
    render(
      <ChapterDraftPanel
        chapterId={chapterId}
        profileId="default-local"
        savedContent="雨😀雨。"
        savedRevisionId={savedRevisionId}
        saved
        acceptExternal={acceptExternal}
        client={client}
      />,
    );
    return acceptExternal;
  }

  it("prepares without sending, then sends only after the estimate allows it", async () => {
    const client = fakeClient();
    renderPanel(client);
    fireEvent.change(screen.getByLabelText("最多请求次数"), {
      target: { value: "4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "准备候选稿" }));
    await screen.findByText(/状态：可以继续生成/u);
    expect(client.prepare).toHaveBeenCalledWith(chapterId, {
      profileId: "default-local",
      instruction: "",
      maxSegments: 4,
      maxOutputCharacters: 3000,
    });
    expect(client.send).not.toHaveBeenCalled();
    const send = await screen.findByRole("button", { name: "确认发送" });
    await waitFor(() => expect(send).toBeEnabled());
    fireEvent.change(screen.getByLabelText("本次生成段数"), {
      target: { value: "2" },
    });
    fireEvent.click(send);
    await waitFor(() =>
      expect(client.send).toHaveBeenCalledWith(chapterId, ready, 2, false),
    );
    expect(await screen.findByText(SEG_A)).toBeInTheDocument();
    expect(screen.getByText(SEG_B)).toBeInTheDocument();
  });

  it("blocks sending when the strict budget refuses", async () => {
    const client = fakeClient({
      list: vi.fn().mockResolvedValue([{ id: "draft-1" }]),
      get: vi.fn().mockResolvedValue(ready),
      estimate: vi.fn().mockResolvedValue(
        allowedAnalysisEstimate({
          decision: "refused",
          budget_mode: "strict",
        }),
      ),
    });
    renderPanel(client);
    const send = await screen.findByRole("button", { name: "确认发送" });
    await waitFor(() => expect(client.estimate).toHaveBeenCalled());
    expect(send).toBeDisabled();
  });

  it("adopts one selected segment or the whole draft with stable receipts", async () => {
    const adopted = parseDraft(
      raw({
        ...raw(),
        version: 5,
        current_revision_id: "chv_after",
        segments: [segment(0, SEG_A, "adopted"), segment(1, SEG_B)],
      }),
      chapterId,
    );
    const client = fakeClient({
      list: vi.fn().mockResolvedValue([{ id: "draft-1" }]),
      adopt: vi.fn().mockResolvedValue(adopted),
    });
    const accept = renderPanel(client);
    await screen.findByText(SEG_A);
    fireEvent.click(screen.getByLabelText("选择第 1 段"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选段落" }));
    await screen.findByText("已采用，正文已更新。");
    expect(accept).toHaveBeenCalledTimes(1);
    const [, draftId, key, indexes] = client.adopt.mock.calls[0] as [
      string,
      string,
      string,
      readonly number[] | null,
    ];
    expect([draftId, indexes]).toEqual(["draft-1", [0]]);
    expect(key).toMatch(/^[A-Za-z0-9_-]{8,}$/u);
  });

  it("keeps the draft and refuses adoption after a hand edit", async () => {
    const client = fakeClient({
      list: vi.fn().mockResolvedValue([{ id: "draft-1" }]),
    });
    renderPanel(client, { savedRevisionId: "chv_hand_edited" });
    await screen.findByText(SEG_A);
    expect(
      screen.getByText(/正文在候选稿基线之后已被修改，不能采用/u),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "采用全部未采用段落" }),
    ).toBeDisabled();
    expect(screen.queryByRole("button", { name: "确认发送" })).toBeNull();
    expect(client.adopt).not.toHaveBeenCalled();
  });

  it("shows a server stale refusal without losing the draft", async () => {
    const stale = Object.assign(new Error("stale"), {});
    const client = fakeClient({
      list: vi.fn().mockResolvedValue([{ id: "draft-1" }]),
      adopt: vi.fn().mockRejectedValue(stale),
    });
    renderPanel(client);
    await screen.findByText(SEG_A);
    fireEvent.click(screen.getByRole("button", { name: "采用全部未采用段落" }));
    await screen.findByRole("alert");
    expect(client.adopt.mock.calls[0][3]).toBeNull();
    expect(screen.getByText(SEG_A)).toBeInTheDocument();
  });

  it("shows failure evidence and offers only an explicit retry", async () => {
    const failed = parseDraft(
      raw({
        status: "failed",
        attempts: 2,
        segments: [segment(0, SEG_A)],
        failures: [
          {
            attempt: 2,
            error: "ChapterDraftOutputInvalid",
            evidence: "太短",
            evidence_truncated: false,
            at: "t",
          },
        ],
        last_error: "ChapterDraftOutputInvalid",
      }),
      chapterId,
    );
    const client = fakeClient({
      list: vi.fn().mockResolvedValue([{ id: "draft-1" }]),
      get: vi.fn().mockResolvedValue(failed),
    });
    renderPanel(client);
    expect(
      await screen.findByText(/第 2 次请求：模型返回的字数不在本段范围内/u),
    ).toBeInTheDocument();
    expect(screen.getByText("太短")).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "确认重试（新的计费请求）" }),
    ).toBeInTheDocument();
    expect(client.send).not.toHaveBeenCalled();
  });
});
