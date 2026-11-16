import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ModelProfile } from "../../frontend/src/features/novel-structure/api/ai-workflow";
import type {
  MethodClient,
  Trial,
} from "../../frontend/src/features/novel-structure/api/method-validation";
import type {
  ChapterPlan,
  RuleRevision,
} from "../../frontend/src/features/novel-structure/api/writing-preparation";
import type { SendEstimate } from "../../frontend/src/features/usage/api/budget";
import { MethodValidation } from "../../frontend/src/features/novel-structure/components/MethodValidation";

const rule: RuleRevision = {
  id: "rule-v1",
  rule_id: "rule",
  project_id: "project",
  version: 1,
  title: "方法",
  reference_id: null,
  rules: [{ name: "动作", instruction: "行动有后果", applies_to: "冲突" }],
  created_at: "now",
};
const plan: ChapterPlan = {
  chapter_id: "chapter",
  project_id: "project",
  version: 1,
  revision_id: "plan",
  updated_at: "now",
  memory_focuses: ["焦点"],
  target_characters: 300,
  chapter_goal: "目标",
  conflict: "冲突",
  continuity_notes: "",
  scenes: [
    { id: "scene", title: "场景", setting: "", character_ids: [], beats: [] },
  ],
  include_story_bible: false,
  writing_rule_revision_ids: [rule.id],
};
const profile: ModelProfile = {
  id: "profile",
  name: "假模型",
  kind: "local",
  base_url: "http://127.0.0.1:1",
  model: "fake",
  max_output_tokens: 100,
  has_key: false,
};
const candidate = { status: "ready", text: null, error: null } as const;
const ready: Trial = {
  id: "trial",
  version: 1,
  chapter_id: "chapter",
  manuscript_revision_id: "revision",
  plan_revision_id: "plan",
  rule_version_id: "rule-v1",
  rule_index: 0,
  scene: "场景",
  plan: "规划",
  manuscript: "甲😀乙",
  method: "行动有后果",
  model_name: "假模型",
  model_kind: "local",
  a: candidate,
  b: candidate,
  complete: false,
};
const estimate: SendEstimate = {
  estimate_method: "utf8_bytes_upper_v1",
  profile_id: "profile",
  input_characters: 10,
  input_tokens_upper: 100,
  output_tokens_upper: 100,
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
};
function fakeClient() {
  const first: Trial = {
    ...ready,
    version: 3,
    a: { status: "completed", text: "候选一", error: null },
  };
  const second: Trial = {
    ...first,
    version: 5,
    b: { status: "completed", text: "候选二", error: null },
    complete: true,
  };
  const rating = {
    focus: 3,
    continuity: 3,
    subtext: 3,
    persistence: 3,
    originality: 3,
    reason: "",
  };
  return {
    listTrials: vi.fn().mockResolvedValue([]),
    annotations: vi.fn().mockResolvedValue([]),
    templates: vi.fn().mockResolvedValue([]),
    prepare: vi.fn().mockResolvedValue(ready),
    estimate: vi.fn().mockResolvedValue(estimate),
    send: vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(second),
    rate: vi.fn().mockResolvedValue({
      ...second,
      version: 6,
      a_uses_rule: true,
      a_score: rating,
      b_score: rating,
    }),
    annotate: vi.fn().mockResolvedValue("annotation"),
    createTemplate: vi.fn(),
    copyTemplate: vi.fn(),
    deleteTemplate: vi.fn(),
    get: vi.fn(),
  };
}
function open(
  client: ReturnType<typeof fakeClient>,
  rules: readonly RuleRevision[] = [rule],
) {
  const result = render(
    <MethodValidation
      projectId="project"
      chapterId="chapter"
      manuscriptRevision="revision"
      savedContent="甲😀乙"
      plan={plan}
      rules={rules}
      profile={profile}
      onRulesChanged={vi.fn()}
      client={client as unknown as MethodClient}
    />,
  );
  const details = screen.getByText("写作方法验证与复用").closest("details")!;
  act(() => {
    details.open = true;
    details.dispatchEvent(new Event("toggle"));
  });
  return result;
}
async function chooseMethod() {
  fireEvent.change(await screen.findByLabelText("规则版本"), {
    target: { value: "rule-v1" },
  });
}

describe("作者方法验证", () => {
  it("场景标签只预选已确认的相关方法，不发送模型请求", async () => {
    const client = fakeClient();
    open(client, [
      {
        ...rule,
        rules: [{ ...rule.rules[0], scene_tags: ["场景"], priority: 4 }],
      },
    ]);
    fireEvent.change(await screen.findByLabelText("已保存场景"), {
      target: { value: "scene" },
    });
    expect(screen.getByLabelText("规则版本")).toHaveValue("rule-v1");
    expect(screen.getByText(/按场景标签建议的方法/u)).toBeVisible();
    expect(client.send).not.toHaveBeenCalled();
  });
  it("准备时零发送，两次各自确认，评分后才揭示并保留候选", async () => {
    const client = fakeClient();
    open(client);
    await chooseMethod();
    fireEvent.change(screen.getByLabelText("已保存场景"), {
      target: { value: "scene" },
    });
    fireEvent.click(screen.getByRole("button", { name: "准备对照（不发送）" }));
    expect(await screen.findByText(/对照已准备/u)).toBeVisible();
    expect(client.send).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "确认发送候选 A" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "确认发送候选 A" }));
    expect(await screen.findByText("候选一")).toBeVisible();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "确认发送候选 B" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "确认发送候选 B" }));
    expect(await screen.findByText("候选二")).toBeVisible();
    expect(screen.queryByText(/本次方法用于候选/u)).not.toBeInTheDocument();
    for (const slot of ["A", "B"])
      for (const label of [
        "焦点清晰度",
        "行动连续性",
        "对话潜台词",
        "场景停留",
        "原创表达",
      ])
        fireEvent.change(screen.getByLabelText(`${slot} ${label}`), {
          target: { value: "3" },
        });
    fireEvent.click(screen.getByRole("button", { name: "保存评分并揭示方法" }));
    expect(await screen.findByText(/本次方法用于候选 A/u)).toBeVisible();
    expect(client.send).toHaveBeenCalledTimes(2);
    expect(client.rate).toHaveBeenCalledTimes(1);
  });

  it("选中包含 emoji 的已保存正文时传递 Unicode 字符偏移", async () => {
    const client = fakeClient();
    open(client);
    await chooseMethod();
    const field = screen.getByLabelText("选择已保存正文中的片段");
    if (!(field instanceof HTMLTextAreaElement))
      throw new Error("expected textarea");
    field.setSelectionRange(1, 3);
    fireEvent.select(field);
    fireEvent.change(screen.getByLabelText("判断依据"), {
      target: { value: "这里体现了动作" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存标注" }));
    await waitFor(() =>
      expect(client.annotate).toHaveBeenCalledWith(
        "project",
        expect.objectContaining({
          start: 1,
          end: 2,
          manuscript_revision_id: "revision",
          rule_version_id: "rule-v1",
        }),
      ),
    );
    expect(client.send).not.toHaveBeenCalled();
  });

  it("严格预算不允许发送，且模板必须作者填写并确认", async () => {
    const client = fakeClient();
    client.estimate.mockResolvedValue({
      ...estimate,
      budget_mode: "strict",
      decision: "refused",
      reasons: ["TASK_LIMIT_EXCEEDED"],
    });
    open(client);
    await chooseMethod();
    fireEvent.change(screen.getByLabelText("已保存场景"), {
      target: { value: "scene" },
    });
    fireEvent.click(screen.getByRole("button", { name: "准备对照（不发送）" }));
    expect(await screen.findByText(/严格预算阻止发送/u)).toBeVisible();
    expect(
      screen.getByRole("button", { name: "确认发送候选 A" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "保存个人模板" })).toBeDisabled();
    expect(
      within(screen.getByLabelText("写作方法验证")).getByLabelText(
        "可复用方法",
      ),
    ).toHaveValue("");
    expect(client.send).not.toHaveBeenCalled();
  });

  it("提示预算必须逐次确认，模板只保存作者填写的方法", async () => {
    const client = fakeClient();
    client.estimate.mockResolvedValue({
      ...estimate,
      budget_mode: "warn",
      decision: "warning",
      reasons: ["TASK_LIMIT_EXCEEDED"],
    });
    client.createTemplate.mockResolvedValue({ id: "template" });
    open(client);
    await chooseMethod();
    fireEvent.change(screen.getByLabelText("已保存场景"), {
      target: { value: "scene" },
    });
    fireEvent.click(screen.getByRole("button", { name: "准备对照（不发送）" }));
    const warning =
      await screen.findByLabelText("我已知晓预算提醒，仍发送一次");
    expect(
      screen.getByRole("button", { name: "确认发送候选 A" }),
    ).toBeDisabled();
    fireEvent.click(warning);
    fireEvent.click(screen.getByRole("button", { name: "确认发送候选 A" }));
    expect(await screen.findByText("候选一")).toBeVisible();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "确认发送候选 B" }),
      ).toBeDisabled(),
    );
    fireEvent.change(screen.getByLabelText("模板名称"), {
      target: { value: "复用方法" },
    });
    fireEvent.change(screen.getByLabelText("可复用方法"), {
      target: { value: "每个动作带来变化" },
    });
    fireEvent.change(screen.getByLabelText("模板适用条件"), {
      target: { value: "冲突场景" },
    });
    fireEvent.click(
      screen.getByLabelText("我已检查模板不含来源正文、人物名及其他小说情节"),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存个人模板" }));
    await waitFor(() =>
      expect(client.createTemplate).toHaveBeenCalledWith(
        "project",
        expect.objectContaining({
          source_rule_version_id: "rule-v1",
          source_rule_index: 0,
          instruction: "每个动作带来变化",
          confirmed: true,
        }),
      ),
    );
    expect(client.send).toHaveBeenCalledTimes(1);
  });
});
