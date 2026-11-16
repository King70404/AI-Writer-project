import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../frontend/src/api/errors";
import { securitySession } from "../../frontend/src/api/security-session";
import type {
  AIWorkflowClient,
  ModelProfile,
  WorkflowRun,
} from "../../frontend/src/features/novel-structure/api/ai-workflow";
import { AIWorkflowAssistant } from "../../frontend/src/features/novel-structure/components/AIWorkflowAssistant";
import { useChapterWriting } from "../../frontend/src/features/novel-structure/hooks/useChapterWriting";
import {
  StoryControlError,
  parseArcPlan,
  parseGuide,
  parsePolicy,
  parsePreview,
  parseTimeline,
  storyControlClient,
  storyControlError,
  type ArcPlan,
  type ChapterGuide,
  type FactSearchPage,
  type Goal,
  type RecallPolicyState,
  type RecallPreview,
  type StoryControlClient,
  type Thread,
  type Timeline,
} from "../../frontend/src/features/story-control/api/storyControl";
import {
  ChapterGuideCard,
  RecallControl,
} from "../../frontend/src/features/story-control/components/ChapterStoryControl";
import {
  StoryControlPanel,
  StoryControlSection,
} from "../../frontend/src/features/story-control/components/StoryControlPanel";
import { written, writingClient } from "./chapter-writing-support";

const projectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const chapterA = "chp_a";
const chapterB = "chp_b";
const volumeA = "vol_a";
const volumeB = "vol_b";

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

const stored = {
  version: 1,
  revision_id: "rev-1",
  updated_at: "2026-10-24T00:00:00+00:00",
};
const goal: Goal = {
  ...stored,
  id: "goal-book",
  scope: "book",
  volume_id: null,
  parent_goal_ids: [],
  title: "夺回渡口",
  conflict: "渡口被夺",
  desire: "",
  obstacle: "夜禁",
  turn: "",
  outcome: "",
  opening_state: "",
  target_characters: null,
  status: "active",
  links: [
    {
      chapter_id: chapterA,
      status: "reflected",
      chapter_revision_id: "chv_old",
      quote: "雨夜",
      note: "第一次靠近",
    },
  ],
};
const thread: Thread = {
  ...stored,
  id: "thread-1",
  title: "船夫旧伤",
  content: "左臂",
  character_ids: ["chr_boat"],
  planned_setup_chapter_id: chapterA,
  planned_payoff_chapter_id: chapterB,
  planned_payoff_volume_id: null,
  priority: "high",
  status: "planted",
  note: "",
  anchors: [
    {
      role: "setup",
      chapter_id: chapterA,
      chapter_revision_id: "chv_a",
      quote: "雨夜",
    },
  ],
};
const volumeThread: Thread = {
  ...thread,
  id: "thread-2",
  title: "远方来信",
  status: "planned",
  priority: "low",
  character_ids: [],
  planned_setup_chapter_id: null,
  planned_payoff_chapter_id: null,
  planned_payoff_volume_id: volumeB,
  anchors: [],
};
const plan: ArcPlan = {
  project_id: projectId,
  goals: [
    {
      goal,
      links: [
        {
          ...goal.links[0],
          chapter_title: "第一章",
          problem: "evidence_stale",
        },
      ],
      child_goal_ids: [],
      reflected: 1,
      open_links: 0,
    },
    {
      goal: {
        ...goal,
        id: "goal-vol",
        scope: "volume",
        volume_id: volumeA,
        title: "卷一潜入",
        status: "archived",
        links: [
          {
            chapter_id: "chp_gone",
            status: "planned",
            chapter_revision_id: null,
            quote: null,
            note: "",
          },
        ],
      },
      links: [
        {
          chapter_id: "chp_gone",
          status: "planned",
          chapter_revision_id: null,
          quote: null,
          note: "",
          chapter_title: null,
          problem: "missing",
        },
      ],
      child_goal_ids: [],
      reflected: 0,
      open_links: 1,
    },
  ],
  volumes: [
    { volume_id: volumeA, title: "卷一", position: 1 },
    { volume_id: volumeB, title: "卷二", position: 2 },
  ],
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
  characters: [{ character_id: "chr_boat", name: "船夫" }],
};
const fireEvent1 = {
  ...stored,
  id: "event-past",
  title: "十年前的大火",
  description: "",
  story_time: "十年前",
  chapter_id: chapterB,
  character_ids: [],
  after_event_ids: [],
  before_event_ids: ["event-now"],
  archived: false,
};
const timeline: Timeline = {
  project_id: projectId,
  threads: [
    {
      thread,
      anchors: [
        {
          anchor: thread.anchors[0],
          chapter_title: "第一章",
          stale: true,
        },
      ],
      evidence_stale: true,
      due: true,
      due_reason: "预计兑现章已有正文，请兑现、延期、改计划或放弃",
    },
    {
      thread: volumeThread,
      anchors: [],
      evidence_stale: false,
      due: false,
      due_reason: null,
    },
  ],
  events: [
    {
      event: fireEvent1,
      story_order: 1,
      narrative_position: [1, 2],
      chapter_title: "第二章",
    },
    {
      event: {
        ...fireEvent1,
        id: "event-now",
        title: "渡口失火",
        story_time: "",
        chapter_id: null,
        before_event_ids: [],
      },
      story_order: 2,
      narrative_position: null,
      chapter_title: null,
    },
  ],
  states: [
    {
      state: {
        ...stored,
        id: "state-1",
        character_id: "chr_boat",
        attribute: "injury",
        label: "左臂",
        value: "烧伤",
        start_event_id: "event-past",
        end_event_id: null,
        fact_ids: ["fact-1"],
        archived: false,
      },
      invalid_fact_ids: ["fact-1"],
    },
    {
      state: {
        ...stored,
        id: "state-2",
        character_id: "chr_gone",
        attribute: "other",
        label: "身份",
        value: "未知",
        start_event_id: "event-missing",
        end_event_id: "event-missing",
        fact_ids: [],
        archived: false,
      },
      invalid_fact_ids: [],
    },
  ],
  warnings: [
    {
      kind: "state_overlap",
      state_ids: ["state-1", "state-2"],
      message: "「左臂」的两个不同状态区间重叠，请核对",
    },
  ],
};
const guide: ChapterGuide = {
  chapter_id: chapterA,
  project_id: projectId,
  goals: [plan.goals[0]],
  setup_threads: [timeline.threads[1]],
  payoff_threads: [timeline.threads[0]],
  due_threads: [timeline.threads[0]],
};
const policy: RecallPolicyState = {
  chapter_id: chapterB,
  version: 1,
  pinned_fact_ids: ["fact-1"],
  excluded_fact_ids: [],
  updated_at: "2026-10-24T00:00:00+00:00",
};
const preview: RecallPreview = {
  chapter_id: chapterB,
  policy_version: 1,
  selected: [
    {
      id: "fact-1",
      revision_id: "fr-1",
      chapter_id: chapterA,
      title: "船夫旧伤",
      reason: "pinned",
      characters: 120,
    },
    {
      id: "fact-2",
      revision_id: "fr-2",
      chapter_id: chapterA,
      title: "渡口天气",
      reason: "related",
      characters: 80,
    },
  ],
  omitted: [{ id: "fact-3", title: "旧事", reason: "budget" }],
  omitted_total: 1,
  excluded_total: 0,
  used_characters: 200,
  character_limit: 10_000,
  item_limit: 24,
  blocked: false,
};
const facts: FactSearchPage = {
  items: [
    {
      id: "fact-1",
      revision_id: "fr-1",
      chapter_id: chapterA,
      chapter_title: "第一章",
      title: "船夫旧伤",
      text: "船夫左臂有旧伤",
      quote: "左臂",
      status: "confirmed",
      stale: false,
      recallable_here: true,
    },
    {
      id: "fact-4",
      revision_id: "fr-4",
      chapter_id: chapterB,
      chapter_title: null,
      title: "后文事实",
      text: "不能召回",
      quote: "后",
      status: "confirmed",
      stale: true,
      recallable_here: false,
    },
  ],
  total: 2,
  offset: 0,
  limit: 20,
};

function fakeClient(
  overrides: Partial<StoryControlClient> = {},
): StoryControlClient {
  return {
    arcPlan: vi.fn().mockResolvedValue(plan),
    saveGoal: vi.fn().mockResolvedValue(goal),
    timeline: vi.fn().mockResolvedValue(timeline),
    saveThread: vi.fn().mockResolvedValue(thread),
    saveEvent: vi.fn().mockResolvedValue(fireEvent1),
    saveState: vi.fn().mockResolvedValue(timeline.states[0].state),
    guide: vi.fn().mockResolvedValue(guide),
    searchFacts: vi.fn().mockResolvedValue(facts),
    recallPolicy: vi.fn().mockResolvedValue(policy),
    saveRecallPolicy: vi
      .fn()
      .mockResolvedValue({ ...policy, version: 2, pinned_fact_ids: [] }),
    recallPreview: vi.fn().mockResolvedValue(preview),
    ...overrides,
  };
}

function apiError(status: number, code: string): ApiError {
  return new ApiError({
    status,
    code,
    message: "server",
    details: {},
    retryable: false,
    suggestedAction: null,
    requestId: null,
  });
}

function json(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

describe("story control API", () => {
  it("calls each endpoint with the right method, path and CSRF proof", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockImplementation(() => Promise.resolve(json(plan)));
    await expect(storyControlClient.arcPlan(projectId)).resolves.toEqual(plan);
    fetcher.mockImplementation(() => Promise.resolve(json(goal)));
    await storyControlClient.saveGoal(projectId, null, goal, 0);
    await storyControlClient.saveGoal(projectId, goal.id, goal, 1);
    fetcher.mockImplementation(() => Promise.resolve(json(timeline)));
    await expect(storyControlClient.timeline(projectId)).resolves.toEqual(
      timeline,
    );
    await storyControlClient.timeline(projectId, {
      status: "planted",
      character_id: "chr_boat",
    });
    fetcher.mockImplementation(() => Promise.resolve(json(thread)));
    await storyControlClient.saveThread(projectId, null, thread, 0);
    fetcher.mockImplementation(() => Promise.resolve(json(fireEvent1)));
    await storyControlClient.saveEvent(projectId, "event-past", fireEvent1, 1);
    fetcher.mockImplementation(() =>
      Promise.resolve(json(timeline.states[0].state)),
    );
    await storyControlClient.saveState(
      projectId,
      null,
      timeline.states[0].state,
      0,
    );
    fetcher.mockImplementation(() => Promise.resolve(json(guide)));
    await expect(storyControlClient.guide(chapterA)).resolves.toEqual(guide);
    fetcher.mockImplementation(() => Promise.resolve(json(facts)));
    await expect(
      storyControlClient.searchFacts(projectId, {
        q: "船夫",
        status: "confirmed",
        forChapter: chapterB,
      }),
    ).resolves.toEqual(facts);
    await storyControlClient.searchFacts(projectId, { offset: 20, limit: 5 });
    fetcher.mockImplementation(() => Promise.resolve(json(policy)));
    await expect(storyControlClient.recallPolicy(chapterB)).resolves.toEqual(
      policy,
    );
    await storyControlClient.saveRecallPolicy(chapterB, ["fact-1"], [], 1);
    fetcher.mockImplementation(() => Promise.resolve(json(preview)));
    await expect(
      storyControlClient.recallPreview(chapterB, ["fact-1"], ["fact-2"]),
    ).resolves.toEqual(preview);
    const calls = fetcher.mock.calls.map(([url, options]) => [
      options?.method,
      url,
    ]);
    expect(calls).toEqual([
      ["GET", `/api/v1/projects/${projectId}/arc-plans`],
      ["POST", `/api/v1/projects/${projectId}/arc-plans`],
      ["PUT", `/api/v1/projects/${projectId}/arc-plans/goal-book`],
      ["GET", `/api/v1/projects/${projectId}/timeline`],
      [
        "GET",
        `/api/v1/projects/${projectId}/timeline?status=planted&character_id=chr_boat`,
      ],
      ["POST", `/api/v1/projects/${projectId}/plot-threads`],
      ["PUT", `/api/v1/projects/${projectId}/story-events/event-past`],
      ["POST", `/api/v1/projects/${projectId}/state-intervals`],
      ["GET", `/api/v1/chapters/${chapterA}/story-guide`],
      [
        "GET",
        `/api/v1/projects/${projectId}/facts/search?offset=0&limit=20&q=%E8%88%B9%E5%A4%AB&status=confirmed&for_chapter=${chapterB}`,
      ],
      ["GET", `/api/v1/projects/${projectId}/facts/search?offset=20&limit=5`],
      ["GET", `/api/v1/chapters/${chapterB}/recall-policy`],
      ["PUT", `/api/v1/chapters/${chapterB}/recall-policy`],
      ["POST", `/api/v1/chapters/${chapterB}/recall-preview`],
    ]);
    const put = fetcher.mock.calls[12][1];
    expect(new Headers(put?.headers).get("X-CSRF-Token")).toBe(
      "fake-csrf-proof".repeat(3),
    );
    expect(JSON.parse(put?.body as string)).toEqual({
      pinned_fact_ids: ["fact-1"],
      excluded_fact_ids: [],
      expected_version: 1,
    });
  });

  it("rejects unsafe or mismatched responses", () => {
    expect(() => parseArcPlan(plan, "prj_other")).toThrow(StoryControlError);
    expect(() =>
      parseTimeline(
        { ...timeline, threads: [{ thread: { status: "x" } }] },
        projectId,
      ),
    ).toThrow(StoryControlError);
    expect(() => parseGuide(guide, chapterB)).toThrow(StoryControlError);
    expect(() => parsePolicy(policy, chapterA)).toThrow(StoryControlError);
    expect(() => parsePreview(preview, chapterA)).toThrow(StoryControlError);
    expect(() =>
      parsePreview({ ...preview, used_characters: -1 }, chapterB),
    ).toThrow(StoryControlError);
    expect(() =>
      parsePolicy({ ...policy, pinned_fact_ids: "x" }, chapterB),
    ).toThrow(StoryControlError);
    expect(() =>
      parsePolicy({ ...policy, pinned_fact_ids: ["bad id"] }, chapterB),
    ).toThrow(StoryControlError);
    expect(() => parsePolicy(null, chapterB)).toThrow(StoryControlError);
    expect(() =>
      parseGuide(
        { ...guide, due_threads: [{ ...guide.due_threads[0], due: "y" }] },
        chapterA,
      ),
    ).toThrow(StoryControlError);
    expect(() =>
      parseArcPlan(
        { ...plan, goals: [{ ...plan.goals[0], goal: { ...goal, title: 1 } }] },
        projectId,
      ),
    ).toThrow(StoryControlError);
  });

  it("maps failures to author-facing messages and clears rejected sessions", async () => {
    const clear = vi.spyOn(securitySession, "clear");
    expect(
      storyControlError(apiError(422, "STORY_CONTROL_CYCLE")).message,
    ).toContain("循环");
    expect(
      storyControlError(apiError(422, "REQUEST_INVALID")).message,
    ).toContain("输入不完整");
    expect(storyControlError(apiError(500, "BOOM")).message).toContain(
      "故事规划请求失败",
    );
    expect(storyControlError(apiError(401, "AUTH")).code).toBe("AUTH");
    expect(clear).toHaveBeenCalled();
    const own = new StoryControlError("x", "Y");
    expect(storyControlError(own)).toBe(own);
    expect(storyControlError(new TypeError("offline")).code).toBe("NETWORK");
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      json(
        {
          error: {
            code: "STORY_CONTROL_CONFLICT",
            message: "server",
            details: {},
            retryable: false,
            suggested_action: null,
          },
          request_id: "req",
        },
        409,
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    await expect(
      storyControlClient.saveThread(projectId, "thread-1", thread, 1),
    ).rejects.toMatchObject({ code: "STORY_CONTROL_CONFLICT" });
    fetcher.mockResolvedValue(json({ nope: true }));
    await expect(storyControlClient.arcPlan(projectId)).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
  });
});

describe("structure page story control", () => {
  it("stays closed without reads until opened, then lists plans and to-dos", async () => {
    const client = fakeClient();
    render(<StoryControlSection projectId={projectId} client={client} />);
    expect(client.arcPlan).not.toHaveBeenCalled();
    const details = screen
      .getByText(/长篇规划与伏笔（/u)
      .closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    await screen.findByRole("heading", { name: "长篇规划与伏笔" });
    expect(client.timeline).toHaveBeenCalledWith(
      projectId,
      {},
      expect.any(AbortSignal),
    );
    expect(screen.getByText(/全书：夺回渡口/u)).toBeInTheDocument();
    expect(screen.getByText(/证据所在正文已修改，待复核/u)).toBeInTheDocument();
    expect(screen.getByText(/关联失效/u)).toBeInTheDocument();
    expect(screen.getByText(/（已归档）/u)).toBeInTheDocument();
    expect(screen.getAllByRole("note").length).toBe(2);
    expect(screen.getByText(/需要处理的伏笔（1）/u)).toBeInTheDocument();
    expect(screen.getByText(/兑现：第2卷/u)).toBeInTheDocument();
    expect(screen.getByText(/叙述位置：第1卷第2章/u)).toBeInTheDocument();
    expect(screen.getByText(/叙述位置：未指定/u)).toBeInTheDocument();
    expect(screen.getByText(/关联事实已失效/u)).toBeInTheDocument();
    expect(screen.getByText(/人物 · 其他「身份」/u)).toBeInTheDocument();
    expect(
      screen.getByText("「左臂」的两个不同状态区间重叠，请核对"),
    ).toBeInTheDocument();
    details.open = false;
    fireEvent(details, new Event("toggle"));
    expect(client.arcPlan).toHaveBeenCalledTimes(1);
  });

  it("creates and archives goals with chapter links and current-revision evidence", async () => {
    const client = fakeClient();
    render(<StoryControlPanel projectId={projectId} client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "新建目标" }));
    const form = screen.getByRole("form", { name: "新建目标" });
    fireEvent.change(within(form).getByLabelText("层级"), {
      target: { value: "volume" },
    });
    fireEvent.change(within(form).getByLabelText("所属分卷"), {
      target: { value: volumeA },
    });
    fireEvent.change(within(form).getByLabelText("目标名称"), {
      target: { value: "卷一目标" },
    });
    fireEvent.change(within(form).getByLabelText("主要阻碍"), {
      target: { value: "守卫" },
    });
    fireEvent.change(within(form).getByLabelText("开局状态"), {
      target: { value: "落魄" },
    });
    fireEvent.click(within(form).getByLabelText("夺回渡口"));
    fireEvent.change(within(form).getByLabelText("添加章节"), {
      target: { value: chapterA },
    });
    fireEvent.change(within(form).getByLabelText("添加章节"), {
      target: { value: chapterA },
    });
    fireEvent.change(within(form).getByLabelText("添加章节"), {
      target: { value: chapterB },
    });
    const statuses = within(form).getAllByLabelText("状态");
    fireEvent.change(statuses[0], { target: { value: "reflected" } });
    fireEvent.change(within(form).getAllByLabelText("本章说明")[0], {
      target: { value: "潜入" },
    });
    fireEvent.change(
      within(form).getAllByLabelText("正文原句（可选，作为已体现的证据）")[0],
      { target: { value: " 雨夜 " } },
    );
    fireEvent.click(
      within(form).getAllByRole("button", { name: "移除该章" })[1],
    );
    fireEvent.click(within(form).getByRole("button", { name: "保存目标" }));
    await screen.findByText("目标已保存。");
    expect(client.saveGoal).toHaveBeenCalledWith(
      projectId,
      null,
      expect.objectContaining({
        scope: "volume",
        volume_id: volumeA,
        title: "卷一目标",
        obstacle: "守卫",
        opening_state: "落魄",
        parent_goal_ids: ["goal-book"],
        links: [
          {
            chapter_id: chapterA,
            status: "reflected",
            note: "潜入",
            quote: "雨夜",
            chapter_revision_id: "chv_a",
          },
        ],
      }),
      0,
    );
    expect(client.arcPlan).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "编辑「夺回渡口」" }));
    const edit = screen.getByRole("form", { name: "编辑目标「夺回渡口」" });
    fireEvent.click(within(edit).getByRole("button", { name: "保存目标" }));
    await waitFor(() => expect(client.saveGoal).toHaveBeenCalledTimes(2));
    expect(vi.mocked(client.saveGoal).mock.calls[1][2].links[0]).toMatchObject({
      quote: "雨夜",
      chapter_revision_id: "chv_old",
    });
    fireEvent.click(screen.getByRole("button", { name: "编辑「夺回渡口」" }));
    fireEvent.click(screen.getByRole("button", { name: "归档目标" }));
    await waitFor(() => expect(client.saveGoal).toHaveBeenCalledTimes(3));
    expect(vi.mocked(client.saveGoal).mock.calls[2]).toEqual([
      projectId,
      "goal-book",
      expect.objectContaining({ status: "archived" }),
      1,
    ]);
    fireEvent.click(screen.getByRole("button", { name: "编辑「卷一潜入」" }));
    fireEvent.click(screen.getByRole("button", { name: "恢复目标" }));
    await waitFor(() => expect(client.saveGoal).toHaveBeenCalledTimes(4));
    fireEvent.click(screen.getByRole("button", { name: "新建目标" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("saves plot threads with evidence and shows conflicts without losing the form", async () => {
    const client = fakeClient({
      saveThread: vi
        .fn()
        .mockRejectedValueOnce(apiError(409, "STORY_CONTROL_CONFLICT"))
        .mockResolvedValue(thread),
    });
    render(<StoryControlPanel projectId={projectId} client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "新建伏笔" }));
    const form = screen.getByRole("form", { name: "新建伏笔" });
    fireEvent.change(within(form).getByLabelText("伏笔名称"), {
      target: { value: "玉佩" },
    });
    fireEvent.change(within(form).getByLabelText("内容"), {
      target: { value: "母亲遗物" },
    });
    fireEvent.click(within(form).getByLabelText("船夫"));
    fireEvent.click(within(form).getByLabelText("船夫"));
    fireEvent.click(within(form).getByLabelText("船夫"));
    fireEvent.change(within(form).getByLabelText("预计埋设章"), {
      target: { value: chapterA },
    });
    fireEvent.change(within(form).getByLabelText("预计兑现章"), {
      target: { value: chapterB },
    });
    fireEvent.change(within(form).getByLabelText("或预计兑现卷"), {
      target: { value: volumeB },
    });
    fireEvent.change(within(form).getByLabelText("或预计兑现卷"), {
      target: { value: "" },
    });
    fireEvent.change(within(form).getByLabelText("预计兑现章"), {
      target: { value: chapterB },
    });
    fireEvent.change(within(form).getByLabelText("预计兑现章"), {
      target: { value: "" },
    });
    fireEvent.change(within(form).getByLabelText("优先级"), {
      target: { value: "high" },
    });
    fireEvent.change(within(form).getByLabelText(/^状态（/u), {
      target: { value: "planted" },
    });
    fireEvent.change(within(form).getByLabelText("备注 / 延期或放弃理由"), {
      target: { value: "第二卷揭开" },
    });
    fireEvent.change(within(form).getByLabelText("证据类型"), {
      target: { value: "setup" },
    });
    const add = within(form).getByRole("button", { name: "添加证据" });
    expect(add).toBeDisabled();
    fireEvent.change(within(form).getByLabelText("证据所在章"), {
      target: { value: chapterA },
    });
    fireEvent.change(within(form).getByLabelText("已保存正文中的原句"), {
      target: { value: "玉佩发烫" },
    });
    fireEvent.click(add);
    fireEvent.change(within(form).getByLabelText("证据所在章"), {
      target: { value: chapterB },
    });
    fireEvent.change(within(form).getByLabelText("已保存正文中的原句"), {
      target: { value: "多余" },
    });
    fireEvent.click(add);
    fireEvent.click(
      within(form).getAllByRole("button", { name: "移除证据" })[1],
    );
    fireEvent.click(within(form).getByRole("button", { name: "保存伏笔" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "已保留你的输入",
    );
    expect(screen.getByRole("form", { name: "新建伏笔" })).toBeInTheDocument();
    fireEvent.click(within(form).getByRole("button", { name: "保存伏笔" }));
    await screen.findByText("伏笔已保存。");
    expect(vi.mocked(client.saveThread).mock.calls[1]).toEqual([
      projectId,
      null,
      {
        title: "玉佩",
        content: "母亲遗物",
        character_ids: ["chr_boat"],
        planned_setup_chapter_id: chapterA,
        planned_payoff_chapter_id: null,
        planned_payoff_volume_id: null,
        priority: "high",
        status: "planted",
        note: "第二卷揭开",
        anchors: [
          {
            role: "setup",
            chapter_id: chapterA,
            chapter_revision_id: "chv_a",
            quote: "玉佩发烫",
          },
        ],
      },
      0,
    ]);
    fireEvent.click(
      screen.getByRole("button", { name: "编辑伏笔「船夫旧伤」" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存伏笔" }));
    await waitFor(() => expect(client.saveThread).toHaveBeenCalledTimes(3));
    expect(vi.mocked(client.saveThread).mock.calls[2][1]).toBe("thread-1");
    fireEvent.click(screen.getByRole("button", { name: "新建伏笔" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    fireEvent.change(screen.getByLabelText("按状态筛选"), {
      target: { value: "planted" },
    });
    fireEvent.change(screen.getByLabelText("按人物筛选"), {
      target: { value: "chr_boat" },
    });
    await waitFor(() =>
      expect(client.timeline).toHaveBeenLastCalledWith(
        projectId,
        { status: "planted", character_id: "chr_boat" },
        expect.any(AbortSignal),
      ),
    );
  });

  it("records events with relative order and character state intervals", async () => {
    const client = fakeClient();
    render(<StoryControlPanel projectId={projectId} client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "新建事件" }));
    const form = screen.getByRole("form", { name: "新建事件" });
    fireEvent.change(within(form).getByLabelText("事件名称"), {
      target: { value: "伤愈" },
    });
    fireEvent.change(
      within(form).getByLabelText("故事时间（可留空，如“十年前”）"),
      {
        target: { value: "三月后" },
      },
    );
    fireEvent.change(within(form).getByLabelText("叙述所在章"), {
      target: { value: chapterB },
    });
    const after = within(form).getByRole("group", {
      name: "发生在这些事件之后",
    });
    fireEvent.click(within(after).getByLabelText("渡口失火"));
    fireEvent.click(within(form).getByRole("button", { name: "保存事件" }));
    await screen.findByText("事件已保存。");
    expect(client.saveEvent).toHaveBeenCalledWith(
      projectId,
      null,
      expect.objectContaining({
        title: "伤愈",
        story_time: "三月后",
        chapter_id: chapterB,
        after_event_ids: ["event-now"],
        before_event_ids: [],
      }),
      0,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "编辑事件「十年前的大火」" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "归档事件" }));
    await waitFor(() => expect(client.saveEvent).toHaveBeenCalledTimes(2));
    expect(vi.mocked(client.saveEvent).mock.calls[1]).toEqual([
      projectId,
      "event-past",
      expect.objectContaining({
        archived: true,
        before_event_ids: ["event-now"],
      }),
      1,
    ]);
    fireEvent.click(screen.getByRole("button", { name: "新建事件" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    fireEvent.click(screen.getByRole("button", { name: "新建人物状态" }));
    const state = screen.getByRole("form", { name: "新建人物状态" });
    fireEvent.change(within(state).getByLabelText("人物"), {
      target: { value: "chr_boat" },
    });
    fireEvent.change(within(state).getByLabelText("状态类别"), {
      target: { value: "possession" },
    });
    fireEvent.change(within(state).getByLabelText("项目（如“左臂”）"), {
      target: { value: "玉佩" },
    });
    fireEvent.change(within(state).getByLabelText("状态"), {
      target: { value: "随身" },
    });
    fireEvent.change(within(state).getByLabelText("开始事件"), {
      target: { value: "event-now" },
    });
    fireEvent.change(
      within(state).getByLabelText("结束事件（可留空，表示仍然有效）"),
      {
        target: { value: "event-past" },
      },
    );
    fireEvent.change(
      within(state).getByLabelText("结束事件（可留空，表示仍然有效）"),
      {
        target: { value: "" },
      },
    );
    fireEvent.click(
      within(state).getByRole("button", { name: "保存人物状态" }),
    );
    await screen.findByText("人物状态已保存。");
    expect(client.saveState).toHaveBeenCalledWith(
      projectId,
      null,
      {
        character_id: "chr_boat",
        attribute: "possession",
        label: "玉佩",
        value: "随身",
        start_event_id: "event-now",
        end_event_id: null,
        fact_ids: [],
        archived: false,
      },
      0,
    );
    fireEvent.click(screen.getByRole("button", { name: "新建人物状态" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
  });

  it("shows empty and failed states honestly", async () => {
    const empty = fakeClient({
      arcPlan: vi
        .fn()
        .mockResolvedValue({ ...plan, goals: [], characters: [] }),
      timeline: vi.fn().mockResolvedValue({
        ...timeline,
        threads: [],
        events: [],
        states: [],
        warnings: [],
      }),
    });
    const { unmount } = render(
      <StoryControlPanel projectId={projectId} client={empty} />,
    );
    expect(await screen.findByText(/还没有目标/u)).toBeInTheDocument();
    expect(screen.getByText("没有符合条件的伏笔。")).toBeInTheDocument();
    expect(screen.getByText(/还没有事件/u)).toBeInTheDocument();
    expect(screen.getByText("还没有人物状态。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建人物状态" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "新建伏笔" }));
    expect(
      screen.queryByRole("group", { name: "涉及人物" }),
    ).not.toBeInTheDocument();
    unmount();
    const failing = fakeClient({
      arcPlan: vi
        .fn()
        .mockRejectedValue(apiError(503, "AI_WORKFLOW_SCHEMA_REQUIRED")),
    });
    render(<StoryControlPanel projectId={projectId} client={failing} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "备份并启用 AI 协作",
    );
  });
});

describe("writing desk story control", () => {
  it("shows the chapter's planned tasks or an empty hint, and read failures", async () => {
    const client = fakeClient();
    const { unmount } = render(
      <MemoryRouter>
        <ChapterGuideCard
          projectId={projectId}
          chapterId={chapterA}
          sourceRevision="chv_a"
          client={client}
        />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText(/全书：夺回渡口（已体现） · 第一次靠近/u),
    ).toBeInTheDocument();
    expect(screen.getByText("计划在本章埋设")).toBeInTheDocument();
    expect(screen.getAllByText(/预计兑现章已有正文/u).length).toBeGreaterThan(
      0,
    );
    unmount();
    const empty = fakeClient({
      guide: vi.fn().mockResolvedValue({
        ...guide,
        goals: [{ ...plan.goals[0], goal: { ...goal, links: [] }, links: [] }],
        setup_threads: [],
        payoff_threads: [],
        due_threads: [],
      }),
    });
    const second = render(
      <MemoryRouter>
        <ChapterGuideCard
          projectId={projectId}
          chapterId={chapterA}
          sourceRevision="chv_a"
          client={empty}
        />
      </MemoryRouter>,
    );
    expect(await screen.findByText("全书：夺回渡口")).toBeInTheDocument();
    second.unmount();
    const none = fakeClient({
      guide: vi.fn().mockResolvedValue({
        ...guide,
        goals: [],
        setup_threads: [],
        payoff_threads: [],
        due_threads: [],
      }),
    });
    const third = render(
      <MemoryRouter>
        <ChapterGuideCard
          projectId={projectId}
          chapterId={chapterA}
          sourceRevision="chv_a"
          client={none}
        />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("link", { name: "小说结构" }),
    ).toBeInTheDocument();
    third.unmount();
    const failing = fakeClient({
      guide: vi.fn().mockRejectedValue(new TypeError("offline")),
    });
    render(
      <MemoryRouter>
        <ChapterGuideCard
          projectId={projectId}
          chapterId={chapterA}
          sourceRevision="chv_a"
          client={failing}
        />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("连接中断");
  });

  it("previews, pins, excludes and saves the recall policy without model calls", async () => {
    const client = fakeClient();
    render(
      <RecallControl
        projectId={projectId}
        chapterId={chapterB}
        sourceRevision="chv_b"
        lastRecall={["fact-2", "fact-9"]}
        client={client}
      />,
    );
    expect(
      await screen.findByText(/已选 2 \/ 24 项（作者固定 1 项）/u),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/新增 1 项（船夫旧伤），移除 1 项/u),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("meter", { name: "事实召回字符预算" }),
    ).toHaveAttribute("value", "200");
    fireEvent.change(screen.getByLabelText("关键词"), {
      target: { value: " 船夫 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "检索事实" }));
    expect(
      await screen.findByText("找到 2 条已确认事实。"),
    ).toBeInTheDocument();
    expect(client.searchFacts).toHaveBeenCalledWith(projectId, {
      q: "船夫",
      status: "confirmed",
      forChapter: chapterB,
    });
    expect(
      screen.getByRole("button", { name: "固定「后文事实」" }),
    ).toBeDisabled();
    expect(screen.getByText(/来源已修改，需重新确认/u)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "保存为本章召回设置" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "排除「船夫旧伤」" }));
    await waitFor(() =>
      expect(client.recallPreview).toHaveBeenLastCalledWith(
        chapterB,
        [],
        ["fact-1"],
      ),
    );
    expect(screen.getByText(/有未保存的调整/u)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "取消排除「船夫旧伤」" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "固定「船夫旧伤」" }));
    fireEvent.click(
      screen.getByRole("button", { name: "取消固定「船夫旧伤」" }),
    );
    await waitFor(() =>
      expect(client.recallPreview).toHaveBeenLastCalledWith(chapterB, [], []),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存为本章召回设置" }));
    expect(
      await screen.findByText(/已保存为本章召回设置第 2 版/u),
    ).toBeInTheDocument();
    expect(client.saveRecallPolicy).toHaveBeenCalledWith(chapterB, [], [], 1);
  });

  it("explains blocked pins, reloads after a conflict and reports read failures", async () => {
    const blocked: RecallPreview = {
      ...preview,
      selected: [],
      omitted: [
        { id: "fact-1", title: null, reason: "pin_stale" },
        { id: "fact-3", title: "旧事", reason: "excluded" },
      ],
      blocked: true,
    };
    const client = fakeClient({
      recallPreview: vi.fn().mockResolvedValue(blocked),
      saveRecallPolicy: vi
        .fn()
        .mockRejectedValue(apiError(409, "STORY_CONTROL_CONFLICT")),
      searchFacts: vi.fn().mockRejectedValue(apiError(500, "BOOM")),
    });
    render(
      <RecallControl
        projectId={projectId}
        chapterId={chapterB}
        sourceRevision="chv_b"
        client={client}
      />,
    );
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "已删除的事实：固定项来源正文已修改，需重新确认",
    );
    expect(alert).not.toHaveTextContent("旧事");
    expect(screen.getByText(/固定：已选事实；排除：无/u)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "检索事实" }));
    expect(await screen.findByText(/故事规划请求失败/u)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("关键词"), {
      target: { value: "" },
    });
    await act(async () => {
      await Promise.resolve();
    });
    // Make the draft dirty through a direct search result toggle.
    vi.mocked(client.searchFacts).mockResolvedValue(facts);
    fireEvent.click(screen.getByRole("button", { name: "检索事实" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "取消固定「船夫旧伤」" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存为本章召回设置" }));
    await waitFor(() => expect(client.recallPolicy).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/已在其他窗口修改/u)).toBeInTheDocument();
  });

  it("shows policy and preview read failures", async () => {
    const client = fakeClient({
      recallPolicy: vi
        .fn()
        .mockRejectedValue(apiError(503, "STORY_CONTROL_UNAVAILABLE")),
    });
    const { unmount } = render(
      <RecallControl
        projectId={projectId}
        chapterId={chapterB}
        sourceRevision="chv_b"
        client={client}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "故事规划暂不可用",
    );
    expect(screen.getByRole("status")).toHaveTextContent("正在计算本次依据");
    unmount();
    const previewFails = fakeClient({
      recallPreview: vi
        .fn()
        .mockRejectedValue(apiError(404, "CHAPTER_NOT_FOUND")),
    });
    render(
      <RecallControl
        projectId={projectId}
        chapterId={chapterB}
        sourceRevision="chv_b"
        client={previewFails}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("章节已不存在");
  });

  it("mounts the chapter task and recall controls inside the prepare tab only when opened", async () => {
    const model: ModelProfile = {
      id: "default-local",
      name: "测试模型",
      kind: "local",
      base_url: "http://127.0.0.1:1234/v1",
      model: "test-model",
      max_output_tokens: 2048,
      has_key: false,
    };
    const run = {
      run_id: "run-one",
      chapter_id: chapterB,
      operation: "continue",
      status: "ready",
      base_revision_id: "revision-one",
      base_version: 1,
      current_revision_id: "revision-one",
      current_version: 1,
      instruction: "",
      selected_text: "",
      profile_id: model.id,
      model_snapshot: model,
      max_steps: 1,
      max_output_characters: 300,
      generated_steps: 0,
      generated_characters: 0,
      context: {
        text: "甲",
        sha256: "a".repeat(64),
        manifest: {
          included_sources: ["story_memory"],
          omitted_sources: [],
          truncated: false,
          character_count: 1,
          sources: [
            {
              source: "story_memory",
              references: [["fact-2", "fr-2"]],
              text: "",
              reason: "",
              omitted_reason: null,
              truncated: false,
            },
            {
              source: "story_guide",
              references: [],
              text: "",
              reason: "",
              omitted_reason: null,
              truncated: false,
            },
          ],
        },
      },
      candidates: [],
      last_error: null,
    } as unknown as WorkflowRun;
    const api = {
      upgrade: vi.fn().mockResolvedValue(undefined),
      models: vi.fn().mockResolvedValue([model]),
      saveModel: vi.fn(),
      list: vi.fn().mockResolvedValue([run]),
      create: vi.fn(),
      action: vi.fn(),
      candidate: vi.fn(),
      saveEdit: vi.fn(),
    } as unknown as AIWorkflowClient;
    const client = fakeClient();
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")),
    );
    function Harness() {
      const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
      return (
        <MemoryRouter>
          <AIWorkflowAssistant
            chapterId={chapterB}
            projectId={projectId}
            writing={writing}
            selection={null}
            client={api}
            storyControlClient={client}
          />
        </MemoryRouter>
      );
    }
    render(<Harness />);
    fireEvent.click(await screen.findByRole("tab", { name: "准备" }));
    const summary = await screen.findByText(/本章任务与本次依据/u);
    expect(client.guide).not.toHaveBeenCalled();
    const details = summary.closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    expect(
      await screen.findByText(/新增 1 项（船夫旧伤），移除 0 项/u),
    ).toBeInTheDocument();
    expect(client.guide).toHaveBeenCalled();
    details.open = false;
    fireEvent(details, new Event("toggle"));
  });
});

it("opens and focuses the linked persisted plot thread", async () => {
  const original = Object.getOwnPropertyDescriptor(
    HTMLElement.prototype,
    "scrollIntoView",
  );
  const scroll = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: scroll,
  });
  try {
    render(
      <StoryControlSection
        projectId={projectId}
        focusThreadId={thread.id}
        client={fakeClient()}
      />,
    );
    await waitFor(() =>
      expect(document.getElementById(`thread-${thread.id}`)).toHaveFocus(),
    );
    expect(scroll).toHaveBeenCalled();
    expect(
      document.querySelector("details.story-control-section"),
    ).toHaveAttribute("open");
  } finally {
    if (original)
      Object.defineProperty(HTMLElement.prototype, "scrollIntoView", original);
    else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  }
});
