import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { securitySession } from "../../frontend/src/api/security-session";
import {
  aiWorkflowClient,
  type ModelInput,
  type ModelProfile,
} from "../../frontend/src/features/novel-structure/api/ai-workflow";
import { AIModelSettings } from "../../frontend/src/features/novel-structure/components/AIModelSettings";

const input: ModelInput = {
  name: "隔离云端测试",
  kind: "cloud",
  base_url: "https://api.example.com/v1",
  model: "fake-model",
  max_output_tokens: 2048,
  api_key: "fake",
};
const saved: ModelProfile = {
  id: "a".repeat(32),
  name: input.name,
  kind: input.kind,
  base_url: input.base_url,
  model: input.model,
  max_output_tokens: input.max_output_tokens,
  has_key: true,
};

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

it("keeps an unconfirmed model form after network failure and only clears the key after a successful retry", async () => {
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("Failed to fetch"))
    .mockResolvedValueOnce(
      new Response(JSON.stringify(saved), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
  vi.stubGlobal("fetch", fetch);
  const onSaved = vi.fn();
  render(<AIModelSettings models={[]} onSaved={onSaved} />);
  fireEvent.click(screen.getByText("模型配置"));
  fireEvent.change(screen.getByLabelText("配置名称"), {
    target: { value: input.name },
  });
  fireEvent.change(screen.getByLabelText("服务位置"), {
    target: { value: input.kind },
  });
  fireEvent.change(screen.getByLabelText("服务地址"), {
    target: { value: input.base_url },
  });
  fireEvent.change(screen.getByLabelText("模型名称"), {
    target: { value: input.model },
  });
  fireEvent.change(screen.getByLabelText("API Key（留空保留已有密钥）"), {
    target: { value: input.api_key },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/^模型配置保存未确认/u);
  expect(alert).toHaveTextContent("无法连接本机服务");
  expect(alert).not.toHaveTextContent(input.api_key!);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(onSaved).not.toHaveBeenCalled();
  expect(screen.getByLabelText("配置名称")).toHaveValue(input.name);
  expect(screen.getByLabelText("服务位置")).toHaveValue(input.kind);
  expect(screen.getByLabelText("服务地址")).toHaveValue(input.base_url);
  expect(screen.getByLabelText("模型名称")).toHaveValue(input.model);
  expect(screen.getByLabelText("每次输出 Token 上限")).toHaveValue("2048");
  expect(screen.getByLabelText("API Key（留空保留已有密钥）")).toHaveValue(
    input.api_key,
  );

  fireEvent.click(screen.getByRole("button", { name: "保存模型配置" }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledExactlyOnceWith(saved));
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent(
    `配置已保存，已选中“${saved.name}”`,
  );
  expect(screen.getByLabelText("API Key（留空保留已有密钥）")).toHaveValue("");
});

const operations = [
  ["list models", () => aiWorkflowClient.models()],
  ["save a model", () => aiWorkflowClient.saveModel(input)],
] as const;

it.each(operations)(
  "explains a local connection failure when trying to %s",
  async (_name, operation) => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetch);
    await expect(operation()).rejects.toThrow("无法连接本机服务");
    expect(fetch).toHaveBeenCalledOnce();
  },
);

const failures = [
  [503, "MODEL_CREDENTIAL_UNAVAILABLE", "密钥保护"],
  [503, "MODEL_CONFIGURATION_UNAVAILABLE", "配置"],
  [401, "SESSION_REQUIRED", "会话"],
  [403, "CSRF_VALIDATION_FAILED", "会话"],
] as const;

it.each(
  operations.flatMap(([name, operation]) =>
    failures.map(([status, code, message]) => ({
      name,
      operation,
      status,
      code,
      message,
    })),
  ),
)(
  "explains $code when trying to $name",
  async ({ operation, status, code, message }) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code,
              message: "Deliberately generic test response.",
              details: {},
              retryable: false,
              suggested_action: null,
            },
            request_id: "model-save-error-test",
          }),
          { status, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    await expect(operation()).rejects.toThrow(message);
  },
);
