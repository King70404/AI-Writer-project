/**
 * C-3：一致性评审使用本章召回设置。准备只走假客户端，从不发送模型请求。
 */
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../../frontend/src/api/errors";
import { StoryMemoryWorkbench } from "../../frontend/src/features/novel-structure/components/StoryMemoryWorkbench";
import {
  memoryError,
  parseMemoryReview,
  type ReviewRecall,
  type StoryMemoryClient,
} from "../../frontend/src/features/novel-structure/api/story-memory";
import { allowFakeAnalysisEstimates } from "./analysis-estimate-support";
import { chapterId, structureProjectId } from "./novel-structure-support";
import { studyModel } from "./writing-preparation-support";
import {
  memoryClient,
  memoryReview,
  memoryWorkspace,
} from "./story-memory-support";

beforeEach(allowFakeAnalysisEstimates);
afterEach(() => vi.restoreAllMocks());

const pinnedFact = {
  id: "fact-pinned",
  title: "旧伤",
  text: "左臂有旧伤",
  quote: "左臂有旧伤。",
};
const relatedFact = {
  id: "fact-related",
  title: "船夫身份",
  text: "船夫是老船夫",
  quote: "老船夫。",
};
const recall: ReviewRecall = {
  policy_version: 2,
  pinned_fact_ids: ["fact-pinned"],
  excluded_fact_ids: ["fact-excluded"],
  selected: [
    {
      id: "fact-pinned",
      revision_id: "rev-pinned",
      chapter_id: "chapter-earlier",
      title: "旧伤",
      reason: "pinned",
      characters: 120,
    },
    {
      id: "fact-related",
      revision_id: "rev-related",
      chapter_id: "chapter-earlier",
      title: "船夫身份",
      reason: "related",
      characters: 80,
    },
  ],
  omitted: [
    { id: "fact-excluded", title: "渡口天气", reason: "excluded" },
    { id: "fact-budget", title: "远方来信", reason: "budget" },
  ],
  omitted_total: 1,
  excluded_total: 1,
  used_characters: 200,
  character_limit: 10_000,
  item_limit: 24,
};
const reviewWithRecall = memoryReview({
  facts: [pinnedFact, relatedFact],
  omitted_facts: 1,
  recall,
});

function raw(review: object) {
  return {
    ...review,
    project_id: structureProjectId,
    kind: "review",
    revision_id: "review-revision",
    updated_at: "2026-11-18T00:00:00+00:00",
  };
}

async function setup(client: StoryMemoryClient) {
  render(
    <MemoryRouter>
      <StoryMemoryWorkbench
        projectId={structureProjectId}
        chapterId={chapterId}
        sourceRevision="chapter-revision-one"
        profile={studyModel}
        disabled={false}
        onRewrite={vi.fn()}
        client={client}
      />
    </MemoryRouter>,
  );
  await waitFor(() => expect(client.workspace).toHaveBeenCalled());
  await act(() => Promise.resolve());
}

it("decodes the frozen recall explanation and keeps legacy reviews readable", () => {
  expect(
    parseMemoryReview(raw(reviewWithRecall), structureProjectId, chapterId)
      .recall,
  ).toEqual(recall);
  const legacy: Record<string, unknown> = raw(memoryReview());
  delete legacy.recall;
  expect(
    parseMemoryReview(legacy, structureProjectId, chapterId).recall,
  ).toBeNull();
});

it.each([
  { selected: [...recall.selected].reverse() },
  { selected: recall.selected.slice(0, 1) },
  {
    omitted: [{ id: "fact-x", title: "x", reason: "pin_over_budget" }],
  },
  { selected: [{ ...recall.selected[0], reason: "auto" }, recall.selected[1]] },
  { used_characters: -1 },
])(
  "rejects an explanation that does not match the frozen facts: %j",
  (patch) => {
    expect(() =>
      parseMemoryReview(
        raw({ ...reviewWithRecall, recall: { ...recall, ...patch } }),
        structureProjectId,
        chapterId,
      ),
    ).toThrow("无法安全读取");
  },
);

it("shows which facts the review pinned, excluded or omitted and why", async () => {
  const client = memoryClient({
    workspace: vi
      .fn()
      .mockResolvedValue(memoryWorkspace({ reviews: [reviewWithRecall] })),
  });
  await setup(client);
  const explanation = screen.getByRole("region", { name: "评审召回说明" });
  expect(explanation).toHaveTextContent("本章召回设置第 2 版");
  expect(explanation).toHaveTextContent("作者排除的事实不发送");
  const selected = within(explanation).getAllByRole("listitem");
  expect(selected[0]).toHaveTextContent("旧伤（作者固定 · 120 字符）");
  expect(selected[1]).toHaveTextContent("船夫身份（文字关联 · 80 字符）");
  const omitted = within(explanation).getByRole("list", {
    name: "未纳入的事实及原因",
  });
  expect(omitted).toHaveTextContent("渡口天气（作者排除）");
  expect(omitted).toHaveTextContent("远方来信（超出召回预算");
  expect(within(explanation).queryByRole("alert")).toBeNull();
  expect(client.send).not.toHaveBeenCalled();
  expect(client.prepare).not.toHaveBeenCalled();
});

it("labels reviews without a saved policy and legacy reviews honestly", async () => {
  const unset = memoryReview({
    id: "review-unset",
    facts: [relatedFact],
    recall: {
      ...recall,
      policy_version: 0,
      pinned_fact_ids: [],
      excluded_fact_ids: [],
      selected: [recall.selected[1]],
      omitted: [],
      omitted_total: 0,
      excluded_total: 0,
    },
  });
  const client = memoryClient({
    workspace: vi
      .fn()
      .mockResolvedValue(memoryWorkspace({ reviews: [unset, memoryReview()] })),
  });
  await setup(client);
  expect(
    screen.getByRole("region", { name: "评审召回说明" }),
  ).toHaveTextContent("准备时本章没有召回设置");
  fireEvent.change(screen.getByLabelText("已保存的评审"), {
    target: { value: "review-one" },
  });
  expect(screen.getByText(/没有记录召回说明/u)).toBeInTheDocument();
});

it("explains a refused preparation without calling the model", async () => {
  const refusal = new ApiError({
    code: "AI_RECALL_PINS_INVALID",
    status: 409,
    message: "private",
    details: {},
    retryable: false,
    suggestedAction: null,
    requestId: null,
  });
  const client = memoryClient({
    prepare: vi.fn().mockRejectedValue(memoryError(refusal)),
  });
  await setup(client);
  fireEvent.click(screen.getByRole("button", { name: "准备本章评审" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("评审未准备");
  expect(alert).toHaveTextContent("未调用模型");
  expect(client.send).not.toHaveBeenCalled();
});
