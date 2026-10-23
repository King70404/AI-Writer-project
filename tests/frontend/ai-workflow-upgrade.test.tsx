import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { securitySession } from "../../frontend/src/api/security-session";
import { AIWritingError } from "../../frontend/src/features/novel-structure/api/ai-writing";
import {
  aiWorkflowClient,
  type AIWorkflowClient,
  type ModelProfile,
} from "../../frontend/src/features/novel-structure/api/ai-workflow";
import { AIWorkflowAssistant } from "../../frontend/src/features/novel-structure/components/AIWorkflowAssistant";
import { useAIWorkflow } from "../../frontend/src/features/novel-structure/hooks/useAIWorkflow";
import { useChapterWriting } from "../../frontend/src/features/novel-structure/hooks/useChapterWriting";
import { chapterId } from "./novel-structure-support";
import { deferred, written, writingClient } from "./chapter-writing-support";

const schemaRequired = () =>
  new AIWritingError("当前数据库需要升级", "AI_WORKFLOW_SCHEMA_REQUIRED");
const savedModel: ModelProfile = {
  id: "isolated-model",
  name: "隔离配置",
  kind: "cloud",
  base_url: "https://api.example.com/v1",
  model: "fake-model",
  max_output_tokens: 2048,
  has_key: false,
};
function oldDatabase(): AIWorkflowClient {
  return {
    models: vi.fn().mockRejectedValue(schemaRequired()),
    list: vi.fn().mockRejectedValue(schemaRequired()),
    upgrade: vi.fn().mockResolvedValue(undefined),
    saveModel: vi.fn().mockResolvedValue(savedModel),
    create: vi.fn(),
    action: vi.fn(),
    candidate: vi.fn(),
  };
}
function showAssistant(api: AIWorkflowClient, content = writingClient()) {
  function Harness() {
    const writing = useChapterWriting(written("原有正文"), content);
    return (
      <>
        <textarea
          aria-label="手动正文"
          value={writing.state.content}
          onChange={(event) => writing.edit(event.target.value)}
        />
        <AIWorkflowAssistant
          chapterId={chapterId}
          writing={writing}
          selection={null}
          client={api}
        />
      </>
    );
  }
  return render(<Harness />);
}
function ready(api: AIWorkflowClient) {
  vi.mocked(api.models).mockResolvedValue([]);
  vi.mocked(api.list).mockResolvedValue([]);
}
function fillModel() {
  fireEvent.click(screen.getByText("模型配置"));
  fireEvent.change(screen.getByLabelText("配置名称"), {
    target: { value: savedModel.name },
  });
  fireEvent.change(screen.getByLabelText("服务位置"), {
    target: { value: savedModel.kind },
  });
  fireEvent.change(screen.getByLabelText("服务地址"), {
    target: { value: savedModel.base_url },
  });
  fireEvent.change(screen.getByLabelText("模型名称"), {
    target: { value: savedModel.model },
  });
}
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  securitySession.clear();
});

it("upgrades only after an explicit author click, saves pending prose first, and selects a newly saved model", async () => {
  const api = oldDatabase();
  const content = writingClient();
  vi.mocked(api.upgrade).mockImplementation(() => {
    expect(content.updateChapterContent).toHaveBeenCalledOnce();
    ready(api);
    return Promise.resolve();
  });
  showAssistant(api, content);
  const enable = await screen.findByRole("button", {
    name: "备份并启用 AI 协作",
  });
  expect(
    screen.getByRole("region", { name: "启用 AI 协作" }),
  ).toHaveTextContent("将先在本机保存数据库备份");
  expect(api.upgrade).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "刷新协作任务" }));
  await waitFor(() => expect(api.models).toHaveBeenCalledTimes(2));
  expect(api.upgrade).not.toHaveBeenCalled();
  await waitFor(() => expect(enable).toBeEnabled());
  fireEvent.change(screen.getByLabelText("手动正文"), {
    target: { value: "原有正文及新编辑" },
  });
  fireEvent.click(enable);
  await screen.findByText("AI 协作已启用，可以保存模型配置。");
  expect(api.upgrade).toHaveBeenCalledOnce();
  expect(
    screen.queryByRole("button", { name: "备份并启用 AI 协作" }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("手动正文")).toHaveValue("原有正文及新编辑");
  fillModel();
  fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
  await waitFor(() =>
    expect(screen.getByLabelText("使用模型")).toHaveValue(savedModel.id),
  );
  expect(
    screen.getByText(
      `配置已保存，已选中“${savedModel.name}”。还需填写 API Key 才能向云端发送。`,
    ),
  ).toBeInTheDocument();
  expect(api.saveModel).toHaveBeenCalledOnce();
  expect(api.action).not.toHaveBeenCalled();
  expect(api.create).not.toHaveBeenCalled();
  expect(api.candidate).not.toHaveBeenCalled();
});

it("keeps a retry action after upgrade failure and ignores double clicks without disabling manual writing", async () => {
  const api = oldDatabase();
  const pending = deferred<void>();
  vi.mocked(api.upgrade).mockReturnValueOnce(pending.promise);
  showAssistant(api);
  const enable = await screen.findByRole("button", {
    name: "备份并启用 AI 协作",
  });
  fireEvent.click(enable);
  fireEvent.click(enable);
  await waitFor(() => expect(api.upgrade).toHaveBeenCalledOnce());
  expect(
    screen.getByRole("button", { name: "正在备份并启用…" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("手动正文")).toBeEnabled();
  fireEvent.change(screen.getByLabelText("手动正文"), {
    target: { value: "仍可编辑" },
  });
  await act(() =>
    Promise.resolve(
      pending.reject(
        new AIWritingError("备份失败，请重试", "AI_WORKFLOW_UPGRADE_FAILED"),
      ),
    ),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "备份失败，请重试",
  );
  expect(
    screen.queryByText("AI 协作已启用，可以保存模型配置。"),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("手动正文")).toHaveValue("仍可编辑");
  const retry = screen.getByRole("button", { name: "备份并启用 AI 协作" });
  expect(retry).toBeEnabled();
  vi.mocked(api.upgrade).mockImplementation(() => {
    ready(api);
    return Promise.resolve();
  });
  fireEvent.click(retry);
  await screen.findByText("AI 协作已启用，可以保存模型配置。");
  expect(api.upgrade).toHaveBeenCalledTimes(2);
});

it("does not claim success or hide recovery when post-upgrade reload fails", async () => {
  const api = oldDatabase();
  vi.mocked(api.upgrade).mockImplementation(() => {
    ready(api);
    vi.mocked(api.list).mockRejectedValue(new Error("任务加载失败，请重试"));
    return Promise.resolve();
  });
  showAssistant(api);
  fireEvent.click(
    await screen.findByRole("button", { name: "备份并启用 AI 协作" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("任务加载失败"),
  );
  expect(
    screen.queryByText("AI 协作已启用，可以保存模型配置。"),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "备份并启用 AI 协作" }),
  ).toBeEnabled();
  expect(screen.getByLabelText("手动正文")).toHaveValue("原有正文");
});

it("blocks upgrade when current prose cannot be saved", async () => {
  const api = oldDatabase();
  const content = writingClient({
    updateChapterContent: vi.fn().mockRejectedValue(new Error("save failed")),
  });
  showAssistant(api, content);
  const enable = await screen.findByRole("button", {
    name: "备份并启用 AI 协作",
  });
  fireEvent.change(screen.getByLabelText("手动正文"), {
    target: { value: "待保存的正文" },
  });
  fireEvent.click(enable);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(
      "请先保存当前正文并处理版本冲突",
    ),
  );
  expect(api.upgrade).not.toHaveBeenCalled();
  expect(screen.getByLabelText("手动正文")).toHaveValue("待保存的正文");
});

it("opens recovery for a schema failure first discovered on model save and retains the entered configuration", async () => {
  const api = oldDatabase();
  ready(api);
  vi.mocked(api.saveModel)
    .mockRejectedValueOnce(schemaRequired())
    .mockResolvedValue(savedModel);
  showAssistant(api);
  await waitFor(() =>
    expect(
      screen.queryByText("正在读取模型与已保存任务…"),
    ).not.toBeInTheDocument(),
  );
  fillModel();
  fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "备份并启用 AI 协作" }),
  );
  await screen.findByText("AI 协作已启用，可以保存模型配置。");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByLabelText("配置名称")).toHaveValue(savedModel.name);
  fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
  await waitFor(() =>
    expect(screen.getByLabelText("使用模型")).toHaveValue(savedModel.id),
  );
});

it("keeps recovery visible when only task loading reports the missing schema", async () => {
  const api = oldDatabase();
  vi.mocked(api.models).mockRejectedValue(new Error("model loading failed"));
  const { result } = renderHook(() => {
    const writing = useChapterWriting(written("原有正文"), writingClient());
    return useAIWorkflow(chapterId, writing, api);
  });
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.upgradeRequired).toBe(true);
  expect(api.upgrade).not.toHaveBeenCalled();
});

it("sends explicit backup consent with CSRF proof and rejects malformed success responses", async () => {
  vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
    csrfToken: "isolated-proof",
    expiresAtMilliseconds: 10000,
  });
  const request = vi
    .fn<typeof fetch>()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ready" }), { status: 200 }),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "pending" }), { status: 200 }),
    );
  vi.stubGlobal("fetch", request);
  await aiWorkflowClient.upgrade();
  const [url, options] = request.mock.calls[0];
  expect(url).toBe("/api/v1/ai/workflow-setup/upgrade");
  expect(options?.method).toBe("POST");
  expect(options?.credentials).toBe("same-origin");
  expect(new Headers(options?.headers).get("X-CSRF-Token")).toBe(
    "isolated-proof",
  );
  expect(JSON.parse(options?.body as string)).toEqual({ confirm_backup: true });
  await expect(aiWorkflowClient.upgrade()).rejects.toThrow("无法安全读取");
});

it.each([
  [503, "AI_WORKFLOW_SCHEMA_REQUIRED", "备份并启用 AI 协作"],
  [503, "AI_WORKFLOW_UPGRADE_FAILED", "点击“备份并启用 AI 协作”重试"],
  [409, "AI_WORKFLOW_UPGRADE_UNSUPPORTED", "当前数据库状态不支持自动启用"],
  [409, "AI_WORKFLOW_UPGRADE_BUSY", "数据库正在处理其他写入或启用请求"],
] as const)(
  "preserves %s %s as an actionable typed error",
  async (status, code, message) => {
    vi.spyOn(securitySession, "getValidSession").mockResolvedValue({
      csrfToken: "isolated-proof",
      expiresAtMilliseconds: 10000,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code,
              message: "private backend detail",
              details: {},
              retryable: false,
              suggested_action: null,
            },
            request_id: "upgrade-test",
          }),
          { status },
        ),
      ),
    );
    const failure = aiWorkflowClient.upgrade();
    await expect(failure).rejects.toMatchObject({ code });
    await expect(failure).rejects.toThrow(message);
  },
);
