import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { securitySession } from "../../frontend/src/api/security-session";
import {
  aiWorkflowClient,
  parseWorkflowRun,
  workflowFailureMessage,
  type AIWorkflowClient,
  type CandidateEdit,
  type ModelProfile,
  type WorkflowRun,
} from "../../frontend/src/features/novel-structure/api/ai-workflow";
import { AIWorkflowAssistant } from "../../frontend/src/features/novel-structure/components/AIWorkflowAssistant";
import { CandidateEditor } from "../../frontend/src/features/novel-structure/components/CandidateEditor";
import { ConflictResolution } from "../../frontend/src/features/novel-structure/components/ConflictResolution";
import {
  editIsCurrent,
  visibleCharacters,
} from "../../frontend/src/features/novel-structure/candidate-edit";
import { useChapterWriting } from "../../frontend/src/features/novel-structure/hooks/useChapterWriting";
import {
  budgetClient,
  BudgetError,
  isAmount,
  isCurrency,
  parseBudget,
  parseEstimate,
  parsePriceState,
  type BudgetClient,
  type BudgetView,
  type PriceState,
  type SendEstimate,
} from "../../frontend/src/features/usage/api/budget";
import { BudgetSettingsPanel } from "../../frontend/src/features/usage/components/BudgetSettingsPanel";
import { SendEstimatePanel } from "../../frontend/src/features/usage/components/SendEstimatePanel";
import {
  DRAFT_PREFIX,
  DraftStorageError,
  downloadText,
  draftFilename,
  draftKey,
  fetchStorageInstance,
  listDrafts,
  removeDraft,
  saveDraft,
  type LocalDraft,
} from "../../frontend/src/features/local-drafts/drafts";
import { LocalDraftManager } from "../../frontend/src/features/local-drafts/LocalDraftManager";
import { LocalDraftRecovery } from "../../frontend/src/features/local-drafts/LocalDraftRecovery";
import { useLocalDraft } from "../../frontend/src/features/local-drafts/useLocalDraft";
import { VersionComparison } from "../../frontend/src/features/local-drafts/VersionComparison";
import { chapterId, structureProjectId } from "./novel-structure-support";
import { written, writingClient } from "./chapter-writing-support";
import { structureError } from "./novel-structure-support";

const projectId = structureProjectId;
const REVISION = "chv_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const INSTANCE = "a".repeat(32);
const EDIT_ID = "11111111-1111-4111-8111-111111111111";
const EDIT_TWO = "22222222-2222-4222-8222-222222222222";

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  securitySession.clear();
  window.localStorage.clear();
});

const model: ModelProfile = {
  id: "default-local",
  name: "测试模型",
  kind: "local",
  base_url: "http://127.0.0.1:1234/v1",
  model: "test-model",
  max_output_tokens: 2048,
  has_key: false,
};
const edit: CandidateEdit = {
  edit_id: EDIT_ID,
  candidate_id: "candidate-one",
  sequence: 1,
  parent_edit_id: null,
  text: "作者改过的候选",
  character_count: 7,
  base_revision_id: REVISION,
  base_version: 1,
  created_at: "2026-10-24T00:00:00+00:00",
  source: "author",
};
const ready: WorkflowRun = {
  run_id: "run-one",
  chapter_id: chapterId,
  operation: "continue",
  status: "ready",
  base_revision_id: REVISION,
  base_version: 1,
  current_revision_id: REVISION,
  current_version: 1,
  instruction: "",
  selected_text: "",
  profile_id: model.id,
  model_snapshot: model,
  max_steps: 5,
  max_output_characters: 1500,
  generated_steps: 0,
  generated_characters: 0,
  context: {
    text: "甲乙丙丁",
    sha256: "a".repeat(64),
    manifest: {
      included_sources: ["current_chapter"],
      omitted_sources: [],
      truncated: false,
      character_count: 4,
      sources: [],
    },
  },
  candidates: [],
  last_error: null,
};
const candidate = {
  candidate_id: "candidate-one",
  sequence: 1,
  text: "文".repeat(240),
  model: "test-model",
  character_count: 240,
  status: "pending" as const,
  adopted_revision_id: null,
  adopted_version: null,
  latest_edit: null,
  edit_count: 0,
  adopted_edit_id: null,
};
const pending: WorkflowRun = {
  ...ready,
  generated_steps: 1,
  generated_characters: 240,
  candidates: [candidate],
};
const edited: WorkflowRun = {
  ...pending,
  candidates: [{ ...candidate, latest_edit: edit, edit_count: 1 }],
};

function workflowClient(runs: WorkflowRun[]): AIWorkflowClient {
  return {
    upgrade: vi.fn().mockResolvedValue(undefined),
    models: vi.fn().mockResolvedValue([model]),
    saveModel: vi.fn().mockResolvedValue(model),
    list: vi.fn().mockResolvedValue(runs),
    create: vi.fn(),
    action: vi.fn().mockResolvedValue(pending),
    candidate: vi.fn().mockResolvedValue({
      ...edited,
      candidates: [
        {
          ...edited.candidates[0],
          status: "adopted",
          adopted_edit_id: EDIT_ID,
        },
      ],
    }),
    saveEdit: vi.fn().mockResolvedValue(edited),
  };
}

function estimate(overrides: Partial<SendEstimate> = {}): SendEstimate {
  return {
    estimate_method: "utf8_bytes_upper_v1",
    profile_id: "default-local",
    input_characters: 100,
    input_tokens_upper: 340,
    output_tokens_upper: 2048,
    price: null,
    estimated_cost_upper: null,
    currency: null,
    budget_mode: "off",
    budget_currency: null,
    task_limit: null,
    monthly_limit: null,
    task_spent_upper: null,
    month_spent_upper: null,
    unpriced_attempts: 0,
    decision: "allowed",
    reasons: [],
    ...overrides,
  };
}
const price = {
  profile_id: "default-local",
  version: 1,
  currency: "CNY",
  input_per_million: "2.00",
  output_per_million: "8.00",
  created_at: "2026-10-24T00:00:00+00:00",
};
function budgetView(overrides: Partial<BudgetView> = {}): BudgetView {
  return {
    project_id: projectId,
    version: 0,
    mode: "off",
    currency: null,
    task_limit: null,
    monthly_limit: null,
    created_at: null,
    month_start: "2026-09-30T16:00:00+00:00",
    month: {
      currency: null,
      attempts: 0,
      settled: "0.00",
      pending: "0.00",
      upper: "0.00",
      unpriced_attempts: 0,
      other_currency_attempts: 0,
    },
    ...overrides,
  };
}
function fakeBudget(overrides: Partial<BudgetClient> = {}): BudgetClient {
  return {
    price: vi.fn().mockResolvedValue({
      profile_id: "default-local",
      current: null,
      history: [],
    } satisfies PriceState),
    savePrice: vi.fn().mockResolvedValue({
      profile_id: "default-local",
      current: price,
      history: [price],
    } satisfies PriceState),
    budget: vi.fn().mockResolvedValue(budgetView()),
    saveBudget: vi.fn().mockResolvedValue(
      budgetView({
        version: 1,
        mode: "strict",
        currency: "CNY",
        monthly_limit: "10.00",
      }),
    ),
    estimate: vi.fn().mockResolvedValue(estimate()),
    ...overrides,
  };
}
function apiFailure(code: string, status: number) {
  return Response.json(
    {
      error: {
        code,
        message: "server text",
        details: {},
        retryable: false,
        suggested_action: null,
      },
      request_id: "req_budget",
    },
    { status },
  );
}

describe("candidate edit contract", () => {
  it("parses author edits and rejects unsafe edit payloads", () => {
    const raw = JSON.parse(JSON.stringify(edited)) as Record<string, unknown>;
    expect(parseWorkflowRun(raw, chapterId).candidates[0].latest_edit).toEqual(
      edit,
    );
    const legacy = JSON.parse(JSON.stringify(pending)) as {
      candidates: Record<string, unknown>[];
    };
    for (const key of ["latest_edit", "edit_count", "adopted_edit_id"])
      delete legacy.candidates[0][key];
    expect(parseWorkflowRun(legacy, chapterId).candidates[0]).toMatchObject({
      latest_edit: null,
      edit_count: 0,
      adopted_edit_id: null,
    });
    for (const broken of [
      { ...edit, source: "model" },
      { ...edit, edit_id: "x" },
      { ...edit, candidate_id: "other" },
      { ...edit, parent_edit_id: "bad" },
      { ...edit, sequence: 51 },
    ])
      expect(() =>
        parseWorkflowRun(
          { ...edited, candidates: [{ ...candidate, latest_edit: broken }] },
          chapterId,
        ),
      ).toThrow();
    expect(() =>
      parseWorkflowRun(
        { ...pending, candidates: [{ ...candidate, adopted_edit_id: "nope" }] },
        chapterId,
      ),
    ).toThrow();
    expect(workflowFailureMessage("BudgetRefused")).toContain("严格预算");
    expect(visibleCharacters(" 甲 乙\n")).toBe(2);
    expect(editIsCurrent(edited.candidates[0], REVISION)).toBe(true);
    expect(editIsCurrent(candidate, REVISION)).toBe(false);
  });

  it("posts an edit with its parent and adopts with the chosen edit id", async () => {
    vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
      sessionId: "session",
      csrfToken: "csrf",
    } as never);
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json(edited, { status: 201 }));
    vi.stubGlobal("fetch", fetcher);
    await aiWorkflowClient.saveEdit(chapterId, "candidate-one", "改", null);
    const [url, options] = fetcher.mock.calls[0];
    expect(url).toBe(
      `/api/v1/chapters/${chapterId}/ai/candidates/candidate-one/edits`,
    );
    expect(JSON.parse(options?.body as string)).toEqual({
      text: "改",
      parent_edit_id: null,
    });
    fetcher.mockResolvedValue(Response.json(edited));
    await aiWorkflowClient.candidate(
      chapterId,
      "candidate-one",
      "adopt",
      "key-one",
      1,
      EDIT_ID,
    );
    expect(JSON.parse(fetcher.mock.calls[1][1]?.body as string)).toEqual({
      idempotency_key: "key-one",
      edit_id: EDIT_ID,
    });
    expect(() => aiWorkflowClient.saveEdit("bad/id", "c", "x", null)).toThrow();
  });
});

describe("CandidateEditor", () => {
  it("saves an author version without touching the manuscript and blocks adoption while dirty", async () => {
    const onSave = vi.fn().mockResolvedValue(true);
    const onDirty = vi.fn();
    render(
      <CandidateEditor
        candidate={candidate}
        savedRevisionId={REVISION}
        disabled={false}
        onSave={onSave}
        onDirtyChange={onDirty}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "编辑候选" }));
    const box = screen.getByLabelText("编辑候选文本");
    expect(box).toHaveValue(candidate.text);
    const save = screen.getByRole("button", { name: "保存修改" });
    expect(save).toBeDisabled();
    fireEvent.change(box, { target: { value: "   " } });
    expect(save).toBeDisabled();
    fireEvent.change(box, { target: { value: "字".repeat(3001) } });
    expect(save).toBeDisabled();
    fireEvent.change(box, { target: { value: "改好的文本" } });
    expect(onDirty).toHaveBeenLastCalledWith(true);
    expect(
      screen.getByText("有未保存的修改；保存或放弃后才能采用。"),
    ).toBeVisible();
    await act(async () => {
      fireEvent.click(save);
      await Promise.resolve();
    });
    expect(onSave).toHaveBeenCalledWith("改好的文本");
    expect(
      await screen.findByText("修改已保存为新版本，尚未写入正文。"),
    ).toBeVisible();
    expect(onDirty).toHaveBeenLastCalledWith(false);
  });

  it("keeps the editor open on a failed save and can discard unsaved changes", async () => {
    const onSave = vi.fn().mockResolvedValue(false);
    render(
      <CandidateEditor
        candidate={edited.candidates[0]}
        savedRevisionId={REVISION}
        disabled={false}
        onSave={onSave}
        onDirtyChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/已保存作者修改第 1 版/u)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "继续编辑修改" }));
    expect(screen.getByLabelText("编辑候选文本")).toHaveValue(edit.text);
    fireEvent.change(screen.getByLabelText("编辑候选文本"), {
      target: { value: "再改" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
      await Promise.resolve();
    });
    expect(screen.getByLabelText("编辑候选文本")).toHaveValue("再改");
    fireEvent.click(screen.getByRole("button", { name: "放弃未保存修改" }));
    expect(screen.queryByLabelText("编辑候选文本")).not.toBeInTheDocument();
  });

  it("asks to re-save an edit written against an older manuscript", async () => {
    const onSave = vi.fn().mockResolvedValue(true);
    render(
      <CandidateEditor
        candidate={edited.candidates[0]}
        savedRevisionId="chv_newer"
        disabled={false}
        onSave={onSave}
        onDirtyChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("较早的正文");
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "按当前正文重新保存修改" }),
      );
      await Promise.resolve();
    });
    expect(onSave).toHaveBeenCalledWith(edit.text);
  });
});

describe("AIWorkflowAssistant with edits and budgets", () => {
  function Harness({
    api,
    budget,
    revision = 1,
  }: {
    readonly api: AIWorkflowClient;
    readonly budget: BudgetClient;
    readonly revision?: number;
  }) {
    const writing = useChapterWriting(
      written("甲乙丙丁", revision),
      writingClient(),
    );
    return (
      <AIWorkflowAssistant
        chapterId={chapterId}
        projectId={projectId}
        writing={writing}
        selection={null}
        client={api}
        budgetClient={budget}
        usageClient={{ page: vi.fn() }}
      />
    );
  }

  it("adopts the newest author edit only on explicit confirmation", async () => {
    const api = workflowClient([edited]);
    render(<Harness api={api} budget={fakeBudget()} />);
    const adopt = await screen.findByRole("button", {
      name: "追加修改后的文本",
    });
    expect(api.candidate).not.toHaveBeenCalled();
    const comparison = screen.getByRole("region", { name: "候选插入位置" });
    expect(comparison).toHaveTextContent(edit.text);
    await act(async () => {
      fireEvent.click(adopt);
      await Promise.resolve();
    });
    await waitFor(() =>
      expect(api.candidate).toHaveBeenCalledWith(
        chapterId,
        "candidate-one",
        "adopt",
        expect.any(String),
        1,
        EDIT_ID,
      ),
    );
    expect(
      await screen.findByText(/已采纳（采用作者修改版本）/u),
    ).toBeInTheDocument();
  });

  it("can still adopt the original candidate and saves edits with the parent id", async () => {
    const api = workflowClient([edited]);
    const second: CandidateEdit = {
      ...edit,
      edit_id: EDIT_TWO,
      sequence: 2,
      parent_edit_id: EDIT_ID,
      text: "第二版",
      character_count: 3,
    };
    vi.mocked(api.saveEdit).mockResolvedValue({
      ...edited,
      candidates: [
        { ...edited.candidates[0], latest_edit: second, edit_count: 2 },
      ],
    });
    render(<Harness api={api} budget={fakeBudget()} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "继续编辑修改" }),
    );
    fireEvent.change(screen.getByLabelText("编辑候选文本"), {
      target: { value: "第二版" },
    });
    expect(
      screen.getByRole("button", { name: "追加修改后的文本" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "改为采用原始候选" }),
    ).toBeDisabled();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
      await Promise.resolve();
    });
    expect(api.saveEdit).toHaveBeenCalledWith(
      chapterId,
      "candidate-one",
      "第二版",
      EDIT_ID,
    );
    // 新版本保存后编辑器不重新挂载：保存成功提示仍可见，并显示第 2 版。
    expect(
      await screen.findByText("修改已保存为新版本，尚未写入正文。"),
    ).toBeVisible();
    expect(screen.getByText(/已保存作者修改第 2 版/u)).toBeVisible();
    await act(async () => {
      fireEvent.click(
        await screen.findByRole("button", { name: "改为采用原始候选" }),
      );
      await Promise.resolve();
    });
    await waitFor(() => expect(api.candidate).toHaveBeenCalled());
    expect(vi.mocked(api.candidate).mock.calls[0]).toHaveLength(5);
  });

  it("disables adopting a stale edit until it is re-saved", async () => {
    const api = workflowClient([edited]);
    render(<Harness api={api} budget={fakeBudget()} revision={2} />);
    expect(
      await screen.findByRole("button", { name: "追加修改后的文本" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "采纳并生成下一段" }),
    ).toBeDisabled();
  });

  it("blocks sending when the strict budget refuses and asks to confirm a warning", async () => {
    const refuse = fakeBudget({
      estimate: vi.fn().mockResolvedValue(
        estimate({
          decision: "refused",
          reasons: ["PRICE_MISSING"],
          budget_mode: "strict",
          budget_currency: "CNY",
          task_limit: "1.00",
          task_spent_upper: "0.00",
        }),
      ),
    });
    const api = workflowClient([ready]);
    const view = render(<Harness api={api} budget={refuse} />);
    expect(await screen.findByText(/按严格预算不会发送/u)).toBeVisible();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "确认发送并生成" }),
      ).toBeDisabled(),
    );
    view.unmount();
    const warn = fakeBudget({
      estimate: vi.fn().mockResolvedValue(
        estimate({
          decision: "warning",
          reasons: ["MONTHLY_LIMIT_EXCEEDED"],
          budget_mode: "warn",
          budget_currency: "CNY",
          monthly_limit: "1.00",
          month_spent_upper: "0.90",
          price,
          estimated_cost_upper: "0.02",
          currency: "CNY",
        }),
      ),
    });
    render(<Harness api={workflowClient([ready])} budget={warn} />);
    expect(await screen.findByText(/预算提示/u)).toBeVisible();
    const send = screen.getByRole("button", { name: "确认发送并生成" });
    await waitFor(() => expect(send).toBeDisabled());
    fireEvent.click(screen.getByRole("checkbox", { name: /仍要发送这一次/u }));
    expect(send).toBeEnabled();
    expect(screen.getByText(/本次最多约 0.02 CNY/u)).toBeVisible();
  });
});

describe("SendEstimatePanel", () => {
  it("shows the conservative bound and keeps sending possible when the estimate is unavailable", async () => {
    const gate = vi.fn();
    const failing = fakeBudget({
      estimate: vi.fn().mockRejectedValue(new Error("x")),
    });
    const view = render(
      <SendEstimatePanel
        chapterId={chapterId}
        runId="run-one"
        refreshKey="0"
        onGate={gate}
        client={failing}
      />,
    );
    expect(screen.getByText("正在计算发送前预估…")).toBeVisible();
    expect(await screen.findByText(/暂时无法读取发送前预估/u)).toBeVisible();
    expect(gate).toHaveBeenLastCalledWith(true, "");
    view.unmount();
    render(
      <SendEstimatePanel
        chapterId={chapterId}
        runId="run-one"
        refreshKey="1"
        onGate={gate}
        client={fakeBudget({
          estimate: vi.fn().mockResolvedValue(
            estimate({
              budget_mode: "strict",
              budget_currency: "CNY",
              monthly_limit: "5.00",
              month_spent_upper: "1.00",
              unpriced_attempts: 2,
            }),
          ),
        })}
      />,
    );
    expect(await screen.findByText(/输入不超过 340/u)).toBeVisible();
    expect(screen.getByText("当前模型未填写价格，不估算金额。")).toBeVisible();
    expect(screen.getByText(/另有 2 次请求发生在填写价格前/u)).toBeVisible();
    render(
      <SendEstimatePanel
        chapterId={chapterId}
        runId="run-two"
        refreshKey="1"
        onGate={gate}
        client={fakeBudget()}
      />,
    );
    expect(await screen.findByText("本书未设预算。")).toBeVisible();
  });
});

describe("BudgetSettingsPanel", () => {
  function openPanel() {
    const details = screen.getByText("费用与预算").closest("details")!;
    act(() => {
      details.open = true;
      details.dispatchEvent(new Event("toggle"));
    });
  }

  it("保存可选缓存单价并允许清空，空值回退普通输入价", async () => {
    const client = fakeBudget();
    render(
      <BudgetSettingsPanel
        projectId={projectId}
        profileId="default-local"
        profileName="测试模型"
        client={client}
      />,
    );
    openPanel();
    await screen.findByText(/价格未填写。本应用不预置价格/u);
    fireEvent.change(screen.getByLabelText("币种（如 CNY、USD）"), {
      target: { value: "CNY" },
    });
    fireEvent.change(screen.getByLabelText("输入价格（每百万 token）"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("输出价格（每百万 token）"), {
      target: { value: "8" },
    });
    fireEvent.change(
      screen.getByLabelText("缓存读取价格（每百万 token，可选）"),
      { target: { value: "0.5" } },
    );
    fireEvent.change(
      screen.getByLabelText("缓存写入价格（每百万 token，可选）"),
      { target: { value: "3" } },
    );
    fireEvent.change(
      screen.getByLabelText("缓存写入价格（每百万 token，可选）"),
      { target: { value: "" } },
    );
    fireEvent.click(
      within(screen.getByRole("form", { name: "模型价格" })).getByRole(
        "button",
        { name: "保存价格" },
      ),
    );
    await waitFor(() =>
      expect(client.savePrice).toHaveBeenCalledWith("default-local", {
        expected_version: 0,
        currency: "CNY",
        input_per_million: "2",
        output_per_million: "8",
        cached_input_per_million: "0.5",
        cache_write_per_million: null,
      }),
    );
    expect(screen.getByText(/留空按普通输入单价计算/u)).toBeVisible();
  });

  it("loads lazily, validates and saves an author-entered price and budget", async () => {
    const client = fakeBudget();
    render(
      <BudgetSettingsPanel
        projectId={projectId}
        profileId="default-local"
        profileName="测试模型"
        client={client}
      />,
    );
    expect(client.price).not.toHaveBeenCalled();
    openPanel();
    expect(
      await screen.findByText(/价格未填写。本应用不预置价格/u),
    ).toBeVisible();
    const priceForm = screen.getByRole("form", { name: "模型价格" });
    fireEvent.click(
      within(priceForm).getByRole("button", { name: "保存价格" }),
    );
    expect(within(priceForm).getByRole("alert")).toHaveTextContent(
      "3 位大写币种",
    );
    fireEvent.change(screen.getByLabelText("币种（如 CNY、USD）"), {
      target: { value: "cny" },
    });
    fireEvent.change(screen.getByLabelText("输入价格（每百万 token）"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("输出价格（每百万 token）"), {
      target: { value: "8" },
    });
    await act(async () => {
      fireEvent.click(
        within(priceForm).getByRole("button", { name: "保存价格" }),
      );
      await Promise.resolve();
    });
    expect(client.savePrice).toHaveBeenCalledWith("default-local", {
      expected_version: 0,
      currency: "CNY",
      input_per_million: "2",
      output_per_million: "8",
    });
    expect(
      await screen.findByText(/当前价格：每百万 token 输入 2.00/u),
    ).toBeVisible();
    const budgetForm = screen.getByRole("form", { name: "本书预算" });
    expect(within(budgetForm).getByText(/已发出 0 次请求/u)).toBeVisible();
    fireEvent.change(screen.getByLabelText("预算方式"), {
      target: { value: "strict" },
    });
    fireEvent.click(
      within(budgetForm).getByRole("button", { name: "保存预算" }),
    );
    expect(within(budgetForm).getByRole("alert")).toHaveTextContent(
      "至少一项上限",
    );
    fireEvent.change(screen.getByLabelText("预算币种"), {
      target: { value: "CNY" },
    });
    fireEvent.change(screen.getByLabelText("本书每月上限（可空）"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("单任务上限（可空）"), {
      target: { value: "" },
    });
    await act(async () => {
      fireEvent.click(
        within(budgetForm).getByRole("button", { name: "保存预算" }),
      );
      await Promise.resolve();
    });
    expect(client.saveBudget).toHaveBeenCalledWith(projectId, {
      expected_version: 0,
      mode: "strict",
      currency: "CNY",
      task_limit: null,
      monthly_limit: "10",
    });
    expect(await screen.findByText("预算已保存为新版本。")).toBeVisible();
  });

  it("explains failures and a missing model, and summarizes unknown spend", async () => {
    const client = fakeBudget({
      budget: vi.fn().mockResolvedValue(
        budgetView({
          version: 2,
          mode: "warn",
          currency: "CNY",
          monthly_limit: "5.00",
          month: {
            currency: "CNY",
            attempts: 3,
            settled: "0.10",
            pending: "0.20",
            upper: "0.30",
            unpriced_attempts: 1,
            other_currency_attempts: 1,
          },
        }),
      ),
      saveBudget: vi
        .fn()
        .mockRejectedValue(
          new BudgetError("设置已在其他窗口修改", "BUDGET_VERSION_CONFLICT"),
        ),
      price: vi.fn().mockRejectedValue(new Error("boom")),
    });
    render(
      <BudgetSettingsPanel
        projectId={projectId}
        profileId={null}
        profileName=""
        client={client}
      />,
    );
    openPanel();
    expect(screen.getByText("添加并选择模型后可填写价格。")).toBeVisible();
    expect(await screen.findByText(/按保守上限计 0.20 CNY/u)).toBeVisible();
    expect(screen.getByText(/1 次使用其他币种价格/u)).toBeVisible();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "保存预算" }));
      await Promise.resolve();
    });
    expect(await screen.findByText("设置已在其他窗口修改")).toBeVisible();
    fireEvent.change(screen.getByLabelText("预算方式"), {
      target: { value: "off" },
    });
    expect(screen.queryByLabelText("预算币种")).not.toBeInTheDocument();
  });

  it("reports a failed price read and an unexpected save error", async () => {
    const client = fakeBudget({
      price: vi.fn().mockRejectedValue(new Error("boom")),
      budget: vi.fn().mockRejectedValue(new BudgetError("预算暂不可用")),
    });
    render(
      <BudgetSettingsPanel
        projectId={projectId}
        profileId="default-local"
        profileName="测试模型"
        client={client}
      />,
    );
    openPanel();
    expect(
      await screen.findByText("操作未完成，请稍后重试；写作不受影响。"),
    ).toBeVisible();
    expect(await screen.findByText("预算暂不可用")).toBeVisible();
  });
});

describe("budget API", () => {
  it("validates amounts, currencies and payloads", () => {
    expect(isAmount("0")).toBe(true);
    expect(isAmount("1.123456")).toBe(true);
    expect(isAmount("01")).toBe(false);
    expect(isCurrency("CNY")).toBe(true);
    expect(isCurrency("cny")).toBe(false);
    expect(
      parseEstimate(estimate({ reasons: ["PRICE_MISSING"] })).reasons,
    ).toEqual(["PRICE_MISSING"]);
    expect(() =>
      parseEstimate({ ...estimate(), estimate_method: "x" }),
    ).toThrow(BudgetError);
    expect(() => parseEstimate({ ...estimate(), reasons: ["NOPE"] })).toThrow(
      BudgetError,
    );
    expect(() =>
      parseEstimate({ ...estimate(), input_tokens_upper: -1 }),
    ).toThrow(BudgetError);
    expect(() =>
      parseEstimate({ ...estimate(), price: { ...price, currency: "x" } }),
    ).toThrow();
    expect(() => parseEstimate(null)).toThrow(BudgetError);
    expect(() => parseEstimate({ ...estimate(), profile_id: 3 })).toThrow(
      BudgetError,
    );
    expect(() =>
      parseEstimate({ ...estimate(), estimated_cost_upper: "1e3" }),
    ).toThrow(BudgetError);
    expect(parseBudget(budgetView(), projectId).mode).toBe("off");
    expect(() => parseBudget(budgetView(), "prj_other")).toThrow(BudgetError);
    expect(() =>
      parsePriceState({ profile_id: "x", current: null, history: [] }, "y"),
    ).toThrow();
  });

  it("reads and writes through the local API with CSRF proof and maps errors", async () => {
    vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
      sessionId: "session",
      csrfToken: "csrf",
    } as never);
    const fetcher = vi.fn<typeof fetch>();
    const respond = (value: unknown) =>
      fetcher.mockImplementation(() => Promise.resolve(Response.json(value)));
    const fail = (code: string, status: number) =>
      fetcher.mockImplementation(() =>
        Promise.resolve(apiFailure(code, status)),
      );
    respond({ profile_id: "default-local", current: price, history: [price] });
    vi.stubGlobal("fetch", fetcher);
    await expect(budgetClient.price("default-local")).resolves.toMatchObject({
      current: { currency: "CNY" },
    });
    await budgetClient.savePrice("default-local", {
      expected_version: 1,
      currency: "CNY",
      input_per_million: "1",
      output_per_million: "1",
    });
    expect(fetcher.mock.calls[1][1]?.method).toBe("PUT");
    expect(
      new Headers(fetcher.mock.calls[1][1]?.headers).get("X-CSRF-Token"),
    ).toBe("csrf");
    respond(budgetView());
    await expect(budgetClient.budget(projectId)).resolves.toMatchObject({
      mode: "off",
    });
    await budgetClient.saveBudget(projectId, {
      expected_version: 0,
      mode: "off",
      currency: null,
      task_limit: null,
      monthly_limit: null,
    });
    respond(estimate());
    await expect(
      budgetClient.estimate(chapterId, "run-one"),
    ).resolves.toMatchObject({
      decision: "allowed",
    });
    expect(fetcher.mock.calls.at(-1)?.[0]).toBe(
      `/api/v1/chapters/${chapterId}/ai/runs/run-one/estimate`,
    );
    fail("BUDGET_VERSION_CONFLICT", 409);
    await expect(budgetClient.budget(projectId)).rejects.toMatchObject({
      code: "BUDGET_VERSION_CONFLICT",
    });
    fail("SOMETHING_ELSE", 500);
    await expect(budgetClient.budget(projectId)).rejects.toThrow(
      /预算或价格操作未完成/u,
    );
    const clear = vi.spyOn(securitySession, "clear");
    fail("FORBIDDEN", 403);
    await expect(budgetClient.budget(projectId)).rejects.toBeInstanceOf(
      BudgetError,
    );
    expect(clear).toHaveBeenCalled();
    respond({ nope: true });
    await expect(budgetClient.budget(projectId)).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
    fetcher.mockRejectedValue(new TypeError("offline"));
    await expect(budgetClient.budget(projectId)).rejects.toMatchObject({
      code: "NETWORK_ERROR",
    });
    await expect(budgetClient.budget("bad/id")).rejects.toBeInstanceOf(
      BudgetError,
    );
  });
});

function draft(overrides: Partial<LocalDraft> = {}): LocalDraft {
  return {
    v: 1,
    instance: INSTANCE,
    projectId,
    chapterId,
    sessionId: "session-old",
    chapterTitle: "第一章",
    baseRevisionId: REVISION,
    baseVersion: 1,
    content: "本机草稿正文",
    updatedAt: "2026-10-24T01:02:03.000Z",
    ...overrides,
  };
}

describe("local drafts storage", () => {
  it("isolates drafts by instance, novel, chapter and session and skips broken entries", () => {
    saveDraft(draft());
    saveDraft(
      draft({
        sessionId: "session-two",
        updatedAt: "2026-10-25T00:00:00.000Z",
      }),
    );
    saveDraft(draft({ chapterId: "chp_other" }));
    saveDraft(draft({ projectId: "prj_other" }));
    window.localStorage.setItem(`${DRAFT_PREFIX}broken`, "{nope");
    window.localStorage.setItem(
      `${DRAFT_PREFIX}x:y:z:w`,
      JSON.stringify(draft()),
    );
    window.localStorage.setItem("unrelated", "1");
    expect(
      listDrafts(projectId, chapterId).map((item) => item.draft.sessionId),
    ).toEqual(["session-two", "session-old"]);
    expect(listDrafts(projectId)).toHaveLength(3);
    removeDraft(draftKey(draft()));
    expect(listDrafts(projectId, chapterId)).toHaveLength(1);
    expect(window.localStorage.getItem(`${DRAFT_PREFIX}broken`)).toBe("{nope");
    expect(draftFilename('a/b:c*"', "2026-10-24T01:02:03Z")).toBe(
      "a_b_c__-本机草稿-20261024010203.txt",
    );
    expect(draftFilename("", "x")).toBe("章节-本机草稿-.txt");
  });

  it("reports a full or unavailable store instead of claiming a draft exists", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    expect(() => saveDraft(draft())).toThrow(DraftStorageError);
    vi.restoreAllMocks();
    const getter = vi
      .spyOn(window, "localStorage", "get")
      .mockImplementation(() => {
        throw new DOMException("denied", "SecurityError");
      });
    expect(() => saveDraft(draft())).toThrow(DraftStorageError);
    expect(listDrafts(projectId)).toEqual([]);
    expect(() => removeDraft("x")).not.toThrow();
    getter.mockRestore();
  });

  it("downloads plain text and reads the storage instance safely", async () => {
    const create = vi.fn(() => "blob:local");
    const revoke = vi.fn();
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }),
    );
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    downloadText("x.txt", "正文");
    expect(click).toHaveBeenCalled();
    expect(revoke).toHaveBeenCalledWith("blob:local");
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(Response.json({ storage_instance_id: INSTANCE }));
    vi.stubGlobal("fetch", fetcher);
    await expect(fetchStorageInstance()).resolves.toBe(INSTANCE);
    fetcher.mockResolvedValue(Response.json({ storage_instance_id: "../x" }));
    await expect(fetchStorageInstance()).rejects.toBeTruthy();
    fetcher.mockResolvedValue(Response.json(null));
    await expect(fetchStorageInstance()).rejects.toBeTruthy();
  });
});

describe("useLocalDraft", () => {
  const source = {
    projectId,
    chapterId,
    chapterTitle: "第一章",
    content: "已保存",
    savedContent: "已保存",
    savedRevisionId: REVISION,
    savedVersion: 1,
  };

  it("saves unsaved text after a bounded delay and clears it once the server holds it", async () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      (props) => useLocalDraft(props, () => Promise.resolve(INSTANCE)),
      {
        initialProps: source,
      },
    );
    await act(() => Promise.resolve());
    expect(result.current.instance).toEqual({ status: "ready", id: INSTANCE });
    rerender({ ...source, content: "未保存的新字" });
    expect(listDrafts(projectId, chapterId)).toHaveLength(0);
    await act(() => vi.advanceTimersByTimeAsync(800));
    const [saved] = listDrafts(projectId, chapterId);
    expect(saved.draft).toMatchObject({
      content: "未保存的新字",
      baseVersion: 1,
    });
    rerender({
      ...source,
      content: "未保存的新字",
      savedContent: "未保存的新字",
    });
    expect(listDrafts(projectId, chapterId)).toHaveLength(0);
  });

  it("offers other sessions' differing drafts, drops identical ones and counts foreign roots", async () => {
    saveDraft(draft({ content: "不同的草稿" }));
    saveDraft(draft({ sessionId: "same", content: "已保存" }));
    saveDraft(draft({ sessionId: "foreign", instance: "b".repeat(32) }));
    const { result } = renderHook(() =>
      useLocalDraft(source, () => Promise.resolve(INSTANCE)),
    );
    await waitFor(() => expect(result.current.recoverable).toHaveLength(1));
    expect(result.current.foreign).toBe(1);
    expect(listDrafts(projectId, chapterId)).toHaveLength(2); // identical one cleaned
    act(() => result.current.dismiss(result.current.recoverable[0].key));
    expect(result.current.recoverable).toHaveLength(0);
    expect(listDrafts(projectId, chapterId)).toHaveLength(2); // dismiss keeps it stored
  });

  it("discards on request, surfaces storage failures and handles an unavailable instance", async () => {
    vi.useFakeTimers();
    saveDraft(draft({ content: "不同的草稿" }));
    const { result, rerender } = renderHook(
      (props) => useLocalDraft(props, () => Promise.resolve(INSTANCE)),
      {
        initialProps: source,
      },
    );
    await act(() => Promise.resolve());
    await act(() => Promise.resolve());
    expect(result.current.recoverable).toHaveLength(1);
    act(() => result.current.discard(result.current.recoverable[0].key));
    expect(listDrafts(projectId, chapterId)).toHaveLength(0);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    rerender({ ...source, content: "新字" });
    await act(() => vi.advanceTimersByTimeAsync(800));
    expect(result.current.storageError).toBe(true);
    rerender({ ...source });
    expect(result.current.storageError).toBe(false);
    const unavailable = renderHook(() =>
      useLocalDraft(source, () => Promise.reject(new Error("x"))),
    );
    await act(() => Promise.resolve());
    await act(() => Promise.resolve());
    expect(unavailable.result.current.instance).toEqual({
      status: "unavailable",
    });
  });
});

describe("LocalDraftRecovery and LocalDraftManager", () => {
  it("compares, restores, downloads and discards a recoverable draft", () => {
    const stored = {
      key: draftKey(draft()),
      draft: draft({ baseRevisionId: "chv_old" }),
    };
    const onRestore = vi.fn();
    const onDiscard = vi.fn();
    const onDismiss = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    vi.stubGlobal(
      "URL",
      Object.assign(URL, {
        createObjectURL: () => "blob:x",
        revokeObjectURL: () => undefined,
      }),
    );
    const view = render(
      <LocalDraftRecovery
        instance={{ status: "ready", id: INSTANCE }}
        storageError
        recoverable={[stored]}
        foreign={2}
        savedContent="服务器正文"
        savedRevisionId={REVISION}
        canRestore
        onRestore={onRestore}
        onDiscard={onDiscard}
        onDismiss={onDismiss}
      />,
    );
    expect(screen.getByText(/本机草稿未能保存/u)).toBeVisible();
    expect(screen.getByText(/另有 2 份来自其他数据根/u)).toBeVisible();
    expect(screen.getByText(/基于较早的服务器版本/u)).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "比较草稿与已保存正文" }),
    );
    expect(
      screen.getByRole("region", { name: "本机草稿与已保存正文对照" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "收起比较" }));
    fireEvent.click(screen.getByRole("button", { name: "下载本地副本" }));
    expect(click).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "丢弃此草稿" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    fireEvent.click(screen.getByRole("button", { name: "丢弃此草稿" }));
    fireEvent.click(screen.getByRole("button", { name: "确认丢弃此草稿" }));
    expect(onDiscard).toHaveBeenCalledWith(stored.key);
    fireEvent.click(screen.getByRole("button", { name: "恢复到编辑区" }));
    expect(onRestore).toHaveBeenCalledWith("本机草稿正文");
    expect(onDismiss).toHaveBeenCalledWith(stored.key);
    view.rerender(
      <LocalDraftRecovery
        instance={{ status: "unavailable" }}
        storageError={false}
        recoverable={[{ ...stored, draft: draft() }]}
        foreign={0}
        savedContent="服务器正文"
        savedRevisionId={REVISION}
        canRestore={false}
        onRestore={onRestore}
        onDiscard={onDiscard}
        onDismiss={onDismiss}
      />,
    );
    expect(screen.getByText(/暂时无法核对本机数据根/u)).toBeVisible();
    expect(screen.getByText(/它基于当前服务器版本/u)).toBeVisible();
    expect(screen.getByRole("button", { name: "恢复到编辑区" })).toBeDisabled();
  });

  it("lists a novel's drafts with their data root and clears only on confirmation", async () => {
    saveDraft(draft());
    saveDraft(
      draft({
        sessionId: "foreign",
        instance: "b".repeat(32),
        chapterTitle: "",
      }),
    );
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    vi.stubGlobal(
      "URL",
      Object.assign(URL, {
        createObjectURL: () => "blob:x",
        revokeObjectURL: () => undefined,
      }),
    );
    render(
      <LocalDraftManager
        projectId={projectId}
        chapterTitles={new Map([[chapterId, "新的章名"]])}
        loadInstance={() => Promise.resolve(INSTANCE)}
      />,
    );
    expect(screen.getByText("本机草稿（2）")).toBeVisible();
    expect(await screen.findByText(/本数据根/u)).toBeInTheDocument();
    expect(screen.getByText(/其他数据根（不会自动套用）/u)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "下载" })[0]);
    expect(click).toHaveBeenCalled();
    fireEvent.click(screen.getAllByRole("button", { name: "清理" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    fireEvent.click(screen.getAllByRole("button", { name: "清理" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "确认清理" }));
    expect(listDrafts(projectId)).toHaveLength(1);
    expect(screen.getByText("本机草稿（1）")).toBeInTheDocument();
  });

  it("shows an empty manager", () => {
    render(
      <LocalDraftManager
        projectId={projectId}
        chapterTitles={new Map()}
        loadInstance={() => Promise.reject(new Error("x"))}
      />,
    );
    expect(screen.getByText("这本小说当前没有本机草稿。")).toBeInTheDocument();
  });
});

describe("conflict resolution", () => {
  it("keeps a local copy, compares and replaces either side only after confirmation", async () => {
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    vi.stubGlobal(
      "URL",
      Object.assign(URL, {
        createObjectURL: () => "blob:x",
        revokeObjectURL: () => undefined,
      }),
    );
    const loadServer = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce("服务器新版本");
    const onKeepLocal = vi.fn().mockResolvedValue(true);
    const onReload = vi.fn();
    render(
      <ConflictResolution
        chapterTitle="第一章"
        localContent="本地版本"
        disabled={false}
        loadServer={loadServer}
        onKeepLocal={onKeepLocal}
        onReloadServer={onReload}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "下载本地副本" }));
    expect(click).toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "比较服务器版本" }));
      await Promise.resolve();
    });
    expect(await screen.findByText(/服务器版本暂未读取/u)).toBeVisible();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "比较服务器版本" }));
      await Promise.resolve();
    });
    expect(
      await screen.findByRole("region", { name: "服务器版本与本地正文对照" }),
    ).toBeVisible();
    const keep = screen.getByRole("button", { name: "保留本地正文并保存" });
    expect(keep).toBeDisabled();
    fireEvent.click(
      screen.getByRole("checkbox", { name: /确认用本地正文替换/u }),
    );
    fireEvent.click(keep);
    expect(onKeepLocal).toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("checkbox", { name: /确认丢弃本地正文/u }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "丢弃本地正文并重新加载服务器版本" }),
    );
    expect(onReload).toHaveBeenCalled();
  });

  it("keepLocal adopts the server version as the new precondition and keeps local text", async () => {
    vi.useFakeTimers();
    const update = vi
      .fn()
      .mockRejectedValueOnce(structureError("conflict", "safe"))
      .mockImplementation((_c, _p, content: string, etag: string) =>
        Promise.resolve(written(content, Number(etag.slice(1, -1)) + 1)),
      );
    const get = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(written("服务器新版本", 2));
    const { result } = renderHook(() =>
      useChapterWriting(
        written("旧", 1),
        writingClient({ getChapterContent: get, updateChapterContent: update }),
      ),
    );
    await expect(result.current.keepLocal()).resolves.toBe(false); // not in conflict
    act(() => result.current.edit("我的本地版本"));
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(result.current.state.status).toBe("conflict");
    let kept = true;
    await act(async () => {
      kept = await result.current.keepLocal();
    });
    expect(kept).toBe(false);
    expect(result.current.state.status).toBe("conflict");
    await act(async () => {
      kept = await result.current.keepLocal();
    });
    expect(kept).toBe(true);
    expect(result.current.state.content).toBe("我的本地版本");
    expect(result.current.state.snapshot.version).toBe(2);
    expect(result.current.state.status).toBe("dirty");
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(update).toHaveBeenLastCalledWith(
      chapterId,
      projectId,
      "我的本地版本",
      '"2"',
      expect.anything(),
    );
    expect(result.current.state.status).toBe("saved");
  });

  it("renders an approximate comparison for very different texts", () => {
    render(
      <VersionComparison
        label="对照"
        leftLabel="甲"
        rightLabel="乙"
        left={"a ".repeat(15_000)}
        right={"b ".repeat(15_000)}
      />,
    );
    expect(screen.getByText(/差异较大，未逐字标记/u)).toBeVisible();
  });
});

it("opens the budget destination directly without reading model prices or sending", async () => {
  const client = fakeBudget();
  render(
    <BudgetSettingsPanel
      projectId={projectId}
      profileId={null}
      profileName=""
      initiallyOpen
      client={client}
    />,
  );
  await waitFor(() => expect(client.budget).toHaveBeenCalledOnce());
  expect(document.querySelector("details.budget-settings")).toHaveAttribute(
    "open",
  );
  expect(client.price).not.toHaveBeenCalled();
  expect(client.estimate).not.toHaveBeenCalled();
});
