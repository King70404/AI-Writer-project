import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../frontend/src/api/errors";
import { ExternalHandoff } from "../../frontend/src/features/external-handoff/ExternalHandoff";
import type {
  Handoff,
  HandoffClient,
} from "../../frontend/src/features/external-handoff/client";
import { storyMemoryClient } from "../../frontend/src/features/novel-structure/api/story-memory";
import { writingPreparationClient } from "../../frontend/src/features/novel-structure/api/writing-preparation";
import type { useChapterWriting } from "../../frontend/src/features/novel-structure/hooks/useChapterWriting";

const task: Handoff = {
  handoff_id: "h1",
  chapter_id: "ch1",
  base_version: 1,
  context_sha256: "hash",
  context: "本章原文",
  candidates: [],
};
const candidate = {
  candidate_id: "c1",
  text: "外部候选",
  status: "pending" as const,
  base_version: 1,
};

function apiError(code: string): ApiError {
  return new ApiError({
    status: 409,
    code,
    message: "server text",
    details: {},
    retryable: false,
    suggestedAction: null,
    requestId: null,
  });
}

function setup(
  overrides: Partial<HandoffClient> = {},
  writingOverrides: { flush?: boolean; accept?: boolean } = {},
) {
  const api: HandoffClient = {
    preview: vi.fn().mockResolvedValue({ ...task, handoff_id: null }),
    create: vi.fn().mockResolvedValue(task),
    list: vi.fn().mockResolvedValue([task]),
    download: vi.fn().mockResolvedValue(new Blob(["zip"])),
    candidate: vi.fn().mockResolvedValue(candidate),
    adopt: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  const writing = {
    flush: vi.fn().mockResolvedValue(writingOverrides.flush ?? true),
    acceptExternal: vi.fn(async (call: () => Promise<void>) => {
      await call();
      return writingOverrides.accept ?? true;
    }),
    state: {
      status: "saved",
      content: "作者原文",
      snapshot: { etag: '"1"', resource: { project_id: "prj1" } },
    },
  } as unknown as ReturnType<typeof useChapterWriting>;
  render(<ExternalHandoff chapterId="ch1" writing={writing} client={api} />);
  fireEvent.click(screen.getByRole("button", { name: "外部 AI 交接" }));
  return { api, writing };
}

async function selectTask() {
  const select = await screen.findByLabelText("选择已有交接任务");
  fireEvent.change(select, { target: { value: "h1" } });
}

function chooseFile(file: File) {
  fireEvent.change(screen.getByLabelText("或选择外部返回文件"), {
    target: { files: [file] },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("外部交接异常与边界", () => {
  it("列表读取失败给出提示，收起后可再次展开", async () => {
    setup({ list: vi.fn().mockRejectedValue(new Error("x")) });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "无法读取本章交接任务",
    );
    fireEvent.click(screen.getByRole("button", { name: "收起外部 AI 交接" }));
    expect(
      screen.getByRole("button", { name: "外部 AI 交接" }),
    ).toHaveAttribute("aria-expanded", "false");
  });

  it.each([
    ["HANDOFF_CHANGED", "正文或选中的来源已变化"],
    ["HANDOFF_TOO_LARGE", "交接内容超过长度限制"],
    ["HANDOFF_NOT_FOUND", "交接任务不存在"],
    ["IMPORT_UNAVAILABLE", "当前数据库需要升级"],
    ["OTHER", "预览失败，请重试。"],
  ])("预览错误 %s 显示作者可读说明", async (code, text) => {
    setup({ preview: vi.fn().mockRejectedValue(apiError(code)) });
    await screen.findByLabelText("选择已有交接任务");
    fireEvent.click(screen.getByRole("button", { name: "预览交接内容" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByText("server text")).not.toBeInTheDocument();
  });

  it("正文未保存时不预览", async () => {
    const { api } = setup({}, { flush: false });
    await screen.findByLabelText("选择已有交接任务");
    fireEvent.click(screen.getByRole("button", { name: "预览交接内容" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "请先保存正文并解决冲突。",
    );
    expect(api.preview).not.toHaveBeenCalled();
  });

  it("勾选包含正文；保存未返回编号或失败时提示", async () => {
    const { api } = setup({
      create: vi
        .fn()
        .mockResolvedValueOnce({ ...task, handoff_id: null })
        .mockRejectedValueOnce(new Error("断开")),
    });
    await screen.findByLabelText("选择已有交接任务");
    fireEvent.click(screen.getByLabelText("包含当前章节已保存正文"));
    fireEvent.change(screen.getByLabelText("本次任务说明"), {
      target: { value: "改写" },
    });
    fireEvent.click(screen.getByRole("button", { name: "预览交接内容" }));
    await screen.findByText("确认交接内容");
    expect(screen.getByText(/4 字符/u)).toBeInTheDocument();
    expect(vi.mocked(api.preview).mock.calls[0][1].include_manuscript).toBe(
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "确认保存交接任务" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "未能保存交接任务。",
    );
    fireEvent.click(screen.getByRole("button", { name: "确认保存交接任务" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("断开"),
    );
  });

  it("可选资料读取失败或没有规划；取消勾选后不再发送", async () => {
    const plan = vi
      .spyOn(writingPreparationClient, "plan")
      .mockRejectedValueOnce(new Error("x"))
      .mockResolvedValueOnce(null);
    vi.spyOn(writingPreparationClient, "rules").mockResolvedValue([
      { id: "r1", title: "叙事", version: 2 },
    ] as Awaited<ReturnType<typeof writingPreparationClient.rules>>);
    vi.spyOn(storyMemoryClient, "workspace").mockResolvedValue({
      facts: [
        {
          revision_id: "f1",
          title: "人物",
          version: 3,
          status: "confirmed",
          stale: false,
        },
        {
          revision_id: "f3",
          title: "待确认",
          version: 1,
          status: "proposed",
          stale: false,
        },
      ],
    } as unknown as Awaited<ReturnType<typeof storyMemoryClient.workspace>>);
    const { api } = setup();
    await screen.findByLabelText("选择已有交接任务");
    const read = screen.getByRole("button", {
      name: "读取可选规划、规则和事实",
    });
    fireEvent.click(read);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "无法读取可选资料",
    );
    fireEvent.click(read);
    expect(await screen.findByText("本章没有已保存规划。")).toBeVisible();
    expect(screen.queryByText(/待确认/u)).not.toBeInTheDocument();
    const rule = screen.getByLabelText("写作规则：叙事 · 版本 2");
    const fact = screen.getByLabelText("已确认事实：人物 · 版本 3");
    fireEvent.click(rule);
    fireEvent.click(fact);
    fireEvent.click(rule);
    fireEvent.click(fact);
    fireEvent.click(screen.getByRole("button", { name: "预览交接内容" }));
    await screen.findByText("确认交接内容");
    expect(vi.mocked(api.preview).mock.calls[0][1]).toMatchObject({
      rule_revision_ids: [],
      fact_revision_ids: [],
    });
    expect(plan).toHaveBeenCalledTimes(2);
  });

  it("下载交接包成功生成文件，失败时提示", async () => {
    const create = vi.fn(() => "blob:x");
    const revoke = vi.fn();
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke }),
    );
    const filenames: string[] = [];
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        filenames.push(this.download);
      });
    const { api } = setup();
    await selectTask();
    fireEvent.click(screen.getByRole("button", { name: "下载交接包" }));
    await waitFor(() => expect(click).toHaveBeenCalledOnce());
    expect(filenames).toEqual(["handoff.zip"]);
    expect(revoke).toHaveBeenCalledWith("blob:x");
    vi.mocked(api.download).mockRejectedValueOnce(new Error("交接包下载失败"));
    fireEvent.click(screen.getByRole("button", { name: "下载交接包" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "交接包下载失败",
    );
    vi.unstubAllGlobals();
  });

  it("来源变化的候选显示待重新核对且不提供采用操作", async () => {
    setup({
      list: vi.fn().mockResolvedValue([
        {
          ...task,
          candidates: [{ ...candidate, status: "needs_recheck" as const }],
        },
      ]),
    });
    await selectTask();
    expect(await screen.findByRole("status")).toHaveTextContent("待重新核对");
    expect(
      screen.queryByRole("button", { name: "确认追加候选到正文" }),
    ).not.toBeInTheDocument();
  });

  it("返回文件：超限、非 UTF-8、JSON 原样、TXT 填入正文", async () => {
    const { api } = setup();
    await selectTask();
    chooseFile(new File(["x".repeat(256 * 1024 + 1)], "big.json"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "返回文件超过 256 KiB",
    );
    chooseFile(new File([new Uint8Array([0xff, 0xfe, 0xfd])], "bad.txt"));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "文件不是有效的 UTF-8。",
      ),
    );
    chooseFile(new File(["正文片段"], "reply.txt"));
    await waitFor(() =>
      expect(screen.getByLabelText("粘贴外部返回正文")).toHaveValue("正文片段"),
    );
    const raw = '{"format_version":1,"text":"x"}';
    chooseFile(new File([raw], "reply.JSON"));
    expect(
      await screen.findByText("已读取 JSON 返回文件，提交时会校验任务归属。"),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "导入为外部候选" }));
    await waitFor(() =>
      expect(api.candidate).toHaveBeenCalledWith("ch1", "h1", raw),
    );
  });

  it("粘贴超长、导入失败与刷新失败分别提示", async () => {
    const { api } = setup();
    await selectTask();
    const box = screen.getByLabelText("粘贴外部返回正文");
    fireEvent.change(box, { target: { value: "字".repeat(90_000) } });
    fireEvent.click(screen.getByRole("button", { name: "导入为外部候选" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "返回内容超过 256 KiB",
    );
    expect(api.candidate).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: "外部候选" } });
    vi.mocked(api.candidate).mockRejectedValueOnce(new Error("导入失败：格式"));
    fireEvent.click(screen.getByRole("button", { name: "导入为外部候选" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("导入失败：格式"),
    );
    vi.mocked(api.list).mockRejectedValueOnce(new Error("x"));
    fireEvent.click(screen.getByRole("button", { name: "导入为外部候选" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "候选已导入，但列表刷新失败",
      ),
    );
  });

  it("采用失败保留候选；采用后刷新失败仍显示已采用", async () => {
    const { api } = setup({}, { accept: false });
    await selectTask();
    fireEvent.change(screen.getByLabelText("粘贴外部返回正文"), {
      target: { value: "外部候选" },
    });
    fireEvent.click(screen.getByRole("button", { name: "导入为外部候选" }));
    const adopt = await screen.findByRole("button", {
      name: "确认追加候选到正文",
    });
    fireEvent.click(adopt);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "采用未完成：正文或来源可能已经改变",
    );
    expect(
      screen.getByRole("region", { name: "外部候选对照" }),
    ).toHaveTextContent("外部候选");
    expect(api.adopt).toHaveBeenCalledOnce();
  });

  it("已有候选的任务直接显示对照；采用后刷新失败给出提示", async () => {
    const withCandidate = { ...task, candidates: [candidate] };
    const { api } = setup({
      list: vi
        .fn()
        .mockResolvedValueOnce([withCandidate])
        .mockRejectedValueOnce(new Error("x")),
    });
    await selectTask();
    const region = await screen.findByRole("region", { name: "外部候选对照" });
    expect(region).toHaveTextContent("作者原文");
    fireEvent.click(screen.getByRole("button", { name: "确认追加候选到正文" }));
    expect(await screen.findByText("已采用")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "候选已采用，但列表刷新失败",
    );
    expect(vi.mocked(api.adopt).mock.calls[0][3]).toBe('"1"');
  });
});
