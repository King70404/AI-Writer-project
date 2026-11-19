import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { securitySession } from "../../frontend/src/api/security-session";
import type {
  ArcPlan,
  StoryControlClient,
} from "../../frontend/src/features/story-control/api/storyControl";
import {
  TimelineExtractionError,
  parseTimelineExtraction,
  parseTimelineRangePreview,
  timelineExtractionClient,
  type TimelineExtractionClient,
} from "../../frontend/src/features/story-control/api/timelineExtraction";
import { StoryControlPanel } from "../../frontend/src/features/story-control/components/StoryControlPanel";
import { TimelineExtractionPanel } from "../../frontend/src/features/story-control/components/TimelineExtractionPanel";
import { OPERATION_LABELS } from "../../frontend/src/features/usage/api/usage";
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
  characters: [{ character_id: "chr_a", name: "船夫" }],
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
    characters: [{ character_id: "chr_a", name: "船夫" }],
    events: [
      {
        id: "event-1",
        version: 1,
        title: "离开渡口",
        description: "",
        story_time: "",
        chapter_id: null,
        character_ids: [],
      },
    ],
    events_omitted: 0,
    states: [
      {
        id: "state-1",
        version: 1,
        character_id: "chr_a",
        attribute: "injury",
        label: "左臂伤势",
        value: "完好",
        start_event_id: "event-1",
      },
    ],
    states_omitted: 0,
    summary: null,
    cards: [],
    checks: [],
    error: null,
    evidence: null,
    evidence_truncated: false,
    adoptions: [],
    created_at: "t",
    updated_at: "t",
    request_preview: "[system]\n只输出 JSON\n\n[user]\n{}",
    ...overrides,
  };
}
const cards = [
  {
    kind: "event",
    title: "渡口遇袭",
    description: "船夫中刀",
    story_time: "当夜",
    chapter_id: chapterA,
    character_ids: ["chr_a"],
    after_event_ids: ["event-1"],
    quote: "船夫左臂中了一刀",
    reason: "",
  },
  {
    kind: "state",
    character_id: "chr_a",
    attribute: "injury",
    label: "左臂伤势",
    value: "刀伤未愈",
    chapter_id: chapterA,
    quote: "血染红了旧布",
    start_event_id: null,
    start_event_card: 0,
    ends_state_id: "state-1",
    reason: "受伤",
  },
  {
    kind: "event",
    title: "少主认人",
    description: "",
    story_time: "",
    chapter_id: chapterB,
    character_ids: [],
    after_event_ids: [],
    quote: "原文没有的句子",
    reason: "",
  },
];
const checks = [
  { valid: true, problem: null },
  { valid: true, problem: null },
  { valid: false, problem: "quote_not_found" },
];
const ready = parseTimelineExtraction(raw(), projectId);
const completed = parseTimelineExtraction(
  raw({ version: 3, status: "completed", summary: "一伤一愈", cards, checks }),
  projectId,
);
const rangePreview = parseTimelineRangePreview({
  chapters: [frozenChapter(chapterA, 1, 12), frozenChapter(chapterB, 2, 30)],
  total_characters: 42,
  max_chapters: 10,
  max_total_characters: 30000,
  characters: 1,
  events: 1,
  events_omitted: 0,
  open_states: 1,
  states_omitted: 0,
  problem: null,
});

function fakeClient(overrides: Partial<TimelineExtractionClient> = {}) {
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
    ...overrides,
  } as unknown as TimelineExtractionClient & {
    models: ReturnType<typeof vi.fn>;
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

describe("timeline extraction API", () => {
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
          characters: 1,
          events: 0,
          events_omitted: 0,
          open_states: 0,
          states_omitted: 0,
          problem: null,
        }),
      ),
    );
    await timelineExtractionClient.preview(projectId, [chapterA]);
    fetcher.mockImplementation(() => Promise.resolve(json(raw(), 201)));
    await expect(
      timelineExtractionClient.prepare(
        projectId,
        [chapterA, chapterB],
        "default-local",
        "伤势",
      ),
    ).resolves.toEqual(ready);
    fetcher.mockImplementation(() =>
      Promise.resolve(json(allowedAnalysisEstimate())),
    );
    await timelineExtractionClient.estimate(projectId, ready.id);
    fetcher.mockImplementation(() =>
      Promise.resolve(json(raw({ status: "completed", cards, checks }))),
    );
    await timelineExtractionClient.send(projectId, ready, false);
    await timelineExtractionClient.adopt(projectId, ready.id, [0, 1]);
    const calls = fetcher.mock.calls.map(([url, options]) => [
      options?.method,
      url,
      options?.body ?? null,
    ]);
    const root = `/api/v1/projects/${projectId}/timeline-proposals`;
    expect(calls).toEqual([
      ["POST", `${root}/preview`, JSON.stringify({ chapter_ids: [chapterA] })],
      [
        "POST",
        root,
        JSON.stringify({
          chapter_ids: [chapterA, chapterB],
          profile_id: "default-local",
          author_request: "伤势",
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
        JSON.stringify({ card_indexes: [0, 1] }),
      ],
    ]);
    const headers = new Headers(fetcher.mock.calls[0][1]?.headers);
    expect(headers.get("X-CSRF-Token")).toBe("fake-csrf-proof".repeat(3));
    expect(OPERATION_LABELS.timeline_extraction).toBe("批量提取事件与人物状态");
  });

  it("rejects unknown or ambiguous cards and maps a needs-event refusal", async () => {
    expect(() =>
      parseTimelineExtraction(
        raw({
          cards: [{ kind: "rewrite", chapter_id: chapterA, quote: "x" }],
          checks: [{ valid: true, problem: null }],
        }),
        projectId,
      ),
    ).toThrow(/无法安全读取/u);
    const both = { ...cards[1], start_event_id: "event-1" };
    expect(() =>
      parseTimelineExtraction(
        raw({ cards: [both], checks: [checks[0]] }),
        projectId,
      ),
    ).toThrow(/无法安全读取/u);
    expect(() => parseTimelineExtraction(raw({ cards }), projectId)).toThrow();
    expect(() => parseTimelineExtraction(raw(), "prj_other")).toThrow();
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockResolvedValue(
      json(
        {
          error: {
            code: "TIMELINE_CARD_NEEDS_EVENT",
            message: "needs",
            details: {},
            retryable: false,
            suggested_action: null,
          },
          request_id: "req",
        },
        422,
      ),
    );
    const refused = await timelineExtractionClient
      .adopt(projectId, ready.id, [1])
      .catch((reason: unknown) => reason);
    expect(refused).toBeInstanceOf(TimelineExtractionError);
    expect((refused as TimelineExtractionError).code).toBe(
      "TIMELINE_CARD_NEEDS_EVENT",
    );
    expect((refused as TimelineExtractionError).message).toMatch(
      /同时勾选那张事件卡/u,
    );
  });
});

describe("timeline extraction panel", () => {
  function renderPanel(client: TimelineExtractionClient, onAdopted = vi.fn()) {
    render(
      <TimelineExtractionPanel
        projectId={projectId}
        plan={plan}
        client={client}
        onAdopted={onAdopted}
        onClose={vi.fn()}
      />,
    );
    return onAdopted;
  }

  it("previews, sends once and adopts a state together with its event card", async () => {
    const client = fakeClient();
    client.adopt.mockResolvedValue(
      parseTimelineExtraction(
        raw({
          version: 4,
          status: "completed",
          cards,
          checks,
          adoptions: [
            {
              index: 0,
              action: "event_created",
              target_id: "extraction-1-0",
              ended_state_id: null,
              adopted_at: "t",
            },
            {
              index: 1,
              action: "state_created",
              target_id: "extraction-1-1",
              ended_state_id: "state-1",
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
    fireEvent.click(screen.getByRole("button", { name: /预览所选范围/u }));
    expect(await screen.findByText(/合计 42 \/ 30000 字/u)).toBeInTheDocument();
    expect(screen.getByText(/1 个已有事件/u)).toBeInTheDocument();
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
    fireEvent.click(send);
    await screen.findByText(/模型判断：一伤一愈/u);
    expect(client.send).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("选择事件或人物状态卡 3")).toBeDisabled();
    expect(screen.getByText(/引文在冻结的原文中找不到/u)).toBeInTheDocument();
    expect(
      screen.getByText(/事件「渡口遇袭」发生于第1卷第1章/u),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /从建议事件卡 1「渡口遇袭」开始.*结束原状态「左臂伤势：完好」/u,
      ),
    ).toBeInTheDocument();
    // Selecting the state also selects the event card it starts at.
    fireEvent.click(screen.getByLabelText("选择事件或人物状态卡 2"));
    expect(screen.getByLabelText("选择事件或人物状态卡 1")).toBeChecked();
    // Unselecting the event also unselects the state that depends on it.
    fireEvent.click(screen.getByLabelText("选择事件或人物状态卡 1"));
    expect(screen.getByLabelText("选择事件或人物状态卡 2")).not.toBeChecked();
    fireEvent.click(screen.getByLabelText("选择事件或人物状态卡 2"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选（2）" }));
    await waitFor(() => expect(onAdopted).toHaveBeenCalledTimes(1));
    expect(client.adopt).toHaveBeenCalledWith(projectId, ready.id, [0, 1]);
    expect(screen.getByLabelText("选择事件或人物状态卡 2")).toBeDisabled();
    expect(screen.getAllByText(/已采用/u)).toHaveLength(2);
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
    const failed = parseTimelineExtraction(
      raw({
        version: 3,
        status: "failed",
        error: "TimelineOutputInvalid",
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
    expect(
      await screen.findByText(/不是有效的证据卡格式/u),
    ).toBeInTheDocument();
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
      new TimelineExtractionError(
        "章节正文已被修改，请重新准备。",
        "TIMELINE_EXTRACTION_STALE",
      ),
    );
    const onAdopted = renderPanel(client);
    fireEvent.click(await screen.findByLabelText("选择事件或人物状态卡 1"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选（1）" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请重新准备");
    expect(onAdopted).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "重新准备提取" }),
    ).toBeInTheDocument();
  });
});

describe("structure page timeline area", () => {
  it("opens the extraction only on request and refreshes after adoption", async () => {
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
        timelineClient={extractions}
      />,
    );
    const open = await screen.findByRole("button", {
      name: "批量提取事件与人物状态",
    });
    expect(extractions.models).not.toHaveBeenCalled();
    fireEvent.click(open);
    fireEvent.click(await screen.findByLabelText("选择事件或人物状态卡 1"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选（1）" }));
    expect(
      await screen.findByText("已采用所选事件与人物状态卡，时间线已更新。"),
    ).toBeInTheDocument();
    await waitFor(() => expect(arcPlan).toHaveBeenCalledTimes(2));
    expect(extractions.prepare).not.toHaveBeenCalled();
    expect(extractions.send).not.toHaveBeenCalled();
  });
});
