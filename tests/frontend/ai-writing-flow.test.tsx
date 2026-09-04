import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { AIWritingAssistant } from "../../frontend/src/features/novel-structure/components/AIWritingAssistant";
import { useChapterWriting } from "../../frontend/src/features/novel-structure/hooks/useChapterWriting";
import {
  appendCandidate,
  useAIWriting,
  type SelectionSnapshot,
} from "../../frontend/src/features/novel-structure/hooks/useAIWriting";
import {
  AIWritingError,
  type AICandidate,
  type AIWritingClient,
} from "../../frontend/src/features/novel-structure/api/ai-writing";
import { chapterId, structureError } from "./novel-structure-support";
import {
  deferred,
  flushReact,
  written,
  writingClient,
} from "./chapter-writing-support";

beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }));
afterEach(() => vi.useRealTimers());
const proposal = (
  operation: "continue" | "rewrite" = "continue",
): AICandidate => ({
  operation,
  text: "候选正文",
  model: "local-model",
  context: {
    included_sources: ["current_chapter"],
    omitted_sources: [],
    truncated: true,
    character_count: 100,
  },
});
function aiClient(): AIWritingClient {
  return {
    continueChapter: vi.fn().mockResolvedValue(proposal()),
    rewriteChapterText: vi.fn().mockResolvedValue(proposal("rewrite")),
  };
}
const selection = { start: 1, end: 3, text: "乙丙" };
function setup(client = writingClient(), ai = aiClient()) {
  const hook = renderHook(() => {
    const writing = useChapterWriting(written("甲乙丙丁"), client);
    return { writing, ai: useAIWriting(chapterId, writing, ai) };
  });
  return { ...hook, client, provider: ai };
}

it("generates from saved content, serializes requests, never adopts automatically and discards without PUT", async () => {
  const pending = deferred<AICandidate>();
  const provider = aiClient();
  vi.mocked(provider.continueChapter).mockReturnValue(pending.promise);
  const { result, client } = setup(writingClient(), provider);
  let work!: Promise<void>;
  act(() => {
    work = result.current.ai.generate("continue", "克制", null);
  });
  expect(result.current.ai.status).toBe("generating");
  await act(() => result.current.ai.generate("rewrite", "", selection));
  expect(provider.rewriteChapterText).not.toHaveBeenCalled();
  await act(async () => {
    pending.resolve(proposal());
    await work;
  });
  expect(result.current.writing.state.content).toBe("甲乙丙丁");
  expect(result.current.ai.candidate?.result).toEqual(proposal());
  act(() => result.current.ai.discard());
  expect(result.current.ai.status).toBe("idle");
  expect(client.updateChapterContent).not.toHaveBeenCalled();
});
it("flushes edits made during a pending save before issuing one AI request", async () => {
  const first = deferred<ReturnType<typeof written>>();
  const client = writingClient({
    updateChapterContent: vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(written("最新正文", 3)),
  });
  const { result, provider } = setup(client);
  act(() => result.current.writing.edit("第一稿"));
  let saving!: Promise<void>;
  act(() => {
    saving = result.current.writing.save();
  });
  let generating!: Promise<void>;
  act(() => {
    generating = result.current.ai.generate("continue", "", null);
  });
  act(() => result.current.writing.edit("最新正文"));
  expect(provider.continueChapter).not.toHaveBeenCalled();
  await act(async () => {
    first.resolve(written("第一稿", 2));
    await saving;
    await generating;
  });
  expect(client.updateChapterContent).toHaveBeenCalledTimes(2);
  expect(vi.mocked(client.updateChapterContent).mock.calls[1][2]).toBe(
    "最新正文",
  );
  expect(vi.mocked(client.updateChapterContent).mock.calls[1][3]).toBe('"2"');
  expect(result.current.writing.state.status).toBe("saved");
  expect(provider.continueChapter).toHaveBeenCalledTimes(1);
});
it("flushes dirty drafts and sends selected text, then guards the original range at adoption", async () => {
  const { result, provider, client } = setup();
  act(() => result.current.writing.edit("甲乙丙丁新"));
  await act(() => result.current.ai.generate("rewrite", "更紧凑", selection));
  expect(provider.rewriteChapterText).toHaveBeenCalledWith(
    chapterId,
    "乙丙",
    "更紧凑",
    expect.any(AbortSignal),
  );
  expect(client.updateChapterContent).toHaveBeenCalledTimes(1);
  act(() => result.current.writing.edit("改乙丙丁新"));
  act(() => result.current.ai.adopt());
  expect(result.current.writing.state.content).toBe("改候选正文丁新");
  expect(result.current.writing.state.status).toBe("dirty");
  await act(() => vi.advanceTimersByTimeAsync(1000));
  expect(client.updateChapterContent).toHaveBeenCalledTimes(2);
  expect(result.current.writing.state.status).toBe("saved");
});
it("rejects changed rewrite range and requires a new generation", async () => {
  const { result } = setup();
  await act(() => result.current.ai.generate("rewrite", "", selection));
  act(() => result.current.writing.edit("甲不同丁"));
  act(() => result.current.ai.adopt());
  expect(result.current.ai.error).toBe(
    "原选中文本已发生变化，请重新选择并生成。",
  );
  expect(result.current.writing.state.content).toBe("甲不同丁");
});
it.each(["error", "conflict"] as const)(
  "blocks generation after save %s without retry or ETag changes",
  async (kind) => {
    const client = writingClient({
      updateChapterContent: vi
        .fn()
        .mockRejectedValue(
          kind === "conflict"
            ? structureError("conflict", "冲突")
            : new Error("private"),
        ),
    });
    const { result, provider } = setup(client);
    act(() => result.current.writing.edit("必须保留"));
    await act(() => result.current.ai.generate("continue", "", null));
    expect(result.current.writing.state.status).toBe(kind);
    expect(result.current.writing.state.snapshot.etag).toBe('"1"');
    expect(result.current.ai.error).toBe("请先保存当前正文后再使用AI。");
    expect(provider.continueChapter).not.toHaveBeenCalled();
    await act(() => result.current.ai.generate("continue", "", null));
    expect(client.updateChapterContent).toHaveBeenCalledTimes(1);
  },
);
it.each([
  new AIWritingError("本地AI生成超时，请稍后重试。"),
  new Error("private"),
])(
  "preserves draft, ETag and save state after AI failure %#",
  async (error) => {
    const provider = aiClient();
    vi.mocked(provider.continueChapter).mockRejectedValue(error);
    const { result } = setup(writingClient(), provider);
    const before = result.current.writing.state;
    await act(() => result.current.ai.generate("continue", "保留要求", null));
    expect(result.current.writing.state).toBe(before);
    expect(result.current.ai.status).toBe("error");
    expect(result.current.ai.error).not.toContain("private");
  },
);
it.each(["", "一行\n", "一行"])(
  "appends deterministically for %j",
  (content) => {
    expect(appendCandidate(content, "候选")).toBe(
      content === ""
        ? "候选"
        : content.endsWith("\n")
          ? "一行\n候选"
          : "一行\n\n候选",
    );
  },
);
it("appends to the latest draft only on adoption and replaces the sole previous proposal", async () => {
  const { result, client } = setup();
  act(() => result.current.ai.adopt());
  await act(() => result.current.ai.generate("continue", "", null));
  act(() => result.current.writing.edit("生成期间的新稿"));
  act(() => result.current.ai.adopt());
  expect(result.current.writing.state.content).toBe(
    "生成期间的新稿\n\n候选正文",
  );
  expect(client.updateChapterContent).not.toHaveBeenCalled();
  await act(() => vi.advanceTimersByTimeAsync(1000));
  expect(client.updateChapterContent).toHaveBeenCalledTimes(1);
  await act(() => result.current.ai.generate("continue", "", null));
  await act(() =>
    result.current.ai.generate("rewrite", "", { start: 0, end: 1, text: "生" }),
  );
  expect(result.current.ai.candidate?.result.operation).toBe("rewrite");
});
it("rejects empty selections without side effects", async () => {
  const { result, provider } = setup();
  await act(() => result.current.ai.generate("rewrite", "", null));
  await act(() =>
    result.current.ai.generate("rewrite", "", { start: 0, end: 1, text: " " }),
  );
  expect(provider.rewriteChapterText).not.toHaveBeenCalled();
});
it.each(["resolve", "reject", "flush"])(
  "ignores %s after leaving the editor",
  async (kind) => {
    const pending = deferred<AICandidate>();
    const save = deferred<ReturnType<typeof written>>();
    const provider = aiClient();
    vi.mocked(provider.continueChapter).mockReturnValue(pending.promise);
    const { result, unmount } = setup(
      writingClient({
        updateChapterContent: vi.fn().mockReturnValue(save.promise),
      }),
      provider,
    );
    if (kind === "flush") act(() => result.current.writing.edit("未保存"));
    let work!: Promise<void>;
    await flushReact(() => {
      work = result.current.ai.generate("continue", "", null);
    });
    unmount();
    await act(async () => {
      if (kind === "reject") pending.reject(new Error("private"));
      else pending.resolve(proposal());
      save.resolve(written("未保存", 2));
      await work;
    });
    expect(result.current.ai.candidate).toBeNull();
    const calls = vi.mocked(provider.continueChapter).mock.calls;
    expect(calls).toHaveLength(kind === "flush" ? 0 : 1);
    expect(calls.every((call) => call[2]?.aborted)).toBe(true);
  },
);

it("renders selection, candidate, errors and explicit adoption controls with the real save hook", async () => {
  const provider = aiClient();
  const pending = deferred<AICandidate>();
  vi.mocked(provider.continueChapter).mockReturnValueOnce(pending.promise);
  function Harness() {
    const writing = useChapterWriting(written("甲乙丙丁"), writingClient());
    const [range, setRange] = useState<SelectionSnapshot | null>(null);
    return (
      <>
        <textarea
          aria-label="正文测试"
          value={writing.state.content}
          onChange={(event) => writing.edit(event.target.value)}
          onSelect={(event) => {
            const e = event.currentTarget;
            setRange({
              start: e.selectionStart,
              end: e.selectionEnd,
              text: e.value.slice(e.selectionStart, e.selectionEnd),
            });
          }}
        />
        <AIWritingAssistant
          chapterId={chapterId}
          writing={writing}
          selection={range}
          client={provider}
        />
      </>
    );
  }
  render(<Harness />);
  const editor = screen.getByLabelText<HTMLTextAreaElement>("正文测试");
  expect(screen.getByRole("button", { name: "改写选中文本" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("额外要求（可选）"), {
    target: { value: "更紧凑" },
  });
  await flushReact(() =>
    fireEvent.click(screen.getByRole("button", { name: "续写" })),
  );
  expect(screen.getByRole("button", { name: "续写" })).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("正在保存并生成");
  await flushReact(() => pending.resolve(proposal()));
  expect(editor).toHaveValue("甲乙丙丁");
  expect(screen.getByLabelText("AI候选文本")).toHaveValue("候选正文");
  expect(screen.getByText(/已按预算截断/u)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "追加到正文" }));
  expect(editor).toHaveValue("甲乙丙丁\n\n候选正文");
  editor.setSelectionRange(1, 3);
  fireEvent.select(editor);
  await flushReact(() =>
    fireEvent.click(screen.getByRole("button", { name: "改写选中文本" })),
  );
  fireEvent.click(screen.getByRole("button", { name: "替换选中文本" }));
  expect(editor.value.startsWith("甲候选正文丁")).toBe(true);
  vi.mocked(provider.continueChapter).mockRejectedValueOnce(
    new AIWritingError("本地AI尚未配置。"),
  );
  await flushReact(() =>
    fireEvent.click(screen.getByRole("button", { name: "续写" })),
  );
  expect(screen.getByRole("alert")).toHaveTextContent("本地AI尚未配置");
  expect(screen.getByLabelText("额外要求（可选）")).toHaveValue("更紧凑");
  vi.mocked(provider.continueChapter).mockResolvedValueOnce({
    ...proposal(),
    context: { ...proposal().context, truncated: false },
  });
  await flushReact(() =>
    fireEvent.click(screen.getByRole("button", { name: "续写" })),
  );
  expect(screen.getByText(/未截断/u)).toBeVisible();
  const before = editor.value;
  fireEvent.click(screen.getByRole("button", { name: "丢弃" }));
  expect(editor).toHaveValue(before);
  expect(screen.queryByLabelText("AI候选文本")).toBeNull();
});

it.each([
  new AIWritingError("本地AI尚未配置。"),
  new AIWritingError("无法连接本地AI服务，或AI服务返回了无效响应。"),
  new AIWritingError("本地AI生成超时，请稍后重试。"),
  new Error("private upstream data"),
])(
  "keeps prose and instruction and enables manual retry after UI failure %#",
  async (failure) => {
    const provider = aiClient();
    const client = writingClient();
    vi.mocked(provider.continueChapter).mockRejectedValueOnce(failure);
    function Harness() {
      const writing = useChapterWriting(written("保留正文"), client);
      return (
        <>
          <output aria-label="当前正文">{writing.state.content}</output>
          <AIWritingAssistant
            chapterId={chapterId}
            writing={writing}
            selection={null}
            client={provider}
          />
        </>
      );
    }
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("额外要求（可选）"), {
      target: { value: "保留要求" },
    });
    await flushReact(() =>
      fireEvent.click(screen.getByRole("button", { name: "续写" })),
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "private upstream data",
    );
    expect(screen.getByLabelText("当前正文")).toHaveTextContent("保留正文");
    expect(screen.getByLabelText("额外要求（可选）")).toHaveValue("保留要求");
    expect(screen.getByRole("button", { name: "续写" })).toBeEnabled();
    expect(provider.continueChapter).toHaveBeenCalledTimes(1);
    await flushReact(() =>
      fireEvent.click(screen.getByRole("button", { name: "续写" })),
    );
    expect(provider.continueChapter).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText("AI候选文本")).toHaveValue("候选正文");
    expect(client.updateChapterContent).not.toHaveBeenCalled();
  },
);
