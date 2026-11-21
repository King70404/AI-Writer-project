import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { securitySession } from "../../frontend/src/api/security-session";
import {
  parseProposal,
  planProposalClient,
  type PlanProposalClient,
} from "../../frontend/src/features/story-control/api/planProposal";
import type {
  ArcPlan,
  Goal,
} from "../../frontend/src/features/story-control/api/storyControl";
import { PlanProposalPanel } from "../../frontend/src/features/story-control/components/PlanProposalPanel";
import { StoryControlPanel } from "../../frontend/src/features/story-control/components/StoryControlPanel";
import type { StoryControlClient } from "../../frontend/src/features/story-control/api/storyControl";
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

const goal: Goal = {
  id: "goal-book",
  version: 1,
  revision_id: "rev-1",
  updated_at: "t",
  scope: "book",
  volume_id: null,
  parent_goal_ids: [],
  title: "夺回渡口",
  conflict: "渡口被夺",
  desire: "",
  obstacle: "",
  turn: "",
  outcome: "",
  opening_state: "",
  target_characters: null,
  status: "active",
  links: [],
};
const plan: ArcPlan = {
  project_id: projectId,
  goals: [{ goal, links: [], child_goal_ids: [], reflected: 0, open_links: 0 }],
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

function raw(overrides: Record<string, unknown> = {}) {
  const merged = rawBase(overrides);
  return {
    ...merged,
    adoptions: (merged.adoptions as Record<string, unknown>[]).map((item) => ({
      edited: false,
      ...item,
    })),
  };
}

function rawBase(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    id: "proposal-1",
    project_id: projectId,
    goal_id: goal.id,
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
    source: {
      id: goal.id,
      version: 1,
      scope: "book",
      volume_id: null,
      title: goal.title,
      conflict: goal.conflict,
      desire: "",
      obstacle: "",
      turn: "",
      outcome: "",
      opening_state: "",
      status: "active",
      linked_chapter_ids: [],
    },
    children: [],
    goal_versions: { [goal.id]: 1 },
    volumes: [{ volume_id: volumeA, title: "卷一", position: 1 }],
    chapters: [
      {
        chapter_id: chapterA,
        volume_id: volumeA,
        title: "第一章",
        volume_position: 1,
        position: 1,
      },
    ],
    chapters_omitted: 0,
    summary: null,
    cards: [],
    error: null,
    evidence: null,
    evidence_truncated: false,
    adoptions: [],
    edits: [],
    undos: [],
    known_goal_version: 1,
    created_goal_ids: [],
    created_at: "t",
    updated_at: "t",
    request_preview: "[system]\n只输出 JSON\n\n[user]\n{}",
    ...overrides,
  };
}
const cards = [
  {
    kind: "child_goal",
    title: "卷一立足",
    volume_id: volumeA,
    conflict: "被逐",
    obstacle: "",
    turn: "",
    outcome: "",
    chapter_ids: [chapterA],
    reason: "开局",
  },
  { kind: "chapter_link", chapter_id: chapterB, note: "揭示阴谋", reason: "" },
];
const ready = parseProposal(raw(), projectId);
const completed = parseProposal(
  raw({ version: 3, status: "completed", summary: "按卷拆分", cards }),
  projectId,
);

function fakeClient(overrides: Partial<PlanProposalClient> = {}) {
  return {
    models: vi
      .fn()
      .mockResolvedValue([
        { id: "default-local", name: "本机模型", kind: "local" },
      ]),
    list: vi.fn().mockResolvedValue([]),
    prepare: vi.fn().mockResolvedValue(ready),
    estimate: vi.fn().mockResolvedValue(allowedAnalysisEstimate()),
    send: vi.fn().mockResolvedValue(completed),
    adopt: vi.fn(),
    editCard: vi.fn(),
    undo: vi.fn(),
    ...overrides,
  } as unknown as PlanProposalClient & {
    editCard: ReturnType<typeof vi.fn>;
    undo: ReturnType<typeof vi.fn>;
    prepare: ReturnType<typeof vi.fn>;
    send: ReturnType<typeof vi.fn>;
    adopt: ReturnType<typeof vi.fn>;
    estimate: ReturnType<typeof vi.fn>;
  };
}

function json(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

describe("plan proposal API", () => {
  it("uses the frozen proposal endpoints with CSRF and strict parsing", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockImplementation(() => Promise.resolve(json(raw(), 201)));
    await expect(
      planProposalClient.prepare(projectId, goal.id, "default-local", "两段"),
    ).resolves.toEqual(ready);
    fetcher.mockImplementation(() =>
      Promise.resolve(json(allowedAnalysisEstimate())),
    );
    await planProposalClient.estimate(projectId, ready.id);
    fetcher.mockImplementation(() =>
      Promise.resolve(json(raw({ status: "completed", cards }))),
    );
    await planProposalClient.send(projectId, ready, false);
    await planProposalClient.adopt(projectId, ready.id, [1]);
    const calls = fetcher.mock.calls.map(([url, options]) => [
      options?.method,
      url,
      options?.body ?? null,
    ]);
    const root = `/api/v1/projects/${projectId}/plan-proposals`;
    expect(calls).toEqual([
      [
        "POST",
        root,
        JSON.stringify({
          goal_id: goal.id,
          profile_id: "default-local",
          author_request: "两段",
        }),
      ],
      ["GET", `${root}/proposal-1/estimate`, null],
      [
        "POST",
        `${root}/proposal-1/send`,
        JSON.stringify({ expected_version: 1, cloud_consent: false }),
      ],
      [
        "POST",
        `${root}/proposal-1/adopt`,
        JSON.stringify({ card_indexes: [1] }),
      ],
    ]);
    const headers = new Headers(fetcher.mock.calls[0][1]?.headers);
    expect(headers.get("X-CSRF-Token")).toBe("fake-csrf-proof".repeat(3));
  });

  it("rejects unknown card kinds and maps a stale adoption", async () => {
    expect(() =>
      parseProposal(
        raw({ cards: [{ kind: "rewrite_chapter", chapter_id: chapterA }] }),
        projectId,
      ),
    ).toThrow(/无法安全读取/u);
    expect(() => parseProposal(raw(), "prj_other")).toThrow();
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockResolvedValue(
      json(
        {
          error: {
            code: "PLAN_PROPOSAL_STALE",
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
      planProposalClient.adopt(projectId, ready.id, [0]),
    ).rejects.toMatchObject({ code: "PLAN_PROPOSAL_STALE" });
  });
});

describe("plan proposal panel", () => {
  function renderPanel(client: PlanProposalClient, onAdopted = vi.fn()) {
    render(
      <PlanProposalPanel
        projectId={projectId}
        goal={goal}
        plan={plan}
        client={client}
        onAdopted={onAdopted}
        onClose={vi.fn()}
      />,
    );
    return onAdopted;
  }

  it("previews, estimates, sends once and adopts only the selected cards", async () => {
    const client = fakeClient();
    client.adopt.mockResolvedValue(
      parseProposal(
        raw({
          version: 4,
          status: "completed",
          summary: "按卷拆分",
          cards,
          adoptions: [
            {
              index: 1,
              action: "linked",
              goal_id: goal.id,
              goal_version: 2,
              adopted_at: "t",
            },
          ],
        }),
        projectId,
      ),
    );
    const onAdopted = renderPanel(client);
    expect(await screen.findByText(/当前目标/u)).toHaveTextContent("夺回渡口");
    expect(client.estimate).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("拆分要求（可选，最多 500 字）"), {
      target: { value: "拆成两段" },
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /准备建议/u }),
      ).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: /准备建议/u }));
    await screen.findByText(/查看将发送的完整内容/u);
    expect(client.prepare).toHaveBeenCalledWith(
      projectId,
      goal.id,
      "default-local",
      "拆成两段",
    );
    expect(client.send).not.toHaveBeenCalled();
    const send = await screen.findByRole("button", { name: /发送一次/u });
    await waitFor(() => expect(send).not.toBeDisabled());
    expect(client.estimate).toHaveBeenCalledWith(projectId, ready.id);
    fireEvent.click(send);
    await screen.findByText(/模型思路：按卷拆分/u);
    expect(client.send).toHaveBeenCalledTimes(1);
    expect(client.adopt).not.toHaveBeenCalled();
    const adopt = screen.getByRole("button", { name: "采用所选（0）" });
    expect(adopt).toBeDisabled();
    fireEvent.click(screen.getByLabelText("选择建议卡 2"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选（1）" }));
    await waitFor(() => expect(onAdopted).toHaveBeenCalledTimes(1));
    expect(client.adopt).toHaveBeenCalledWith(projectId, ready.id, [1]);
    expect(screen.getByLabelText("选择建议卡 2")).toBeDisabled();
    expect(screen.getByText(/已采用/u)).toBeInTheDocument();
  });

  it("blocks sending under a strict budget refusal", async () => {
    const client = fakeClient({
      list: vi.fn().mockResolvedValue([ready]),
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
    const failed = parseProposal(
      raw({
        version: 3,
        status: "failed",
        error: "PlanProposalOutputInvalid",
        evidence: "好的```json{}```",
      }),
      projectId,
    );
    const client = fakeClient({
      list: vi.fn().mockResolvedValue([ready]),
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
    fireEvent.click(screen.getByRole("button", { name: "重新准备" }));
    expect(
      await screen.findByRole("button", { name: /准备建议/u }),
    ).toBeInTheDocument();
  });

  it("asks to prepare again when the plan changed before adoption", async () => {
    const { PlanProposalError } =
      await import("../../frontend/src/features/story-control/api/planProposal");
    const client = fakeClient({
      list: vi.fn().mockResolvedValue([completed]),
    });
    client.adopt.mockRejectedValue(
      new PlanProposalError(
        "规划已被修改，请重新准备建议。",
        "PLAN_PROPOSAL_STALE",
      ),
    );
    const onAdopted = renderPanel(client);
    fireEvent.click(await screen.findByLabelText("选择建议卡 1"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选（1）" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "请重新准备建议",
    );
    expect(onAdopted).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "重新准备建议" }),
    ).toBeInTheDocument();
  });
});

describe("plan proposal card edits and undo", () => {
  const editedCard = { ...cards[0], title: "卷一立足·作者改" };
  const withEdit = parseProposal(
    raw({
      version: 4,
      status: "completed",
      summary: "按卷拆分",
      cards,
      edits: [{ index: 0, card: editedCard, edited_at: "t" }],
    }),
    projectId,
  );
  const adoptedLink = parseProposal(
    raw({
      version: 5,
      status: "completed",
      cards,
      adoptions: [
        {
          index: 1,
          action: "linked",
          goal_id: goal.id,
          goal_version: 2,
          adopted_at: "t",
          edited: false,
        },
      ],
    }),
    projectId,
  );

  it("sends edits and undo with the proposal version and CSRF", async () => {
    const fetcher = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetcher);
    fetcher.mockImplementation(() =>
      Promise.resolve(
        json(
          raw({
            version: 4,
            status: "completed",
            cards,
            edits: [{ index: 0, card: editedCard, edited_at: "t" }],
            undos: [
              { index: 1, action: "linked", goal_id: goal.id, undone_at: "t" },
            ],
          }),
        ),
      ),
    );
    const edited = await planProposalClient.editCard(
      projectId,
      completed,
      0,
      completed.cards[0],
    );
    expect(edited.edits).toEqual([{ index: 0, card: editedCard }]);
    expect(edited.undos).toEqual([{ index: 1, action: "linked" }]);
    await planProposalClient.editCard(projectId, completed, 0, null);
    await planProposalClient.undo(projectId, completed, 1);
    const root = `/api/v1/projects/${projectId}/plan-proposals/proposal-1`;
    expect(
      fetcher.mock.calls.map(([url, options]) => [
        options?.method,
        url,
        options?.body,
      ]),
    ).toEqual([
      [
        "PUT",
        `${root}/cards/0`,
        JSON.stringify({ expected_version: 3, card: completed.cards[0] }),
      ],
      [
        "PUT",
        `${root}/cards/0`,
        JSON.stringify({ expected_version: 3, card: null }),
      ],
      [
        "POST",
        `${root}/undo`,
        JSON.stringify({ expected_version: 3, card_index: 1 }),
      ],
    ]);
    for (const call of fetcher.mock.calls)
      expect(new Headers(call[1]?.headers).get("X-CSRF-Token")).toBe(
        "fake-csrf-proof".repeat(3),
      );
  });

  it("edits a card, keeps the original for comparison and can restore it", async () => {
    const client = fakeClient({ list: vi.fn().mockResolvedValue([completed]) });
    client.editCard
      .mockResolvedValueOnce(withEdit)
      .mockResolvedValueOnce(completed);
    render(
      <PlanProposalPanel
        projectId={projectId}
        goal={goal}
        plan={plan}
        client={client}
        onAdopted={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "修改建议卡 1" }),
    );
    fireEvent.change(screen.getByLabelText("子目标名（最多 120 字）"), {
      target: { value: "卷一立足·作者改" },
    });
    expect(screen.getByText(/模型理由（不可修改）：开局/u)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await screen.findByText("对照模型原始建议");
    expect(client.editCard).toHaveBeenCalledWith(projectId, completed, 0, {
      ...completed.cards[0],
      title: "卷一立足·作者改",
    });
    expect(client.adopt).not.toHaveBeenCalled();
    expect(
      screen.getByText(/新子目标「卷一立足·作者改」/u),
    ).toBeInTheDocument();
    expect(screen.getByText(/新子目标「卷一立足」/u)).toBeInTheDocument();
    expect(screen.getByText(/已修改/u)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "恢复建议卡 1 的原始建议" }),
    );
    await waitFor(() =>
      expect(client.editCard).toHaveBeenLastCalledWith(
        projectId,
        withEdit,
        0,
        null,
      ),
    );
    await waitFor(() =>
      expect(screen.queryByText("对照模型原始建议")).toBeNull(),
    );
  });

  it("undoes an adopted card and reports a refused undo without changes", async () => {
    const { PlanProposalError } =
      await import("../../frontend/src/features/story-control/api/planProposal");
    const client = fakeClient({
      list: vi.fn().mockResolvedValue([adoptedLink]),
    });
    client.undo
      .mockRejectedValueOnce(
        new PlanProposalError(
          "这张卡写入的规划之后已被修改，没有撤销。",
          "PLAN_PROPOSAL_UNDO_CONFLICT",
        ),
      )
      .mockResolvedValueOnce(completed);
    const onAdopted = vi.fn();
    const onUndone = vi.fn();
    render(
      <PlanProposalPanel
        projectId={projectId}
        goal={goal}
        plan={plan}
        client={client}
        onAdopted={onAdopted}
        onUndone={onUndone}
        onClose={vi.fn()}
      />,
    );
    const undo = await screen.findByRole("button", {
      name: "撤销采用建议卡 2",
    });
    expect(screen.queryByRole("button", { name: "修改建议卡 2" })).toBeNull();
    fireEvent.click(undo);
    expect(await screen.findByRole("alert")).toHaveTextContent("没有撤销");
    expect(onUndone).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "撤销采用建议卡 2" }));
    await waitFor(() => expect(onUndone).toHaveBeenCalledTimes(1));
    expect(client.undo).toHaveBeenLastCalledWith(projectId, adoptedLink, 1);
    expect(onAdopted).not.toHaveBeenCalled();
    expect(
      await screen.findByRole("button", { name: "修改建议卡 2" }),
    ).toBeInTheDocument();
  });
});

describe("structure page goal area", () => {
  it("opens the split suggestion only on request and refreshes plans after adoption", async () => {
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
    const proposals = fakeClient({
      list: vi.fn().mockResolvedValue([completed]),
    });
    proposals.adopt.mockResolvedValue(completed);
    render(
      <StoryControlPanel
        projectId={projectId}
        client={control}
        proposalClient={proposals}
      />,
    );
    const open = await screen.findByRole("button", {
      name: "建议拆分「夺回渡口」",
    });
    expect(proposals.models).not.toHaveBeenCalled();
    fireEvent.click(open);
    fireEvent.click(await screen.findByLabelText("选择建议卡 1"));
    fireEvent.click(screen.getByRole("button", { name: "采用所选（1）" }));
    expect(
      await screen.findByText("已采用所选建议卡，规划已更新。"),
    ).toBeInTheDocument();
    await waitFor(() => expect(arcPlan).toHaveBeenCalledTimes(2));
    expect(proposals.prepare).not.toHaveBeenCalled();
    expect(proposals.send).not.toHaveBeenCalled();
  });
});
