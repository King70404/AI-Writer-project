import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExternalHandoff } from "../../frontend/src/features/external-handoff/ExternalHandoff";
import type {
  HandoffClient,
  Handoff,
} from "../../frontend/src/features/external-handoff/client";
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
function setup() {
  const api: HandoffClient = {
    preview: vi.fn().mockResolvedValue({ ...task, handoff_id: null }),
    create: vi.fn().mockResolvedValue(task),
    list: vi.fn().mockResolvedValue([task]),
    download: vi.fn().mockResolvedValue(new Blob()),
    candidate: vi.fn().mockResolvedValue(candidate),
    adopt: vi.fn().mockResolvedValue(undefined),
  };
  const commit = vi.fn(async (call: () => Promise<void>) => {
    await call();
    return true;
  });
  const writing = {
    flush: vi.fn().mockResolvedValue(true),
    acceptExternal: commit,
    state: { status: "saved", content: "作者原文", snapshot: { etag: '"1"' } },
  } as unknown as ReturnType<typeof useChapterWriting>;
  render(<ExternalHandoff chapterId="ch1" writing={writing} client={api} />);
  fireEvent.click(screen.getByRole("button", { name: "外部 AI 交接" }));
  return { api, writing, commit };
}
beforeEach(() => localStorage.clear());
describe("外部交接", () => {
  it("预览仅选定的正文并确认保存，默认不发送原文", async () => {
    const { api } = setup();
    await screen.findByLabelText("选择已有交接任务");
    fireEvent.change(screen.getByLabelText("本次任务说明"), {
      target: { value: "续写" },
    });
    fireEvent.click(screen.getByRole("button", { name: "预览交接内容" }));
    await screen.findByText("确认交接内容");
    expect(api.preview).toHaveBeenCalledWith("ch1", {
      instruction: "续写",
      include_manuscript: false,
    });
    expect(api.create).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认保存交接任务" }));
    await waitFor(() =>
      expect(api.create).toHaveBeenCalledWith("ch1", {
        instruction: "续写",
        include_manuscript: false,
        context_sha256: "hash",
      }),
    );
  });
  it("导入候选不改变正文，采用必须由作者确认", async () => {
    const { api, commit } = setup();
    const select = await screen.findByLabelText("选择已有交接任务");
    fireEvent.change(select, { target: { value: "h1" } });
    fireEvent.change(screen.getByLabelText("粘贴外部返回正文"), {
      target: { value: "外部候选" },
    });
    fireEvent.click(screen.getByRole("button", { name: "导入为外部候选" }));
    await screen.findByRole("region", { name: "外部候选对照" });
    expect(api.adopt).not.toHaveBeenCalled();
    expect(commit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认追加候选到正文" }));
    await waitFor(() => expect(api.adopt).toHaveBeenCalledOnce());
    expect(commit).toHaveBeenCalledOnce();
  });
});
