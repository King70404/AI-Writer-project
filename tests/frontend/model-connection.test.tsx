import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AIModelSettings } from "../../frontend/src/features/novel-structure/components/AIModelSettings";
import { modelConnectionClient } from "../../frontend/src/features/novel-structure/api/model-connection";

const profile = {
  id: "test",
  name: "测试",
  kind: "local" as const,
  base_url: "http://127.0.0.1:1234/v1",
  model: "fake",
  max_output_tokens: 512,
  has_key: false,
};
afterEach(() => vi.restoreAllMocks());
it("does not probe on mount and checks only after an author click", async () => {
  const check = vi.spyOn(modelConnectionClient, "check").mockResolvedValue({
    status: "verified",
    configuration_version: "version-one",
    model_available: true,
  });
  render(<AIModelSettings models={[profile]} onSaved={vi.fn()} open />);
  expect(check).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "检查连接 测试" }));
  expect(await screen.findByText(/连接已验证/u)).toBeVisible();
  expect(check).toHaveBeenCalledExactlyOnceWith("test");
  check.mockRejectedValueOnce(new Error("private failure must not escape"));
  fireEvent.click(screen.getByRole("button", { name: "检查连接 测试" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("配置仍保留"),
  );
  expect(screen.queryByText(/连接已验证/u)).not.toBeInTheDocument();
  expect(screen.queryByText(/private failure/u)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "编辑 测试" })).toBeEnabled();
});

it("requires another author confirmation before a metered test message", async () => {
  const check = vi
    .spyOn(modelConnectionClient, "check")
    .mockResolvedValueOnce({
      status: "unsupported",
      configuration_version: "frozen-version",
      model_available: false,
    })
    .mockResolvedValueOnce({
      status: "verified",
      configuration_version: "frozen-version",
      model_available: true,
    });
  render(
    <AIModelSettings
      models={[profile]}
      projectId="project"
      onSaved={vi.fn()}
      open
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "检查连接 测试" }));
  expect(
    await screen.findByText(/将发送一条测试消息，可能计费/u),
  ).toBeVisible();
  const send = screen.getByRole("button", { name: "确认发送测试消息 测试" });
  expect(send).toBeDisabled();
  expect(check).toHaveBeenCalledTimes(1);
  fireEvent.click(
    screen.getByRole("checkbox", { name: "我同意发送可能计费的测试消息" }),
  );
  fireEvent.click(send);
  await waitFor(() => expect(check).toHaveBeenCalledTimes(2));
  expect(check).toHaveBeenLastCalledWith("test", {
    confirm_test_message: true,
    configuration_version: "frozen-version",
    project_id: "project",
  });
  expect(await screen.findByText(/连接已验证/u)).toBeVisible();
});

it("never offers a chat test message for an embedding model", async () => {
  const check = vi.spyOn(modelConnectionClient, "check").mockResolvedValue({
    status: "unsupported",
    configuration_version: "embedding-version",
    model_available: false,
  });
  render(
    <AIModelSettings
      models={[{ ...profile, purpose: "embedding" as const }]}
      projectId="project"
      onSaved={vi.fn()}
      open
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "检查连接 测试" }));
  expect(
    await screen.findByText(/嵌入模型不提供测试消息/u),
  ).toBeVisible();
  expect(
    screen.queryByText(/将发送一条测试消息，可能计费/u),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /确认发送测试消息/u }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("checkbox", {
      name: "我同意发送可能计费的测试消息",
    }),
  ).not.toBeInTheDocument();
  expect(check).toHaveBeenCalledExactlyOnceWith("test");
});
