/**
 * C-4 语义索引前端：只用假客户端，读取/预估从不发送；建立索引需作者勾选确认。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  parseModelProfile,
  type AIWorkflowClient,
  type ModelProfile,
} from "../../frontend/src/features/novel-structure/api/ai-workflow";
import {
  parseSemanticStatus,
  type SemanticIndexClient,
  type SemanticIndexStatus,
} from "../../frontend/src/features/novel-structure/api/semantic-index";
import { AIModelSettings } from "../../frontend/src/features/novel-structure/components/AIModelSettings";
import { SemanticIndexPanel } from "../../frontend/src/features/novel-structure/components/SemanticIndexPanel";
import { parsePreview } from "../../frontend/src/features/story-control/api/storyControl";
import { RecallExplanation } from "../../frontend/src/features/story-control/components/ChapterStoryControl";
import {
  budgetClient,
  type SendEstimate,
} from "../../frontend/src/features/usage/api/budget";

afterEach(() => vi.restoreAllMocks());

const PROJECT = "prj_semantic";
const EMBED: ModelProfile = {
  id: "e".repeat(32),
  name: "本地嵌入",
  kind: "local",
  base_url: "http://127.0.0.1:1234/v1",
  model: "fake-embed",
  max_output_tokens: 1,
  has_key: false,
  purpose: "embedding",
};
const CHAT: ModelProfile = {
  ...EMBED,
  id: "c".repeat(32),
  name: "对话",
  model: "chat",
  purpose: undefined,
};
const estimate: SendEstimate = {
  estimate_method: "utf8_bytes_upper_v1",
  profile_id: EMBED.id,
  input_characters: 120,
  input_tokens_upper: 400,
  output_tokens_upper: 0,
  price: null,
  estimated_cost_upper: "0.0004",
  currency: "CNY",
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
function status(
  changes: Partial<SemanticIndexStatus> = {},
): SemanticIndexStatus {
  return {
    project_id: PROJECT,
    settings: {
      version: 1,
      enabled: true,
      profile_id: EMBED.id,
      updated_at: "t",
    },
    profile: {
      id: EMBED.id,
      name: EMBED.name,
      kind: "local",
      model: "fake-embed",
    },
    profile_problem: null,
    facts_total: 3,
    facts_indexed: 0,
    chapters_total: 2,
    chapters_indexed: 0,
    stale_entries: 0,
    up_to_date: false,
    plan: {
      plan_version: "a".repeat(64),
      fact_items: 3,
      chunk_items: 2,
      requests: 1,
      input_characters: 120,
      deferred_items: 0,
      obsolete_entries: 0,
    },
    estimate,
    ...changes,
  };
}
function client(current: SemanticIndexStatus) {
  const built = status({
    plan: null,
    estimate: null,
    up_to_date: true,
    facts_indexed: 3,
    chapters_indexed: 2,
  });
  return {
    status: vi.fn().mockResolvedValue(current),
    saveSettings: vi.fn().mockResolvedValue(current.settings),
    build: vi.fn().mockResolvedValue({
      build_id: "build",
      requests_sent: 1,
      items_indexed: 5,
      entries_removed: 0,
      status: built,
    }),
  } satisfies SemanticIndexClient;
}
async function open(fake: SemanticIndexClient) {
  render(
    <SemanticIndexPanel
      projectId={PROJECT}
      client={fake}
      loadModels={() => Promise.resolve([CHAT, EMBED])}
    />,
  );
  fireEvent.click(screen.getByText("语义索引（可选，建立索引会计费）"));
  await screen.findByText(/本次待更新/u);
}

it("does not read anything until opened and shows the estimate without sending", async () => {
  const fake = client(status());
  render(
    <SemanticIndexPanel
      projectId={PROJECT}
      client={fake}
      loadModels={() => Promise.resolve([CHAT, EMBED])}
    />,
  );
  expect(fake.status).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("语义索引（可选，建立索引会计费）"));
  expect(await screen.findByText(/事实 3 项、正文分块 2/u)).toBeTruthy();
  expect(screen.getByText(/预估输入 token 上限 400/u).textContent).toContain(
    "0.0004 CNY",
  );
  // Only embedding profiles are offered.
  const options = screen
    .getAllByRole("option")
    .map((item) => item.textContent ?? "");
  expect(options.some((text) => text.includes("对话"))).toBe(false);
  expect(options.some((text) => text.includes("本地嵌入"))).toBe(true);
  expect(fake.build).not.toHaveBeenCalled();
});

it("builds only after the author confirms the exact plan", async () => {
  const fake = client(status());
  await open(fake);
  const button = screen.getByRole("button", { name: "确认并建立/更新索引" });
  expect(button).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByLabelText("我已核对以上预估，确认发送并计费"));
  fireEvent.click(button);
  await screen.findByText(/已发送 1 个嵌入请求/u);
  expect(fake.build).toHaveBeenCalledWith(PROJECT, {
    plan_version: "a".repeat(64),
    confirm_estimate: true,
    cloud_consent: false,
  });
  expect(screen.getByText("语义索引已是最新。")).toBeTruthy();
});

it("refuses a strict-budget plan and requires cloud consent", async () => {
  const refused = client(
    status({
      estimate: {
        ...estimate,
        decision: "refused",
        reasons: ["PRICE_MISSING"],
      },
    }),
  );
  await open(refused);
  expect(screen.getByText(/严格预算将拒绝/u)).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "确认并建立/更新索引" }),
  ).toHaveProperty("disabled", true);
  refused.build.mockClear();
  document.body.innerHTML = "";

  const cloud = client(
    status({
      profile: { id: EMBED.id, name: "云嵌入", kind: "cloud", model: "e" },
    }),
  );
  await open(cloud);
  fireEvent.click(screen.getByLabelText("我已核对以上预估，确认发送并计费"));
  const button = screen.getByRole("button", { name: "确认并建立/更新索引" });
  expect(button).toHaveProperty("disabled", true);
  fireEvent.click(screen.getByLabelText(/同意把上述事实与正文分块发送给云端/u));
  fireEvent.click(button);
  await waitFor(() =>
    expect(cloud.build).toHaveBeenCalledWith(PROJECT, {
      plan_version: "a".repeat(64),
      confirm_estimate: true,
      cloud_consent: true,
    }),
  );
});

it("parses status strictly and keeps chat profiles in their old shape", () => {
  expect(parseSemanticStatus(status(), PROJECT).plan?.requests).toBe(1);
  expect(() => parseSemanticStatus(status(), "prj_other")).toThrow();
  expect(() =>
    parseSemanticStatus({ ...status(), profile_problem: "unknown" }, PROJECT),
  ).toThrow();
  expect(parseModelProfile({ ...CHAT, purpose: "chat" })).not.toHaveProperty(
    "purpose",
  );
  expect(parseModelProfile({ ...EMBED }).purpose).toBe("embedding");
  expect(() => parseModelProfile({ ...EMBED, purpose: "other" })).toThrow();
});

it("labels semantic and fallback recall in the explanation", () => {
  const preview = parsePreview(
    {
      chapter_id: "ch",
      policy_version: 0,
      selected: [
        {
          id: "f1",
          revision_id: "r1",
          chapter_id: "c1",
          title: "船夫旧伤",
          reason: "related",
          characters: 80,
          similarity: 0.95,
        },
      ],
      omitted: [],
      omitted_total: 0,
      excluded_total: 0,
      used_characters: 80,
      character_limit: 10000,
      item_limit: 24,
      blocked: false,
      mode: "semantic",
      semantic_note: null,
    },
    "ch",
  );
  const { rerender } = render(<RecallExplanation recall={preview} />);
  expect(screen.getByText(/排序方式：语义召回/u)).toBeTruthy();
  expect(screen.getByText(/语义相似度 0.95/u)).toBeTruthy();
  rerender(
    <RecallExplanation
      recall={{
        ...preview,
        mode: "fallback",
        semantic_note: "本章正文尚未建立语义索引或已修改，请增量更新索引",
      }}
    />,
  );
  expect(screen.getByText(/已回退为文字关联/u).textContent).toContain(
    "原因：本章正文尚未建立语义索引或已修改",
  );
  const deterministic = parsePreview(
    { ...preview, mode: "deterministic", semantic_note: null, selected: [] },
    "ch",
  );
  expect(deterministic).not.toHaveProperty("mode");
});

it("saves an embedding profile with its purpose and offers the embedding price", async () => {
  const saveModel = vi.fn().mockResolvedValue(EMBED);
  vi.spyOn(budgetClient, "price").mockResolvedValue({
    profile_id: EMBED.id,
    current: null,
    history: [],
  });
  render(
    <AIModelSettings
      models={[]}
      onSaved={() => undefined}
      open
      client={{ saveModel } as unknown as AIWorkflowClient}
    />,
  );
  fireEvent.change(screen.getByLabelText("配置名称"), {
    target: { value: "本地嵌入" },
  });
  fireEvent.change(screen.getByLabelText("用途"), {
    target: { value: "embedding" },
  });
  expect(screen.queryByLabelText("每次输出 Token 上限")).toBeNull();
  expect(
    screen.getByText(/每次建立\/更新索引都会按服务商价格计费/u),
  ).toBeTruthy();
  fireEvent.change(screen.getByLabelText("模型名称"), {
    target: { value: "fake-embed" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
  await screen.findByText(/嵌入模型“本地嵌入”已保存/u);
  expect(saveModel.mock.calls[0][0]).toMatchObject({
    purpose: "embedding",
    model: "fake-embed",
  });
  expect(screen.getByRole("form", { name: "嵌入模型单价" })).toBeTruthy();
});
