import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  allowFakeAnalysisEstimates,
  allowedAnalysisEstimate,
} from "./analysis-estimate-support";
import { analysisEstimateClient } from "../../frontend/src/features/usage/api/budget";
import { StoryMemoryWorkbench } from "../../frontend/src/features/novel-structure/components/StoryMemoryWorkbench";
import { AIWritingError } from "../../frontend/src/features/novel-structure/api/ai-writing";
import type { StoryMemoryClient } from "../../frontend/src/features/novel-structure/api/story-memory";
import { chapterId, structureProjectId } from "./novel-structure-support";
import { studyModel } from "./writing-preparation-support";
import { deferred } from "./chapter-writing-support";
import {
  memoryClient,
  memoryFact,
  memoryReview,
  memoryWorkspace,
} from "./story-memory-support";

beforeEach(allowFakeAnalysisEstimates);
afterEach(() => vi.restoreAllMocks());

async function setup(
  client: StoryMemoryClient = memoryClient(),
  disabled = false,
  revision = "chapter-revision-one",
) {
  const onRewrite = vi.fn();
  const result = render(
    <MemoryRouter>
      <StoryMemoryWorkbench
        projectId={structureProjectId}
        chapterId={chapterId}
        sourceRevision={revision}
        profile={studyModel}
        disabled={disabled}
        onRewrite={onRewrite}
        client={client}
      />
    </MemoryRouter>,
  );
  await waitFor(() => expect(client.workspace).toHaveBeenCalled());
  await act(() => Promise.resolve());
  return { ...result, client, onRewrite };
}
it("reads memory without sending a review and saves a manual candidate pending explicit confirmation", async () => {
  const { client } = await setup();
  expect(client.send).not.toHaveBeenCalled();
  expect(client.prepare).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("事实标题"), {
    target: { value: "新事实" },
  });
  fireEvent.change(screen.getByLabelText("事实内容"), {
    target: { value: "渡口雨停" },
  });
  fireEvent.change(screen.getByLabelText("事实原文引文"), {
    target: { value: "雨停" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存为待确认事实" }));
  await screen.findByText("事实状态已保存。");
  expect(client.fact).toHaveBeenCalledWith(
    structureProjectId,
    chapterId,
    {
      title: "新事实",
      text: "渡口雨停",
      quote: "雨停",
      status: "pending",
      expected_version: 0,
      source_revision: "chapter-revision-one",
    },
    undefined,
  );
  expect(screen.getByLabelText("事实内容")).toHaveValue("");
});
it("confirms a saved fact with its expected version and supports explicit rejection", async () => {
  const { client } = await setup();
  fireEvent.click(screen.getByRole("button", { name: "确认此事实" }));
  await screen.findByText("事实已由你确认，可供后文章节召回。");
  expect(client.fact).toHaveBeenLastCalledWith(
    structureProjectId,
    chapterId,
    expect.objectContaining({ status: "confirmed", expected_version: 1 }),
    "fact-one",
  );
  fireEvent.click(screen.getByRole("button", { name: "驳回此事实" }));
  await screen.findByText("事实状态已保存。");
  expect(client.fact).toHaveBeenLastCalledWith(
    structureProjectId,
    chapterId,
    expect.objectContaining({ status: "rejected" }),
    "fact-one",
  );
});
it("preserves editable draft on conflict and allows author reconfirmation after checking new prose", async () => {
  const client = memoryClient({
    fact: vi.fn().mockRejectedValue(new AIWritingError("草稿已保留，请刷新。")),
  });
  await setup(client);
  fireEvent.click(screen.getByRole("button", { name: "编辑并核对原文" }));
  fireEvent.change(screen.getByLabelText("事实内容"), {
    target: { value: "修改后的事实" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认编辑后的事实" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("事实内容")).toHaveValue("修改后的事实");
  fireEvent.click(screen.getByRole("button", { name: "取消事实编辑" }));
  expect(screen.getByLabelText("事实内容")).toHaveValue("");
});
it("requires cloud consent for the selected frozen review and sends only on explicit action", async () => {
  const { client } = await setup();
  const send = screen.getByRole("button", { name: "确认发送并评审" });
  expect(send).toBeDisabled();
  fireEvent.click(screen.getByText("查看评审实际发送内容"));
  expect(screen.getByLabelText("评审发送正文")).toHaveValue("渡口正在下雨。");
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(send);
  await screen.findByText(/评审完成/u);
  expect(client.send).toHaveBeenCalledExactlyOnceWith(
    structureProjectId,
    chapterId,
    memoryReview(),
    true,
  );
});
it("prepares a review without provider send and resets consent", async () => {
  const { client } = await setup();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "准备本章评审" }));
  await screen.findByText(/评审已准备/u);
  expect(client.prepare).toHaveBeenCalledWith(
    structureProjectId,
    chapterId,
    "chapter-revision-one",
    studyModel.id,
  );
  expect(client.send).not.toHaveBeenCalled();
  expect(screen.getByRole("checkbox")).not.toBeChecked();
});
it("exposes extracted facts for editing and hands an anchored recommendation to guarded rewrite", async () => {
  const fact = { title: "天气", text: "正在下雨", quote: "渡口正在下雨。" };
  const review = memoryReview({
    status: "completed",
    attempts: 1,
    result: {
      summary: "检查完成",
      facts: [fact],
      findings: [
        {
          quote: "正在下雨",
          explanation: "需承接天气变化",
          instruction: "补充雨停过渡",
          fact_ids: [],
        },
      ],
    },
  });
  const { client, onRewrite } = await setup(
    memoryClient({
      workspace: vi
        .fn()
        .mockResolvedValue(memoryWorkspace({ reviews: [review] })),
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "编辑这条候选事实" }));
  expect(screen.getByLabelText("事实原文引文")).toHaveValue(fact.quote);
  expect(client.fact).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "按此建议准备改写" }));
  expect(onRewrite).toHaveBeenCalledWith(
    "正在下雨",
    "补充雨停过渡",
    "chapter-revision-one",
  );
});
it("keeps stale reviews historical and links affected chapters", async () => {
  const review = memoryReview({
    stale: true,
    status: "failed",
    last_error: "AIProviderTimeout",
    attempts: 3,
  });
  const client = memoryClient({
    workspace: vi.fn().mockResolvedValue(
      memoryWorkspace({
        facts: [memoryFact({ stale: true })],
        reviews: [review],
        impacts: [
          {
            chapter_id: chapterId,
            title: "受影响章节",
            reason: "来源已变化",
          },
        ],
      }),
    ),
  });
  await setup(client);
  expect(screen.getByRole("button", { name: "确认发送并评审" })).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "确认此事实" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "受影响章节" })).toHaveAttribute(
    "href",
    `/projects/${structureProjectId}/chapters/${chapterId}/write`,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("不会自动重发");
});
it.each([true, false])(
  "blocks unsaved or mismatched source versions: disabled=%s",
  async (disabled) => {
    await setup(
      memoryClient(),
      disabled,
      disabled ? "chapter-revision-one" : "changed-revision",
    );
    expect(screen.getByRole("button", { name: "准备本章评审" })).toBeDisabled();
  },
);
it("reconciles a lost send response by reading and never duplicates a locked send", async () => {
  const pending = deferred<ReturnType<typeof memoryReview>>();
  const client = memoryClient({
    send: vi.fn().mockReturnValue(pending.promise),
  });
  await setup(client);
  fireEvent.click(screen.getByRole("checkbox"));
  const button = screen.getByRole("button", { name: "确认发送并评审" });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(client.send).toHaveBeenCalledOnce();
  await act(() => {
    pending.reject(new Error("private transport details"));
    return Promise.resolve();
  });
  expect(await screen.findByRole("alert")).toHaveTextContent("不会自动重发");
  expect(screen.getByRole("alert")).not.toHaveTextContent("private");
  expect(client.workspace).toHaveBeenCalledTimes(2);
});
it("reports initial load failures and can refresh without losing typed draft", async () => {
  const client = memoryClient({
    workspace: vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(memoryWorkspace()),
  });
  await setup(client);
  expect(screen.getByRole("alert")).toHaveTextContent("连接中断");
  fireEvent.click(screen.getByRole("button", { name: "刷新记忆与评审" }));
  await screen.findByText("渡口正在下雨");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("shows a strict refusal for review and makes no send request", async () => {
  vi.mocked(analysisEstimateClient.review).mockResolvedValueOnce(
    allowedAnalysisEstimate({
      budget_mode: "strict",
      decision: "refused",
      reasons: ["MONTHLY_LIMIT_EXCEEDED"],
    }),
  );
  const client = memoryClient();
  await setup(client);
  expect(await screen.findByText(/按严格预算不会发送/u)).toBeVisible();
  expect(screen.getByRole("button", { name: "确认发送并评审" })).toBeDisabled();
  expect(client.send).not.toHaveBeenCalled();
});
