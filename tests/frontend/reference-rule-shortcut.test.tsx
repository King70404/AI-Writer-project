import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { allowFakeAnalysisEstimates } from "./analysis-estimate-support";

import { ReferenceWritingWorkbench } from "../../frontend/src/features/novel-structure/components/ReferenceWritingWorkbench";
import type { WritingPreparationClient } from "../../frontend/src/features/novel-structure/api/writing-preparation";
import { chapterId, structureProjectId } from "./novel-structure-support";
import {
  analyzedReference,
  chapterPlan,
  preparationClient,
  ruleRevision,
  studyModel,
} from "./writing-preparation-support";

beforeEach(allowFakeAnalysisEstimates);
afterEach(() => {
  vi.restoreAllMocks();
});

async function setup(client: WritingPreparationClient, withGenerate = true) {
  const onDirty = vi.fn();
  const onOpenGenerate = withGenerate ? vi.fn() : undefined;
  render(
    <ReferenceWritingWorkbench
      projectId={structureProjectId}
      chapterId={chapterId}
      profile={studyModel}
      content="正文"
      onDirty={onDirty}
      onOpenGenerate={onOpenGenerate}
      client={client}
    />,
  );
  await screen.findByRole("textbox", { name: "范文名称" });
  return { onDirty, onOpenGenerate };
}

it("adds a confirmed rule version to the chapter plan without saving, then returns to generation after saving", async () => {
  const revision = ruleRevision({ id: "rules-version-new", version: 1 });
  const api = preparationClient({
    references: vi.fn().mockResolvedValue([analyzedReference()]),
    confirmRules: vi.fn().mockResolvedValue(revision),
    savePlan: vi
      .fn()
      .mockResolvedValue(
        chapterPlan({ writing_rule_revision_ids: [revision.id] }),
      ),
  });
  const { onDirty, onOpenGenerate } = await setup(api);
  expect(
    screen.queryByRole("button", { name: "将此规则加入本章规划" }),
  ).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "已保存范文" }), {
    target: { value: "reference-one" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "编辑并提炼这份范文的写作规则" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "确认保存写作规则" }));
  const rules = screen.getByRole("region", { name: "确认写作规则" });
  await waitFor(() =>
    expect(within(rules).getByRole("status")).toHaveTextContent(
      "可点击“将此规则加入本章规划”",
    ),
  );
  const checkbox = screen.getByRole("checkbox", { name: "动作方法 · 版本 1" });
  expect(checkbox).not.toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: "将此规则加入本章规划" }));
  expect(checkbox).toBeChecked();
  expect(onDirty).toHaveBeenLastCalledWith(true);
  expect(api.savePlan).not.toHaveBeenCalled();
  expect(
    within(rules).getByText(/已把“动作方法”版本 1 加入本章规划，尚未保存/u),
  ).toHaveAttribute("role", "status");
  await waitFor(() => expect(checkbox).toHaveFocus());
  fireEvent.click(screen.getByRole("button", { name: "将此规则加入本章规划" }));
  expect(
    within(rules).getByText("本章规划已选用“动作方法”版本 1。"),
  ).toHaveAttribute("role", "status");
  fireEvent.change(screen.getByRole("textbox", { name: "章节重点 1" }), {
    target: { value: "主人公开始怀疑来客" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存章节规划" }));
  const notice = await screen.findByRole("group", { name: "规划已保存" });
  expect(api.savePlan).toHaveBeenCalledWith(
    structureProjectId,
    chapterId,
    expect.objectContaining({ writing_rule_revision_ids: [revision.id] }),
    0,
  );
  fireEvent.click(
    within(notice).getByRole("button", { name: "去“生成”准备续写" }),
  );
  expect(onOpenGenerate).toHaveBeenCalledOnce();
});

it("refuses a ninth rule version and keeps the existing selection", async () => {
  const selected = Array.from({ length: 8 }, (_, index) =>
    ruleRevision({
      id: `rules-version-${index}`,
      rule_id: `rules-${index}`,
      title: `方法${index}`,
    }),
  );
  const extra = ruleRevision({
    id: "rules-version-extra",
    rule_id: "rules-extra",
    title: "第九份方法",
  });
  const api = preparationClient({
    rules: vi.fn().mockResolvedValue([extra, ...selected]),
    plan: vi.fn().mockResolvedValue(
      chapterPlan({
        writing_rule_revision_ids: selected.map((item) => item.id),
      }),
    ),
  });
  await setup(api);
  fireEvent.change(screen.getByRole("combobox", { name: "编辑已有规则版本" }), {
    target: { value: extra.id },
  });
  fireEvent.click(screen.getByRole("button", { name: "将此规则加入本章规划" }));
  expect(
    within(screen.getByRole("region", { name: "确认写作规则" })).getByRole(
      "status",
    ),
  ).toHaveTextContent("最多选用 8 份规则版本");
  expect(
    screen.getByRole("checkbox", { name: "第九份方法 · 版本 1" }),
  ).not.toBeChecked();
  expect(api.savePlan).not.toHaveBeenCalled();
});

it("does not change the plan while it is being saved", async () => {
  let release!: () => void;
  const api = preparationClient({
    rules: vi.fn().mockResolvedValue([ruleRevision()]),
    plan: vi
      .fn()
      .mockResolvedValue(chapterPlan({ writing_rule_revision_ids: [] })),
    savePlan: vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve(chapterPlan());
        }),
    ),
  });
  await setup(api, false);
  fireEvent.change(screen.getByRole("combobox", { name: "编辑已有规则版本" }), {
    target: { value: "rules-version-one" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存章节规划" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "正在保存规划…" })).toBeVisible(),
  );
  // The shortcut is disabled while saving; the handle also refuses edits.
  expect(
    screen.getByRole("button", { name: "将此规则加入本章规划" }),
  ).toBeDisabled();
  release();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "保存章节规划" })).toBeVisible(),
  );
  // Without a generation callback the saved notice is not offered.
  expect(
    screen.queryByRole("group", { name: "规划已保存" }),
  ).not.toBeInTheDocument();
});
