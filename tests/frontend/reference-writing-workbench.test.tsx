import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ReferenceWritingWorkbench } from "../../frontend/src/features/novel-structure/components/ReferenceWritingWorkbench";
import { AIWritingError } from "../../frontend/src/features/novel-structure/api/ai-writing";
import type {
  WritingPreparationClient,
  WritingReference,
} from "../../frontend/src/features/novel-structure/api/writing-preparation";
import { chapterId, structureProjectId } from "./novel-structure-support";
import { deferred } from "./chapter-writing-support";
import {
  analyzedReference,
  chapterPlan,
  preparationClient,
  ruleRevision,
  studyModel,
  writingReference,
} from "./writing-preparation-support";

afterEach(() => {
  vi.restoreAllMocks();
});

async function setup(client: WritingPreparationClient = preparationClient()) {
  const onDirty = vi.fn();
  const result = render(
    <ReferenceWritingWorkbench
      projectId={structureProjectId}
      chapterId={chapterId}
      profile={studyModel}
      content="正文"
      onDirty={onDirty}
      client={client}
    />,
  );
  await screen.findByRole("textbox", { name: "范文名称" });
  return { ...result, client, onDirty };
}
function selectReference(value = "reference-one") {
  fireEvent.change(screen.getByRole("combobox", { name: "已保存范文" }), {
    target: { value },
  });
}

it("prepares a frozen reference before model calls and binds cloud consent to the chosen reference", async () => {
  const second = writingReference({ id: "reference-two", title: "渡口范文" });
  const api = preparationClient({
    references: vi.fn().mockResolvedValue([second]),
  });
  await setup(api);
  fireEvent.click(screen.getByRole("button", { name: "保存范文并准备分析" }));
  expect(screen.getByRole("alert")).toHaveTextContent("请填写范文名称");
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "保存范文并准备分析" }),
    ).toBeEnabled(),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "范文名称" }), {
    target: { value: "庭院范文" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "范文原文" }), {
    target: { value: "😀风吹门响。她停住脚。" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "分析粒度" }), {
    target: { value: "paragraph" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存范文并准备分析" }));
  await screen.findByText("范文已保存。请核对发送内容，再确认分析。");
  expect(api.prepareReference).toHaveBeenCalledWith(structureProjectId, {
    title: "庭院范文",
    text: "😀风吹门响。她停住脚。",
    granularity: "paragraph",
    profile_id: studyModel.id,
  });
  expect(api.analyze).not.toHaveBeenCalled();
  const send = screen.getByRole("button", { name: "确认发送并分析范文" });
  expect(send).toBeDisabled();
  fireEvent.click(screen.getByText("查看范文分析实际发送内容"));
  expect(
    screen.getByRole("textbox", { name: "分析请求 2 · user" }),
  ).toHaveValue(writingReference().text);
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "我同意向该云端模型发送此范文与分析要求",
    }),
  );
  expect(send).toBeEnabled();
  selectReference(second.id);
  expect(
    screen.getByRole("checkbox", {
      name: "我同意向该云端模型发送此范文与分析要求",
    }),
  ).not.toBeChecked();
  expect(
    screen.getByRole("button", { name: "确认发送并分析范文" }),
  ).toBeDisabled();
  selectReference();
  expect(
    screen.getByRole("button", { name: "确认发送并分析范文" }),
  ).toBeDisabled();
  expect(api.analyze).not.toHaveBeenCalled();
});

it("shows analysis progress and failure beside the send action, reconciles once and never resends automatically", async () => {
  const response = deferred<WritingReference>();
  const failed = writingReference({
    version: 3,
    attempts: 1,
    status: "failed",
    last_error: "AIProviderRateLimited",
  });
  const api = preparationClient({
    references: vi.fn().mockResolvedValue([writingReference()]),
    analyze: vi.fn().mockReturnValue(response.promise),
    reference: vi.fn().mockResolvedValue(failed),
  });
  await setup(api);
  selectReference();
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "我同意向该云端模型发送此范文与分析要求",
    }),
  );
  const button = screen.getByRole("button", { name: "确认发送并分析范文" });
  fireEvent.click(button);
  fireEvent.click(button);
  const section = screen.getByRole("region", { name: "当前范文分析" });
  expect(
    within(section).getByRole("button", { name: "正在发送并分析范文…" }),
  ).toBeDisabled();
  expect(within(section).getByText(/分析请求正在处理/)).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "丢弃未保存规划并重新加载" }),
  ).toBeDisabled();
  expect(api.analyze).toHaveBeenCalledExactlyOnceWith(
    structureProjectId,
    writingReference(),
    true,
  );
  act(() =>
    response.reject(
      new AIWritingError(
        "模型请求过于频繁，请手动重试分析。",
        "AI_PROVIDER_RATE_LIMITED",
      ),
    ),
  );
  await waitFor(() =>
    expect(within(section).getByRole("alert")).toHaveTextContent(
      "模型请求过于频繁",
    ),
  );
  expect(
    within(section).getByText("上次分析未完成 · 已发送 1/3 次"),
  ).toBeInTheDocument();
  expect(api.reference).toHaveBeenCalledExactlyOnceWith(
    structureProjectId,
    "reference-one",
  );
  expect(api.analyze).toHaveBeenCalledOnce();
  vi.mocked(api.references).mockResolvedValue([failed]);
  fireEvent.click(
    screen.getByRole("button", { name: "丢弃未保存规划并重新加载" }),
  );
  await screen.findByRole("textbox", { name: "范文名称" });
  const recovered = screen.getByRole("region", { name: "当前范文分析" });
  expect(within(recovered).getByRole("alert")).toHaveTextContent(
    "请求过于频繁",
  );
  expect(api.analyze).toHaveBeenCalledOnce();
});

it("keeps the saved reference and safe error when reconciliation also fails", async () => {
  const api = preparationClient({
    references: vi
      .fn()
      .mockResolvedValue([
        writingReference({ model_snapshot: { ...studyModel, kind: "local" } }),
      ]),
    analyze: vi.fn().mockRejectedValue(new Error("transport internal secret")),
    reference: vi.fn().mockRejectedValue(new Error("offline")),
  });
  await setup(api);
  selectReference();
  expect(
    screen.queryByRole("checkbox", {
      name: "我同意向该云端模型发送此范文与分析要求",
    }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "确认发送并分析范文" }));
  const section = screen.getByRole("region", { name: "当前范文分析" });
  await waitFor(() =>
    expect(within(section).getByRole("alert")).toHaveTextContent("连接中断"),
  );
  expect(section).not.toHaveTextContent("secret");
  expect(section).toHaveTextContent("庭院范文");
  expect(api.analyze).toHaveBeenCalledOnce();
});

it("requires rule confirmation, supports revisions, and reloads the chapter's exact chosen version", async () => {
  const revisionOne = ruleRevision();
  const revisionTwo = ruleRevision({ id: "rules-version-two", version: 2 });
  const api = preparationClient({
    references: vi.fn().mockResolvedValue([analyzedReference()]),
    confirmRules: vi
      .fn()
      .mockResolvedValueOnce(revisionOne)
      .mockResolvedValueOnce(revisionTwo),
  });
  await setup(api);
  selectReference();
  expect(screen.getByText("门响")).toBeInTheDocument();
  expect(screen.getAllByText(/写作原因（推测）/)).toHaveLength(2);
  expect(api.confirmRules).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "编辑并提炼这份范文的写作规则" }),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "规则 1 操作方法" }), {
    target: { value: "" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认保存写作规则" }));
  const editor = screen.getByRole("region", { name: "确认写作规则" });
  expect(within(editor).getByRole("alert")).toHaveTextContent("操作方法");
  expect(api.confirmRules).not.toHaveBeenCalled();
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "确认保存写作规则" }),
    ).toBeEnabled(),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "规则 1 操作方法" }), {
    target: { value: "将动作拆为意图、实施和余波。" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认保存写作规则" }));
  await waitFor(() =>
    expect(within(editor).getByRole("status")).toHaveTextContent("版本 1"),
  );
  expect(api.confirmRules).toHaveBeenLastCalledWith(
    structureProjectId,
    {
      title: "庭院范文 写作方法",
      reference_id: "reference-one",
      rules: [
        {
          ...revisionOne.rules[0],
          instruction: "将动作拆为意图、实施和余波。",
        },
      ],
    },
    undefined,
  );
  expect(
    screen.getByRole("checkbox", { name: "动作方法 · 版本 1" }),
  ).not.toBeChecked();
  fireEvent.change(screen.getByRole("textbox", { name: "规则 1 适用范围" }), {
    target: { value: "关键冲突" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "确认保存写作规则新版本" }),
  );
  await waitFor(() =>
    expect(within(editor).getByRole("status")).toHaveTextContent("版本 2"),
  );
  expect(api.confirmRules).toHaveBeenLastCalledWith(
    structureProjectId,
    expect.objectContaining({ reference_id: "reference-one" }),
    revisionOne,
  );
  expect(
    screen.getByRole("checkbox", { name: "动作方法 · 版本 1" }),
  ).not.toBeChecked();
  expect(
    screen.getByRole("checkbox", { name: "动作方法 · 版本 2" }),
  ).not.toBeChecked();
  vi.mocked(api.rules).mockResolvedValue([revisionTwo, revisionOne]);
  vi.mocked(api.plan).mockResolvedValue(chapterPlan());
  fireEvent.click(
    screen.getByRole("button", { name: "丢弃未保存规划并重新加载" }),
  );
  await screen.findByText(/规划已保存 · 版本 1/);
  expect(
    screen.getByRole("checkbox", { name: "动作方法 · 版本 1" }),
  ).toBeChecked();
  expect(
    screen.getByRole("checkbox", { name: "动作方法 · 版本 2" }),
  ).not.toBeChecked();
  expect(api.analyze).not.toHaveBeenCalled();
});

it("shows successful analysis without automatically confirming its suggested rules", async () => {
  const local = writingReference({
    model_snapshot: { ...studyModel, kind: "local" },
  });
  const api = preparationClient({
    references: vi.fn().mockResolvedValue([local]),
  });
  await setup(api);
  selectReference();
  fireEvent.click(screen.getByRole("button", { name: "确认发送并分析范文" }));
  await screen.findByText("分析已保存。查看对照说明后，可编辑并确认写作规则。");
  expect(api.analyze).toHaveBeenCalledExactlyOnceWith(
    structureProjectId,
    local,
    false,
  );
  expect(screen.getByText("门响")).toBeInTheDocument();
  expect(api.confirmRules).not.toHaveBeenCalled();
});

it("keeps a conflicting rule draft visible and offers explicit version selection", async () => {
  const revision = ruleRevision();
  const api = preparationClient({
    rules: vi.fn().mockResolvedValue([revision]),
    confirmRules: vi
      .fn()
      .mockRejectedValue(
        new AIWritingError(
          "规则版本已改变，当前草稿已保留。",
          "WRITING_CONFLICT",
        ),
      ),
  });
  await setup(api);
  fireEvent.change(screen.getByRole("combobox", { name: "编辑已有规则版本" }), {
    target: { value: revision.id },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "规则集名称" }), {
    target: { value: "我的规则草稿" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "确认保存写作规则新版本" }),
  );
  const section = screen.getByRole("region", { name: "确认写作规则" });
  await waitFor(() =>
    expect(within(section).getByRole("alert")).toHaveTextContent("草稿已保留"),
  );
  expect(screen.getByRole("textbox", { name: "规则集名称" })).toHaveValue(
    "我的规则草稿",
  );
  fireEvent.click(screen.getByRole("button", { name: "增加写作规则" }));
  expect(screen.getByRole("textbox", { name: "规则 2 名称" })).toHaveValue("");
  fireEvent.click(screen.getByRole("button", { name: "删除规则 2" }));
  expect(
    screen.queryByRole("textbox", { name: "规则 2 名称" }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "编辑已有规则版本" }), {
    target: { value: "" },
  });
  expect(screen.getByRole("textbox", { name: "规则集名称" })).toHaveValue("");
  expect(
    screen.getByRole("button", { name: "确认保存写作规则" }),
  ).toBeDisabled();
});

it("blocks reload during a plan save and preserves unsaved content after a conflict", async () => {
  const pending = deferred<ReturnType<typeof chapterPlan>>();
  const api = preparationClient({
    plan: vi.fn().mockResolvedValue(chapterPlan()),
    savePlan: vi.fn().mockReturnValue(pending.promise),
  });
  const { onDirty } = await setup(api);
  fireEvent.change(screen.getByRole("textbox", { name: "章节重点 1" }), {
    target: { value: "我的新重点" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存章节规划" }));
  expect(
    screen.getByRole("button", { name: "丢弃未保存规划并重新加载" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "保存范文并准备分析" }),
  ).toBeDisabled();
  act(() =>
    pending.reject(
      new AIWritingError("规划冲突，当前草稿已保留。", "PLANNING_CONFLICT"),
    ),
  );
  await screen.findByText("规划冲突，当前草稿已保留。");
  expect(screen.getByRole("textbox", { name: "章节重点 1" })).toHaveValue(
    "我的新重点",
  );
  expect(
    screen.getByRole("button", { name: "丢弃未保存规划并重新加载" }),
  ).toBeEnabled();
  expect(onDirty).toHaveBeenLastCalledWith(true);
  fireEvent.click(
    screen.getByRole("button", { name: "丢弃未保存规划并重新加载" }),
  );
  await screen.findByRole("textbox", { name: "章节重点 1" });
  expect(screen.getByRole("textbox", { name: "章节重点 1" })).toHaveValue(
    "主人公开始怀疑来客",
  );
  expect(onDirty).toHaveBeenLastCalledWith(false);
});

it("recovers an initial loading failure on explicit reload and prevents exhausted analysis attempts", async () => {
  const api = preparationClient({
    references: vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce([
        writingReference({
          status: "failed",
          attempts: 3,
          last_error: "WritingOutputInvalid",
        }),
      ]),
  });
  render(
    <ReferenceWritingWorkbench
      projectId={structureProjectId}
      chapterId={chapterId}
      profile={undefined}
      content=""
      onDirty={vi.fn()}
      client={api}
    />,
  );
  await screen.findByRole("alert");
  expect(
    screen.queryByRole("textbox", { name: "范文名称" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "丢弃未保存规划并重新加载" }),
  );
  await screen.findByRole("textbox", { name: "范文名称" });
  expect(
    screen.getByRole("button", { name: "保存范文并准备分析" }),
  ).toBeDisabled();
  selectReference();
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "我同意向该云端模型发送此范文与分析要求",
    }),
  );
  expect(
    screen.getByRole("button", { name: "确认发送并分析范文" }),
  ).toBeDisabled();
  expect(
    within(screen.getByRole("region", { name: "当前范文分析" })).getByRole(
      "alert",
    ),
  ).toHaveTextContent("引文与原文不符");
  expect(api.analyze).not.toHaveBeenCalled();
});
