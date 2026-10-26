import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AIWorkflowAssistant } from "../../frontend/src/features/novel-structure/components/AIWorkflowAssistant";
import { AIModelSettings } from "../../frontend/src/features/novel-structure/components/AIModelSettings";
import { securitySession } from "../../frontend/src/api/security-session";
import { useAIWorkflow } from "../../frontend/src/features/novel-structure/hooks/useAIWorkflow";
import { useChapterWriting } from "../../frontend/src/features/novel-structure/hooks/useChapterWriting";
import {
  aiWorkflowClient,
  parseWorkflowRun,
  workflowFailureMessage,
  type AIWorkflowClient,
  type ModelProfile,
  type WorkflowRun,
} from "../../frontend/src/features/novel-structure/api/ai-workflow";
import { AIWritingError } from "../../frontend/src/features/novel-structure/api/ai-writing";
import { chapterId } from "./novel-structure-support";
import { deferred, written, writingClient } from "./chapter-writing-support";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
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
const run: WorkflowRun = {
  run_id: "run-one",
  chapter_id: chapterId,
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
      sources: [
        {
          source: "current_chapter",
          references: [[chapterId, "revision-one"]],
          text: "甲乙丙丁",
          reason: "最近正文尾部",
          omitted_reason: null,
          truncated: false,
        },
      ],
    },
  },
  candidates: [],
  last_error: null,
};
const pending: WorkflowRun = {
  ...run,
  generated_steps: 1,
  generated_characters: 240,
  candidates: [
    {
      candidate_id: "candidate-one",
      sequence: 1,
      text: "文".repeat(240),
      model: "test-model",
      character_count: 240,
      status: "pending",
      adopted_revision_id: null,
      adopted_version: null,
      latest_edit: null,
      edit_count: 0,
      adopted_edit_id: null,
    },
  ],
};
const adopted: WorkflowRun = {
  ...pending,
  current_version: 2,
  current_revision_id: "revision-two",
  candidates: [
    {
      ...pending.candidates[0],
      status: "adopted",
      adopted_revision_id: "revision-two",
      adopted_version: 2,
    },
  ],
};
function client(initial: WorkflowRun[] = []): AIWorkflowClient {
  return {
    upgrade: vi.fn().mockResolvedValue(undefined),
    models: vi.fn().mockResolvedValue([model]),
    saveModel: vi.fn().mockResolvedValue(model),
    list: vi.fn().mockResolvedValue(initial),
    create: vi.fn().mockResolvedValue(run),
    action: vi.fn().mockResolvedValue(pending),
    candidate: vi.fn().mockResolvedValue(adopted),
    saveEdit: vi.fn(),
  };
}
function setup(api = client(), content = writingClient()) {
  const hook = renderHook(() => {
    const writing = useChapterWriting(written("甲乙丙丁"), content);
    return { writing, ai: useAIWorkflow(chapterId, writing, api) };
  });
  return { ...hook, api, content };
}

it("keeps available models when persisted task loading fails", async () => {
  const api = client();
  vi.mocked(api.list).mockRejectedValue(new Error("任务读取失败"));
  const { result } = setup(api);
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  expect(result.current.ai.models).toEqual([model]);
  expect(result.current.ai.error).toBeTruthy();
});

it("does not erase a saved model when an older refresh finishes later", async () => {
  const api = client();
  const oldModels = deferred<ModelProfile[]>();
  vi.mocked(api.models).mockReturnValue(oldModels.promise);
  const { result } = setup(api);
  await waitFor(() => expect(api.models).toHaveBeenCalledOnce());
  act(() => result.current.ai.modelSaved(model));
  await act(async () => {
    oldModels.resolve([]);
    await oldModels.promise;
  });
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  expect(result.current.ai.models).toEqual([model]);
});

it("selects a saved model even when task history is unavailable", async () => {
  const api = client();
  vi.mocked(api.models).mockResolvedValue([]);
  vi.mocked(api.list).mockRejectedValue(new Error("任务读取失败"));
  function Harness() {
    const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
    return (
      <AIWorkflowAssistant
        chapterId={chapterId}
        writing={writing}
        selection={null}
        client={api}
      />
    );
  }
  render(<Harness />);
  await waitFor(() =>
    expect(
      screen.queryByText("正在读取模型与已保存任务…"),
    ).not.toBeInTheDocument(),
  );
  fireEvent.click(screen.getByText("模型配置"));
  fireEvent.change(screen.getByLabelText("配置名称"), {
    target: { value: model.name },
  });
  fireEvent.change(screen.getByLabelText("模型名称"), {
    target: { value: model.model },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
  await waitFor(() =>
    expect(screen.getByLabelText("使用模型")).toHaveValue(model.id),
  );
  expect(
    screen.getByText(
      `配置已保存，已选中“${model.name}”。密钥不会回显；尚未检查服务连接。`,
    ),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "请先添加模型" }),
  ).not.toBeInTheDocument();
  expect(api.saveModel).toHaveBeenCalledOnce();
  expect(api.action).not.toHaveBeenCalled();
});

it("model settings save an explicit cloud key once and clear it from the form", async () => {
  const api = client();
  const saved = deferred<ModelProfile>();
  const onSaved = vi.fn().mockResolvedValue(undefined);
  vi.mocked(api.saveModel).mockReturnValue(saved.promise);
  render(<AIModelSettings models={[]} onSaved={onSaved} client={api} />);
  fireEvent.click(screen.getByText("模型配置"));
  fireEvent.change(screen.getByLabelText("配置名称"), {
    target: { value: "云端测试" },
  });
  fireEvent.change(screen.getByLabelText("服务位置"), {
    target: { value: "cloud" },
  });
  fireEvent.change(screen.getByLabelText("服务地址"), {
    target: { value: "https://api.example.com/v1" },
  });
  fireEvent.change(screen.getByLabelText("模型名称"), {
    target: { value: "cloud-model" },
  });
  fireEvent.change(screen.getByLabelText("API Key（留空保留已有密钥）"), {
    target: { value: "fake" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "模型配置表单" }));
  fireEvent.submit(screen.getByRole("form", { name: "模型配置表单" }));
  expect(api.saveModel).toHaveBeenCalledExactlyOnceWith(
    {
      name: "云端测试",
      kind: "cloud",
      base_url: "https://api.example.com/v1",
      model: "cloud-model",
      max_output_tokens: 2048,
      api_key: "fake",
    },
    undefined,
  );
  expect(screen.getByLabelText("配置名称")).toBeDisabled();
  await act(async () => {
    saved.resolve({
      ...model,
      id: "cloud-profile",
      kind: "cloud",
      has_key: true,
    });
    await saved.promise;
  });
  expect(screen.getByLabelText("API Key（留空保留已有密钥）")).toHaveValue("");
  expect(onSaved).toHaveBeenCalledOnce();
  expect(screen.getByRole("status")).toHaveTextContent(
    `配置已保存，已选中“${model.name}”。密钥不会回显`,
  );
});

it("model settings clear hidden keys on service changes and validate output budgets", async () => {
  const api = client();
  const cloud = { ...model, kind: "cloud" as const, has_key: true };
  render(
    <AIModelSettings
      models={[cloud]}
      onSaved={vi.fn().mockResolvedValue(undefined)}
      client={api}
    />,
  );
  fireEvent.click(screen.getByText("模型配置"));
  fireEvent.click(screen.getByRole("button", { name: "编辑 测试模型" }));
  fireEvent.change(screen.getByLabelText("API Key（留空保留已有密钥）"), {
    target: { value: "fake" },
  });
  fireEvent.click(screen.getByRole("checkbox", { name: "移除已保存密钥" }));
  expect(screen.getByLabelText("API Key（留空保留已有密钥）")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("API Key（留空保留已有密钥）"), {
    target: { value: "other-key" },
  });
  expect(
    screen.getByRole("checkbox", { name: "移除已保存密钥" }),
  ).not.toBeChecked();
  fireEvent.change(screen.getByLabelText("服务位置"), {
    target: { value: "local" },
  });
  fireEvent.change(screen.getByLabelText("每次输出 Token 上限"), {
    target: { value: "99999" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "模型配置表单" }));
  expect(api.saveModel).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("1–16384");
  fireEvent.change(screen.getByLabelText("每次输出 Token 上限"), {
    target: { value: "2048" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "模型配置表单" }));
  await waitFor(() => expect(api.saveModel).toHaveBeenCalledOnce());
  expect(vi.mocked(api.saveModel).mock.calls[0][0]).not.toHaveProperty(
    "api_key",
  );
});

it("workflow transport supplies session proof, version preconditions and a stable adoption key", async () => {
  vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
    csrfToken: "workflow-proof",
    expiresAtMilliseconds: 10000,
  });
  const request = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(JSON.stringify(adopted), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", request);
  await aiWorkflowClient.candidate(
    chapterId,
    "candidate-one",
    "adopt",
    "adoption-key",
    1,
  );
  const [url, options] = request.mock.calls[0];
  expect(url).toBe(
    `/api/v1/chapters/${chapterId}/ai/candidates/candidate-one/adopt`,
  );
  expect(options?.method).toBe("POST");
  expect(options?.credentials).toBe("same-origin");
  expect(new Headers(options?.headers).get("X-CSRF-Token")).toBe(
    "workflow-proof",
  );
  expect(new Headers(options?.headers).get("If-Match")).toBe('"1"');
  expect(JSON.parse(options?.body as string)).toEqual({
    idempotency_key: "adoption-key",
  });
});

it("workflow transport hides private session failures before network requests", async () => {
  vi.spyOn(securitySession, "getValidSession").mockRejectedValue(
    new Error("PRIVATE_SESSION_DETAIL"),
  );
  const request = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", request);
  await expect(
    aiWorkflowClient.action(chapterId, "run-one", "generate"),
  ).rejects.toThrow("连接中断");
  expect(request).not.toHaveBeenCalled();
});

it("prepares persisted context without generation, restores pending candidates, and requires author adoption", async () => {
  const { result, api, content } = setup(
    client([pending]),
    writingClient({
      getChapterContent: vi
        .fn()
        .mockResolvedValue(
          written("甲乙丙丁\n\n" + pending.candidates[0].text, 2),
        ),
    }),
  );
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  expect(result.current.ai.active?.candidates[0].text).toBe(
    pending.candidates[0].text,
  );
  expect(content.updateChapterContent).not.toHaveBeenCalled();
  await act(() => result.current.ai.adopt(pending.candidates[0], false));
  expect(result.current.writing.state.snapshot.version).toBe(2);
  expect(result.current.writing.state.status).toBe("saved");
  expect(content.updateChapterContent).not.toHaveBeenCalled();
  expect(api.action).not.toHaveBeenCalled();
  expect(api.candidate).toHaveBeenCalledExactlyOnceWith(
    chapterId,
    "candidate-one",
    "adopt",
    expect.any(String),
    1,
  );
});

it("explicit prepare saves first, preserves UTF16 selection, and never calls a provider", async () => {
  const { result, api } = setup();
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  act(() => result.current.writing.edit("甲😀乙甲"));
  await act(() =>
    result.current.ai.prepare("rewrite", model.id, "克制", 5, {
      start: 4,
      end: 5,
      text: "甲",
    }),
  );
  expect(api.create).toHaveBeenCalledWith(
    chapterId,
    expect.objectContaining({
      operation: "rewrite",
      selected_text: "甲",
      selection_start: 4,
      selection_end: 5,
      max_steps: 1,
      max_output_characters: 300,
    }),
  );
  expect(api.action).not.toHaveBeenCalled();
});

it("dirty local manuscript prevents adoption", async () => {
  const { result, api } = setup(client([pending]));
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  act(() => result.current.writing.edit("本地修改"));
  await act(() => result.current.ai.adopt(pending.candidates[0], false));
  expect(api.candidate).not.toHaveBeenCalled();
  expect(result.current.writing.state.content).toBe("本地修改");
});

it("failed content read after adoption blocks old autosave until server reload", async () => {
  const api = client([pending]);
  const content = writingClient({
    getChapterContent: vi
      .fn()
      .mockRejectedValueOnce(new Error("read failed"))
      .mockResolvedValue(written("服务器已采纳", 2)),
  });
  const { result } = setup(api, content);
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  await act(() => result.current.ai.adopt(pending.candidates[0], false));
  expect(result.current.writing.state.reloadFailed).toBe(true);
  expect(result.current.writing.state.status).toBe("conflict");
  act(() => result.current.writing.edit("危险的旧覆盖"));
  expect(result.current.writing.state.content).toBe("甲乙丙丁");
  await act(() => result.current.writing.reloadServer());
  expect(result.current.writing.state.content).toBe("服务器已采纳");
  expect(content.updateChapterContent).not.toHaveBeenCalled();
});

it("duplicate adoption clicks send one atomic write", async () => {
  const api = client([pending]);
  const response = deferred<WorkflowRun>();
  vi.mocked(api.candidate).mockReturnValue(response.promise);
  const { result } = setup(
    api,
    writingClient({
      getChapterContent: vi.fn().mockResolvedValue(written("服务器已采纳", 2)),
    }),
  );
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  let first!: Promise<void>;
  act(() => {
    first = result.current.ai.adopt(pending.candidates[0], false);
  });
  await act(() => result.current.ai.adopt(pending.candidates[0], false));
  expect(api.candidate).toHaveBeenCalledTimes(1);
  await act(async () => {
    response.resolve(adopted);
    await first;
  });
  expect(result.current.writing.state.content).toBe("服务器已采纳");
  expect(api.candidate).toHaveBeenCalledTimes(1);
});

it("lost adoption response retains the same idempotency key after an explicit content reload", async () => {
  const api = client([pending]);
  vi.mocked(api.candidate)
    .mockRejectedValueOnce(new Error("连接中断"))
    .mockResolvedValue(adopted);
  const content = writingClient({
    getChapterContent: vi.fn().mockResolvedValue(written("服务器已采纳", 2)),
  });
  const { result } = setup(api, content);
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  await act(() => result.current.ai.adopt(pending.candidates[0], false));
  const firstKey = vi.mocked(api.candidate).mock.calls[0][3];
  expect(result.current.writing.state.reloadFailed).toBe(true);
  await act(() => result.current.ai.adopt(pending.candidates[0], false));
  expect(api.candidate).toHaveBeenCalledTimes(1);
  await act(() => result.current.writing.reloadServer());
  await act(() => result.current.ai.adopt(pending.candidates[0], false));
  expect(api.candidate).toHaveBeenLastCalledWith(
    chapterId,
    "candidate-one",
    "adopt",
    firstKey,
    1,
  );
  expect(content.updateChapterContent).not.toHaveBeenCalled();
});

it("pause during explicit adopt-and-continue suppresses the next generation", async () => {
  const api = client([pending]);
  const response = deferred<WorkflowRun>();
  vi.mocked(api.candidate).mockReturnValue(response.promise);
  vi.mocked(api.action).mockResolvedValue({ ...pending, status: "paused" });
  const { result } = setup(
    api,
    writingClient({
      getChapterContent: vi.fn().mockResolvedValue(written("已采纳", 2)),
    }),
  );
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  let action!: Promise<void>;
  act(() => {
    action = result.current.ai.adopt(pending.candidates[0], true);
  });
  await act(() => result.current.ai.pause());
  await act(async () => {
    response.resolve({ ...adopted, status: "paused" });
    await action;
  });
  expect(api.action).toHaveBeenCalledExactlyOnceWith(
    chapterId,
    "run-one",
    "pause",
  );
});

it("cloud UI requires visible transmission consent before sending", async () => {
  const api = client([
    {
      ...run,
      model_snapshot: {
        ...model,
        kind: "cloud",
        base_url: "https://api.example.com/v1",
      },
    },
  ]);
  function Harness() {
    const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
    return (
      <AIWorkflowAssistant
        chapterId={chapterId}
        writing={writing}
        selection={null}
        client={api}
      />
    );
  }
  render(<Harness />);
  const generate = await screen.findByRole("button", {
    name: "确认发送并生成",
  });
  expect(generate).toBeDisabled();
  expect(
    screen.getByText(/https:\/\/api.example.com\/v1/u),
  ).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "我同意本轮任务向该模型发送上述内容",
    }),
  );
  expect(generate).toBeEnabled();
  fireEvent.click(generate);
  await waitFor(() =>
    expect(api.action).toHaveBeenCalledExactlyOnceWith(
      chapterId,
      "run-one",
      "generate",
    ),
  );
});

it("shows cloud generation progress and errors next to the clicked button and reads persisted failure without retry", async () => {
  const cloudRun: WorkflowRun = {
    ...run,
    model_snapshot: {
      ...model,
      kind: "cloud",
      base_url: "https://api.example.com",
    },
  };
  const failed: WorkflowRun = {
    ...cloudRun,
    status: "interrupted",
    generated_steps: 1,
    last_error: "AIProviderAuthFailed",
  };
  const api = client([cloudRun]);
  vi.mocked(api.list)
    .mockResolvedValueOnce([cloudRun])
    .mockResolvedValue([failed]);
  const response = deferred<WorkflowRun>();
  vi.mocked(api.action).mockReturnValue(response.promise);
  function Harness() {
    const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
    return (
      <AIWorkflowAssistant
        chapterId={chapterId}
        writing={writing}
        selection={null}
        client={api}
      />
    );
  }
  render(<Harness />);
  const generate = await screen.findByRole("button", {
    name: "确认发送并生成",
  });
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "我同意本轮任务向该模型发送上述内容",
    }),
  );
  fireEvent.click(generate);
  const task = within(screen.getByRole("region", { name: "当前AI任务" }));
  expect(task.getByText(/正在发送请求并等待模型回复/u)).toBeVisible();
  expect(generate).toBeDisabled();
  await act(async () => {
    response.reject(
      new AIWritingError("模型服务拒绝了 API Key", "AI_PROVIDER_AUTH_FAILED"),
    );
    await response.promise.catch(() => undefined);
  });
  await waitFor(() =>
    expect(task.getByRole("status")).toHaveTextContent("中断"),
  );
  expect(task.getByRole("alert")).toHaveTextContent("模型服务拒绝了 API Key");
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(task.getByRole("status")).toHaveTextContent("1/5");
  expect(task.getByRole("button", { name: "恢复任务" })).toBeEnabled();
  expect(api.action).toHaveBeenCalledExactlyOnceWith(
    chapterId,
    run.run_id,
    "generate",
  );
  expect(api.list).toHaveBeenCalledTimes(2);
  expect(api.candidate).not.toHaveBeenCalled();
});

it("explains unsaved prose at the send button before any provider request", async () => {
  const api = client([run]);
  function Harness() {
    const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
    return (
      <>
        <button onClick={() => writing.edit("作者尚未保存的修改")}>
          修改正文
        </button>
        <AIWorkflowAssistant
          chapterId={chapterId}
          writing={writing}
          selection={null}
          client={api}
        />
      </>
    );
  }
  render(<Harness />);
  const generate = await screen.findByRole("button", {
    name: "确认发送并生成",
  });
  fireEvent.click(screen.getByRole("button", { name: "修改正文" }));
  fireEvent.click(generate);
  const task = within(screen.getByRole("region", { name: "当前AI任务" }));
  await waitFor(() =>
    expect(task.getByRole("alert")).toHaveTextContent("正文有未保存修改"),
  );
  expect(api.action).not.toHaveBeenCalled();
  expect(api.list).toHaveBeenCalledOnce();
});

it.each(["read-failed", "candidate-saved", "run-missing"])(
  "reconciles a lost generation response safely when %s",
  async (outcome) => {
    const api = client([run]);
    vi.mocked(api.action).mockRejectedValue(new AIWritingError("连接中断"));
    const { result } = setup(api);
    await waitFor(() => expect(result.current.ai.loading).toBe(false));
    if (outcome === "read-failed")
      vi.mocked(api.list).mockRejectedValue(new Error("读取失败"));
    else
      vi.mocked(api.list).mockResolvedValue(
        outcome === "candidate-saved" ? [pending] : [],
      );
    await act(() => result.current.ai.generate());
    expect(result.current.ai.error).toBe("连接中断");
    expect(result.current.ai.errorRunId).toBe(run.run_id);
    expect(result.current.ai.active).toEqual(
      outcome === "candidate-saved" ? pending : run,
    );
    expect(result.current.ai.busy).toBe(false);
    expect(api.action).toHaveBeenCalledOnce();
    expect(api.candidate).not.toHaveBeenCalled();
  },
);

it("refreshes failure after adoption and next generation without duplicating adoption", async () => {
  const api = client([pending]);
  vi.mocked(api.action).mockRejectedValue(new AIWritingError("请求过于频繁"));
  const { result } = setup(
    api,
    writingClient({
      getChapterContent: vi.fn().mockResolvedValue(written("服务器已采纳", 2)),
    }),
  );
  await waitFor(() => expect(result.current.ai.loading).toBe(false));
  vi.mocked(api.list).mockResolvedValue([
    {
      ...adopted,
      status: "interrupted",
      generated_steps: 2,
      last_error: "AIProviderRateLimited",
    },
  ]);
  await act(() => result.current.ai.adopt(pending.candidates[0], true));
  expect(result.current.ai.error).toBe("请求过于频繁");
  expect(result.current.ai.active?.status).toBe("interrupted");
  expect(result.current.ai.active?.generated_steps).toBe(2);
  expect(result.current.writing.state.content).toBe("服务器已采纳");
  expect(api.action).toHaveBeenCalledExactlyOnceWith(
    chapterId,
    run.run_id,
    "generate",
  );
  expect(api.candidate).toHaveBeenCalledOnce();
});

it.each([
  ["AI_PROVIDER_AUTH_FAILED", "API Key"],
  ["AI_PROVIDER_ACCESS_DENIED", "权限"],
  ["AI_PROVIDER_PAYMENT_REQUIRED", "余额"],
  ["AI_PROVIDER_RATE_LIMITED", "频繁"],
  ["AI_PROVIDER_ENDPOINT_INVALID", "地址"],
  ["AI_PROVIDER_REQUEST_REJECTED", "参数"],
  ["AI_PROVIDER_UNAVAILABLE", "网络"],
  ["AI_PROVIDER_INVALID_RESPONSE", "无法读取"],
  ["AI_PROVIDER_TIMEOUT", "超时"],
  ["AI_OUTPUT_LENGTH_INVALID", "200–300"],
  ["MODEL_CREDENTIAL_UNAVAILABLE", "Windows"],
])("preserves safe generation diagnosis for %s", async (code, message) => {
  vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
    csrfToken: "test-proof",
    expiresAtMilliseconds: 10000,
  });
  const request = vi.fn<typeof fetch>().mockResolvedValue(
    new Response(
      JSON.stringify({
        error: {
          code,
          message: "PRIVATE_UPSTREAM_DETAIL",
          details: {},
          suggested_action: null,
          retryable: false,
        },
        request_id: "isolated-request",
      }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    ),
  );
  vi.stubGlobal("fetch", request);
  const failure = aiWorkflowClient.action(chapterId, run.run_id, "generate");
  await expect(failure).rejects.toThrow(message);
  await expect(failure).rejects.toHaveProperty("code", code);
  expect(workflowFailureMessage(code)).toContain(message);
  expect(workflowFailureMessage(code)).not.toContain("PRIVATE_UPSTREAM_DETAIL");
  expect(request).toHaveBeenCalledOnce();
});

it("explains persisted provider failures and safely handles legacy errors", () => {
  expect(workflowFailureMessage("AIProviderAuthFailed")).toContain("API Key");
  expect(workflowFailureMessage("AIProviderRateLimited")).toContain("频繁");
  expect(workflowFailureMessage("PROCESS_INTERRUPTED")).toContain("手动恢复");
});

it("previews the saved rewrite text, exact source excerpt and omitted reason before cloud consent", async () => {
  const rewrite: WorkflowRun = {
    ...run,
    operation: "rewrite",
    selected_text: "任务准备时的选区",
    instruction: "保留情节",
    model_snapshot: {
      ...model,
      kind: "cloud",
      base_url: "https://api.example.com/v1",
    },
    context: {
      ...run.context,
      manifest: {
        ...run.context.manifest,
        sources: [
          ...run.context.manifest.sources,
          {
            source: "outline",
            references: [],
            text: "",
            reason: "相关创作资料",
            omitted_reason: "尚未创建或无匹配内容",
            truncated: false,
          },
        ],
      },
    },
  };
  const api = client([rewrite]);
  function Harness() {
    const writing = useChapterWriting(
      written("此刻已是另一选区"),
      writingClient(),
    );
    return (
      <AIWorkflowAssistant
        chapterId={chapterId}
        writing={writing}
        selection={{ start: 0, end: 2, text: "此刻" }}
        client={api}
      />
    );
  }
  render(<Harness />);
  await screen.findByRole("button", { name: "确认发送并生成" });
  fireEvent.click(screen.getByText("查看本次上下文依据与发送内容"));
  expect(
    screen.getByRole("textbox", { name: "本次发送的改写选区" }),
  ).toHaveValue("任务准备时的选区");
  expect(
    screen.getByRole("textbox", { name: "本次发送的小说上下文" }),
  ).toHaveValue(run.context.text);
  fireEvent.click(screen.getByText("查看各项来源与取舍原因"));
  expect(
    screen.getByText(/小说大纲：未纳入，尚未创建或无匹配内容/u),
  ).toBeVisible();
  expect(screen.getByText(/已固定 1 项来源快照/u)).toBeVisible();
  expect(
    screen.queryByText(new RegExp(chapterId, "u")),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/revision-one/u)).not.toBeInTheDocument();
  expect(api.action).not.toHaveBeenCalled();
});

it("continuation preview contains adopted and pending text and excludes discarded text", async () => {
  const api = client([
    {
      ...pending,
      candidates: [
        ...adopted.candidates,
        {
          ...pending.candidates[0],
          candidate_id: "candidate-two",
          sequence: 2,
          text: "待".repeat(240),
        },
        {
          ...pending.candidates[0],
          candidate_id: "candidate-three",
          sequence: 3,
          status: "discarded",
          text: "弃".repeat(240),
        },
      ],
    },
  ]);
  function Harness() {
    const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
    return (
      <AIWorkflowAssistant
        chapterId={chapterId}
        writing={writing}
        selection={null}
        client={api}
      />
    );
  }
  render(<Harness />);
  await screen.findByRole("button", { name: "追加到正文" });
  fireEvent.click(screen.getByText("查看本次上下文依据与发送内容"));
  expect(
    screen.getByRole("textbox", { name: "下一段随上下文发送的本轮候选" }),
  ).toHaveValue(`${"文".repeat(240)}\n\n${"待".repeat(240)}`);
});

it("cloud confirmation does not transfer to a different restored task", async () => {
  const cloud = {
    ...model,
    kind: "cloud" as const,
    base_url: "https://api.example.com/v1",
  };
  const api = client([{ ...run, model_snapshot: cloud }]);
  function Harness() {
    const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
    return (
      <AIWorkflowAssistant
        chapterId={chapterId}
        writing={writing}
        selection={null}
        client={api}
      />
    );
  }
  render(<Harness />);
  const generate = await screen.findByRole("button", {
    name: "确认发送并生成",
  });
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "我同意本轮任务向该模型发送上述内容",
    }),
  );
  expect(generate).toBeEnabled();
  vi.mocked(api.list).mockResolvedValue([
    { ...run, run_id: "different-run", model_snapshot: cloud },
  ]);
  fireEvent.click(screen.getByRole("button", { name: "刷新协作任务" }));
  await waitFor(() =>
    expect(screen.getByRole("combobox", { name: "已保存的任务" })).toHaveValue(
      "different-run",
    ),
  );
  expect(generate).toBeDisabled();
  expect(
    screen.getByRole("checkbox", {
      name: "我同意本轮任务向该模型发送上述内容",
    }),
  ).not.toBeChecked();
  expect(api.action).not.toHaveBeenCalled();
});

it("rejects foreign ownership, malformed state and unsafe candidate payloads", () => {
  expect(parseWorkflowRun(run, chapterId).context.text).toBe("甲乙丙丁");
  expect(() =>
    parseWorkflowRun({ ...run, chapter_id: "foreign" }, chapterId),
  ).toThrow();
  expect(() =>
    parseWorkflowRun(
      { ...run, operation: "rewrite", selected_text: "" },
      chapterId,
    ),
  ).toThrow();
  expect(() =>
    parseWorkflowRun(
      {
        ...run,
        context: {
          ...run.context,
          manifest: {
            ...run.context.manifest,
            sources: [
              {
                ...run.context.manifest.sources[0],
                references: [["only-one-id"]],
              },
            ],
          },
        },
      },
      chapterId,
    ),
  ).toThrow();
  expect(() =>
    parseWorkflowRun({ ...run, status: "auto-adopt" }, chapterId),
  ).toThrow();
  expect(() =>
    parseWorkflowRun(
      {
        ...pending,
        candidates: [{ ...pending.candidates[0], character_count: 500 }],
      },
      chapterId,
    ),
  ).toThrow();
  expect(() =>
    parseWorkflowRun(
      { ...run, model_snapshot: { ...model, api_key: "should-not-echo" } },
      chapterId,
    ),
  ).toThrow();
});

it("explains an old database upgrade without hiding the cause behind refresh", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            error: {
              code: "AI_WORKFLOW_SCHEMA_REQUIRED",
              message: "Database upgrade required.",
              suggested_action: null,
              details: {},
              retryable: false,
            },
            request_id: "upgrade-test",
          }),
          { status: 503, headers: { "Content-Type": "application/json" } },
        ),
      ),
    ),
  );
  const { result } = renderHook(() => {
    const writing = useChapterWriting(written("已有正文"), writingClient());
    return useAIWorkflow(chapterId, writing, aiWorkflowClient);
  });
  await waitFor(() =>
    expect(result.current.error).toContain("当前数据库需要升级"),
  );
  expect(result.current.error).toContain("手动写作仍可使用");
});
