import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { securitySession } from "../../frontend/src/api/security-session";
import {
  ForeshadowExtractionError,
  foreshadowExtractionClient,
  parseExtraction,
  parseRangePreview,
  type ForeshadowExtractionClient,
} from "../../frontend/src/features/story-control/api/foreshadowExtraction";
import type {
  ArcPlan,
  StoryControlClient,
} from "../../frontend/src/features/story-control/api/storyControl";
import { ForeshadowExtractionPanel } from "../../frontend/src/features/story-control/components/ForeshadowExtractionPanel";
import { StoryControlPanel } from "../../frontend/src/features/story-control/components/StoryControlPanel";
import { allowedAnalysisEstimate } from "./analysis-estimate-support";

const projectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const chapterA = "chp_a";
const chapterB = "chp_b";
const volumeA = "vol_a";

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

const plan: ArcPlan = {
  project_id: projectId,
  goals: [],
  volumes: [{ volume_id: volumeA, title: "卷一", position: 1 }],
  chapters: [
    {
      chapter_id: chapterA,
      volume_id: volumeA,
      title: "第一章",
      volume_position: 1,
      position: 1,
      revision_id: "chv_a",
    },
    {
      chapter_id: chapterB,
      volume_id: volumeA,
      title: "第二章",
      volume_position: 1,
      position: 2,
      revision_id: "chv_b",
    },
  ],
  characters: [],
};

function frozenChapter(chapterId: string, position: number, characters = 20) {
  return {
    chapter_id: chapterId,
    volume_id: volumeA,
    title: position === 1 ? "第一章" : "第二章",
    volume_position: 1,
    position,
    revision_id: `chv_${position}`,
    characters,
  };
}

function raw(overrides: Record<string, unknown> = {}) {
  const merged = rawBase(overrides);
  return {
    ...merged,
    effective_checks:
      "effective_checks" in overrides
        ? overrides.effective_checks
        : merged.checks,
    adoptions: (merged.adoptions as Record<string, unknown>[]).map((item) => ({
      edited: false,
      ...item,
    })),
  };
}

function rawBase(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    id: "extraction-1",
    project_id: projectId,
    version: 1,
    status: "ready",
    attempts: 0,
    model: {
      id: "default-local",
      name: "本机模型",
      kind: "local",
      base_url: "http://127.0.0.1:1",
      model: "fake",
      max_output_tokens: 100,
    },
    author_request: "",
    chapters: [frozenChapter(chapterA, 1), frozenChapter(chapterB, 2)],
    total_characters: 40,
    threads: [
      {
        id: "thread-1",
        version: 1,
        title: "少主身世",
        content: "",
        status: "planned",
        setup_chapter_ids: [],
      },
    ],
    threads_omitted: 0,
    summary: null,
    cards: [],
    checks: [],
    error: null,
    evidence: null,
    evidence_truncated: false,
    adoptions: [],
    edits: [],
    undos: [],
    created_at: "t",
    updated_at: "t",
    request_preview: "[system]\n只输出 JSON\n\n[user]\n{}",
    ...overrides,
  };
}
const cards = [
  {
    kind: "new_thread",
    title: "船夫的旧伤",
    content: "旧布下的往事",
    chapter_id: chapterA,
    quote: "船夫左臂缠着旧布",
    reason: "刻意遮掩",
  },
  {
    kind: "payoff",
    thread_id: "thread-1",
    chapter_id: chapterB,
    quote: "替少主挡下的一刀",
    reason: "",
  },
  {
    kind: "new_thread",
    title: "火因",
    content: "",
    chapter_id: chapterB,
    quote: "原文没有的句子",
    reason: "",
  },
];
const checks = [
  { valid: true, problem: null },
  { valid: true, problem: null },
  { valid: false, problem: "quote_not_found" },
];
const ready = parseExtraction(raw(), projectId);
const completed = parseExtraction(
  raw({ version: 3, status: "completed", summary: "一新一兑", cards, checks }),
  projectId,
);
const rangePreview = parseRangePreview({
  chapters: [frozenChapter(chapterA, 1, 12), frozenChapter(chapterB, 2, 30)],
  total_characters: 42,
  max_chapters: 10,
  max_total_characters: 30000,
  open_threads: 1,
  threads_omitted: 0,
  problem: null,
});

function fakeClient(overrides: Partial<ForeshadowExtractionClient> = {}) {
  return {
    models: vi
      .fn()
      .mockResolvedValue([
        { id: "default-local", name: "本机模型", kind: "local" },
      ]),
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue(completed),
    preview: vi.fn().mockResolvedValue(rangePreview),
    prepare: vi.fn().mockResolvedValue(ready),
    estimate: vi.fn().mockResolvedValue(allowedAnalysisEstimate()),
    send: vi.fn().mockResolvedValue(completed),
    adopt: vi.fn(),
    editCard: vi.fn(),
    undo: vi.fn(),
    ...overrides,
  } as unknown as ForeshadowExtractionClient & {
    editCard: ReturnType<typeof vi.fn>;
    undo: ReturnType<typeof vi.fn>;
    get: ReturnType<typeof vi.fn>;
    preview: ReturnType<typeof vi.fn>;
    prepare: ReturnType<typeof vi.fn>;
    send: ReturnType<typeof vi.fn>;
    adopt: ReturnType<typeof vi.fn>;
    estimate: ReturnType<typeof vi.fn>;
  };
}

function json(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

describe("foreshadow extraction API", () => {
  it("uses the frozen extraction endpoints with CSRF and strict parsing", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockImplementation(() =>
      Promise.resolve(
        json({
          chapters: [frozenChapter(chapterA, 1)],
          total_characters: 20,
          max_chapters: 10,
          max_total_characters: 30000,
          open_threads: 0,
          threads_omitted: 0,
          problem: null,
        }),
      ),
    );
    await foreshadowExtractionClient.preview(projectId, [chapterA]);
    fetcher.mockImplementation(() => Promise.resolve(json(raw(), 201)));
    await expect(
      foreshadowExtractionClient.prepare(
        projectId,
        [chapterA, chapterB],
        "default-local",
        "人物",
      ),
    ).resolves.toEqual(ready);
    fetcher.mockImplementation(() =>
      Promise.resolve(json(allowedAnalysisEstimate())),
    );
    await foreshadowExtractionClient.estimate(projectId, ready.id);
    fetcher.mockImplementation(() =>
      Promise.resolve(json(raw({ status: "completed", cards, checks }))),
    );
    await foreshadowExtractionClient.send(projectId, ready, false);
    await foreshadowExtractionClient.adopt(projectId, ready.id, [1]);
    const calls = fetcher.mock.calls.map(([url, options]) => [
      options?.method,
      url,
      options?.body ?? null,
    ]);
    const root = `/api/v1/projects/${projectId}/foreshadow-proposals`;
    expect(calls).toEqual([
      ["POST", `${root}/preview`, JSON.stringify({ chapter_ids: [chapterA] })],
      [
        "POST",
        root,
        JSON.stringify({
          chapter_ids: [chapterA, chapterB],
          profile_id: "default-local",
          author_request: "人物",
        }),
      ],
      ["GET", `${root}/extraction-1/estimate`, null],
      [
        "POST",
        `${root}/extraction-1/send`,
        JSON.stringify({ expected_version: 1, cloud_consent: false }),
      ],
      [
        "POST",
        `${root}/extraction-1/adopt`,
        JSON.stringify({ card_indexes: [1] }),
      ],
    ]);
    const headers = new Headers(fetcher.mock.calls[0][1]?.headers);
    expect(headers.get("X-CSRF-Token")).toBe("fake-csrf-proof".repeat(3));
  });

  it("rejects unknown cards, cards without checks and maps a stale adoption", async () => {
    expect(() =>
      parseExtraction(
        raw({
          cards: [{ kind: "rewrite", chapter_id: chapterA, quote: "x" }],
          checks: [{ valid: true, problem: null }],
        }),
        projectId,
      ),
    ).toThrow(/无法安全读取/u);
    expect(() => parseExtraction(raw({ cards }), projectId)).toThrow();
    expect(() => parseExtraction(raw(), "prj_other")).toThrow();
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockResolvedValue(
      json(
        {
          error: {
            code: "FORESHADOW_EXTRACTION_STALE",
            message: "changed",
            details: {},
            retryable: false,
            suggested_action: null,
          },
          request_id: "req",
        },
        409,
      ),
    );
    await expect(
      foreshadowExtractionClient.adopt(projectId, ready.id, [0]),
    ).rejects.toMatchObject({ code: "FORESHADOW_EXTRACTION_STALE" });
  });
});

describe("foreshadow advance cards", () => {
  it("parses and shows an advance card and its problem", () => {
    const advance = {
      kind: "advance",
      thread_id: "thread-1",
      chapter_id: chapterB,
      quote: "露出一道刀疤",
      reason: "",
    };
    const parsed = parseExtraction(
      raw({
        status: "completed",
        cards: [advance, advance],
        checks: [
          { valid: true, problem: null },
          { valid: false, problem: "duplicate_advance" },
        ],
        adoptions: [
          {
            index: 0,
            action: "advanced",
            thread_id: "thread-1",
            thread_version: 2,
            adopted_at: "t",
          },
        ],
      }),
      projectId,
    );
    expect(parsed.cards[0]).toEqual(advance);
    expect(parsed.adoptions[0].action).toBe("advanced");
    render(
      <ForeshadowExtractionPanel
        projectId={projectId}
        plan={plan}
        client={fakeClient({
          list: vi
            .fn()
            .mockResolvedValue([
              { id: parsed.id, status: "completed", chapter_ids: [chapterB] },
            ]),
          get: vi.fn().mockResolvedValue(parsed),
        })}
        onAdopted={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    return screen
      .findAllByText(/推进伏笔「少主身世」于第1卷第2章/u)
      .then((items) => {
        expect(items).toHaveLength(2);
        expect(
          screen.getByText(/重复推进同一伏笔的同一段原文/u),
        ).toBeInTheDocument();
        expect(screen.getByLabelText("选择伏笔建议卡 2")).toBeDisabled();
      });
  });
});

describe("foreshadow extraction panel", () => {
  function renderPanel(
    client: ForeshadowExtractionClient,
    onAdopted = vi.fn(),
  ) {
    render(
      <ForeshadowExtractionPanel
        projectId={projectId}
        plan={plan}
        client={client}
        onAdopted={onAdopted}
        onClose={vi.fn()}
      />,
    );
    return onAdopted;
  }

  it("previews the range, sends once and adopts only selected valid cards", async () => {
    const client = fakeClient();
    client.adopt.mockResolvedValue(
      parseExtraction(
        raw({
          version: 4,
          status: "completed",
          cards,
          checks,
          adoptions: [
            {
              index: 1,
              action: "paid_off",
              thread_id: "thread-1",
              thread_version: 2,
              adopted_at: "t",
            },
          ],
        }),
        projectId,
      ),
    );
    const onAdopted = renderPanel(client);
    fireEvent.click(await screen.findByLabelText(/第1卷第1章/u));
    fireEvent.click(screen.getByLabelText(/第1卷第2章/u));
    expect(
      screen.queryByRole("button", { name: /准备提取/u }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /预览所选范围/u }));
    expect(await screen.findByText(/合计 42 \/ 30000 字/u)).toBeInTheDocument();
    expect(
      screen.getByText(/第1卷第2章「第二章」：30 字/u),
    ).toBeInTheDocument();
    expect(client.preview).toHaveBeenCalledWith(projectId, [
      chapterA,
      chapterB,
    ]);
    expect(client.estimate).not.toHaveBeenCalled();
    const prepare = screen.getByRole("button", { name: /准备提取/u });
    await waitFor(() => expect(prepare).not.toBeDisabled());
    fireEvent.click(prepare);
    await screen.findByText(/查看将发送的完整内容/u);
    expect(client.prepare).toHaveBeenCalledWith(
      projectId,
      [chapterA, chapterB],
      "default-local",
      "",
    );
    const send = await screen.findByRole("button", { name: /发送一次/u });
    await waitFor(() => expect(send).not.toBeDisabled());
    expect(client.estimate).toHaveBeenCalledWith(projectId, ready.id);
    fireEvent.click(send);
    await screen.findByText(/模型判断：一新一兑/u);
    expect(client.send).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("选择伏笔建议卡 3")).toBeDisabled();
    expect(screen.getByText(/引文在冻结的原文中找不到/u)).toBeInTheDocument();
    expect(screen.getByText(/兑现伏笔「少主身世」/u)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("选择伏笔建议卡 2"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选（1）" }));
    await waitFor(() => expect(onAdopted).toHaveBeenCalledTimes(1));
    expect(client.adopt).toHaveBeenCalledWith(projectId, ready.id, [1]);
    expect(screen.getByLabelText("选择伏笔建议卡 2")).toBeDisabled();
    expect(screen.getByText(/已采用/u)).toBeInTheDocument();
  });

  it("refuses to prepare an over-limit range", async () => {
    const client = fakeClient({
      preview: vi.fn().mockResolvedValue({
        ...rangePreview,
        total_characters: 40000,
        problem: "too_many_characters",
      }),
    });
    renderPanel(client);
    fireEvent.click(await screen.findByLabelText(/第1卷第1章/u));
    fireEvent.click(screen.getByRole("button", { name: /预览所选范围/u }));
    expect(await screen.findByRole("alert")).toHaveTextContent("超过字数上限");
    expect(screen.getByRole("button", { name: /准备提取/u })).toBeDisabled();
    expect(client.prepare).not.toHaveBeenCalled();
  });

  it("blocks sending under a strict budget refusal", async () => {
    const client = fakeClient({
      list: vi
        .fn()
        .mockResolvedValue([
          { id: ready.id, status: "ready", chapter_ids: [chapterA] },
        ]),
      get: vi.fn().mockResolvedValue(ready),
      estimate: vi.fn().mockResolvedValue(
        allowedAnalysisEstimate({
          decision: "refused",
          budget_mode: "strict",
          reasons: ["TASK_LIMIT_EXCEEDED"],
        }),
      ),
    });
    renderPanel(client);
    expect(await screen.findByText(/按严格预算不会发送/u)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /发送一次/u })).toBeDisabled();
    expect(client.send).not.toHaveBeenCalled();
  });

  it("shows retained evidence for an invalid reply without retrying", async () => {
    const failed = parseExtraction(
      raw({
        version: 3,
        status: "failed",
        error: "ForeshadowOutputInvalid",
        evidence: "好的```json{}```",
      }),
      projectId,
    );
    const client = fakeClient({
      list: vi
        .fn()
        .mockResolvedValue([
          { id: ready.id, status: "ready", chapter_ids: [chapterA] },
        ]),
      get: vi.fn().mockResolvedValue(ready),
      send: vi.fn().mockResolvedValue(failed),
    });
    renderPanel(client);
    const send = await screen.findByRole("button", { name: /发送一次/u });
    await waitFor(() => expect(send).not.toBeDisabled());
    fireEvent.click(send);
    expect(await screen.findByText(/不是有效的建议格式/u)).toBeInTheDocument();
    expect(screen.getByText("好的```json{}```")).toBeInTheDocument();
    expect(client.send).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /发送一次/u })).toBeNull();
  });

  it("asks to prepare again when the chapter text changed before adoption", async () => {
    const client = fakeClient({
      list: vi
        .fn()
        .mockResolvedValue([
          { id: completed.id, status: "completed", chapter_ids: [chapterA] },
        ]),
    });
    client.adopt.mockRejectedValue(
      new ForeshadowExtractionError(
        "章节正文已被修改，请重新准备。",
        "FORESHADOW_EXTRACTION_STALE",
      ),
    );
    const onAdopted = renderPanel(client);
    fireEvent.click(await screen.findByLabelText("选择伏笔建议卡 1"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选（1）" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请重新准备");
    expect(onAdopted).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "重新准备提取" }),
    ).toBeInTheDocument();
  });
});

describe("structure page thread area", () => {
  it("opens batch extraction only on request and refreshes after adoption", async () => {
    const arcPlan = vi.fn().mockResolvedValue(plan);
    const control = {
      arcPlan,
      timeline: vi.fn().mockResolvedValue({
        project_id: projectId,
        threads: [],
        events: [],
        states: [],
        warnings: [],
      }),
    } as unknown as StoryControlClient;
    const extractions = fakeClient({
      list: vi
        .fn()
        .mockResolvedValue([
          { id: completed.id, status: "completed", chapter_ids: [chapterA] },
        ]),
    });
    extractions.adopt.mockResolvedValue(completed);
    render(
      <StoryControlPanel
        projectId={projectId}
        client={control}
        foreshadowClient={extractions}
      />,
    );
    const open = await screen.findByRole("button", {
      name: "批量提取伏笔建议",
    });
    expect(extractions.models).not.toHaveBeenCalled();
    fireEvent.click(open);
    fireEvent.click(await screen.findByLabelText("选择伏笔建议卡 1"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选（1）" }));
    expect(
      await screen.findByText("已采用所选伏笔建议卡，伏笔已更新。"),
    ).toBeInTheDocument();
    await waitFor(() => expect(arcPlan).toHaveBeenCalledTimes(2));
    expect(extractions.prepare).not.toHaveBeenCalled();
    expect(extractions.send).not.toHaveBeenCalled();
  });
});

describe("foreshadow card edits and undo", () => {
  const repairedCard = { ...cards[2], quote: "替少主挡下" };
  const repaired = parseExtraction(
    raw({
      version: 4,
      status: "completed",
      cards,
      checks,
      effective_checks: [
        { valid: true, problem: null },
        { valid: true, problem: null },
        { valid: true, problem: null },
      ],
      edits: [{ index: 2, card: repairedCard, edited_at: "t" }],
    }),
    projectId,
  );

  it("parses effective checks and sends edit/undo with the version", async () => {
    expect(repaired.checks[2].valid).toBe(false);
    expect(repaired.effective_checks[2].valid).toBe(true);
    expect(() =>
      parseExtraction(raw({ cards, checks, effective_checks: [] }), projectId),
    ).toThrow(/无法安全读取/u);
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockImplementation(() =>
      Promise.resolve(
        json(raw({ version: 4, status: "completed", cards, checks })),
      ),
    );
    await foreshadowExtractionClient.editCard(
      projectId,
      completed,
      2,
      completed.cards[2],
    );
    await foreshadowExtractionClient.undo(projectId, completed, 0);
    const root = `/api/v1/projects/${projectId}/foreshadow-proposals/extraction-1`;
    expect(
      fetcher.mock.calls.map(([url, options]) => [
        options?.method,
        url,
        options?.body,
      ]),
    ).toEqual([
      [
        "PUT",
        `${root}/cards/2`,
        JSON.stringify({ expected_version: 3, card: completed.cards[2] }),
      ],
      [
        "POST",
        `${root}/undo`,
        JSON.stringify({ expected_version: 3, card_index: 0 }),
      ],
    ]);
  });

  it("repairs an invalid card by editing its quote, then it can be selected", async () => {
    const client = fakeClient({
      list: vi
        .fn()
        .mockResolvedValue([
          { id: "extraction-1", status: "completed", chapter_ids: [] },
        ]),
    });
    client.editCard.mockResolvedValue(repaired);
    render(
      <ForeshadowExtractionPanel
        projectId={projectId}
        plan={plan}
        client={client}
        onAdopted={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(await screen.findByLabelText("选择伏笔建议卡 3")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "修改伏笔建议卡 3" }));
    fireEvent.change(
      screen.getByLabelText("引文（必须逐字出自该章冻结原文，最多 300 字）"),
      { target: { value: "替少主挡下" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "核对并保存修改" }));
    await screen.findByText("对照模型原始建议");
    expect(client.editCard).toHaveBeenCalledWith(projectId, completed, 2, {
      ...completed.cards[2],
      quote: "替少主挡下",
    });
    expect(screen.getByLabelText("选择伏笔建议卡 3")).not.toBeDisabled();
    expect(screen.getByText(/引文在冻结的原文中找不到/u)).toBeInTheDocument();
    expect(client.adopt).not.toHaveBeenCalled();
  });

  it("undoes an adopted card and refreshes threads", async () => {
    const adoptedOne = parseExtraction(
      raw({
        version: 5,
        status: "completed",
        cards,
        checks,
        adoptions: [
          {
            index: 0,
            action: "created",
            thread_id: "extraction-1-0",
            thread_version: 1,
            adopted_at: "t",
            edited: false,
          },
        ],
      }),
      projectId,
    );
    const client = fakeClient({
      list: vi
        .fn()
        .mockResolvedValue([
          { id: "extraction-1", status: "completed", chapter_ids: [] },
        ]),
      get: vi.fn().mockResolvedValue(adoptedOne),
    });
    client.undo.mockResolvedValue(completed);
    const onUndone = vi.fn();
    render(
      <ForeshadowExtractionPanel
        projectId={projectId}
        plan={plan}
        client={client}
        onAdopted={vi.fn()}
        onUndone={onUndone}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "撤销采用伏笔建议卡 1" }),
    );
    await waitFor(() => expect(onUndone).toHaveBeenCalledTimes(1));
    expect(client.undo).toHaveBeenCalledWith(projectId, adoptedOne, 0);
    expect(screen.getByLabelText("选择伏笔建议卡 1")).not.toBeDisabled();
  });
});
