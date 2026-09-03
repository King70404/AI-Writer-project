import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHAPTER_AUTOSAVE_MS,
  useChapterWriting,
} from "../../frontend/src/features/novel-structure/hooks/useChapterWriting";
import type { VersionedChapterContent } from "../../frontend/src/features/novel-structure/api/contracts";
import { structureError } from "./novel-structure-support";
import {
  flushReact,
  deferred,
  written,
  writingClient,
} from "./chapter-writing-support";

beforeEach(() => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }));
afterEach(() => vi.useRealTimers());
const tick = async (milliseconds = CHAPTER_AUTOSAVE_MS) => {
  await act(() => vi.advanceTimersByTimeAsync(milliseconds));
};

describe("serial Chapter autosave", () => {
  it("marks dirty immediately, debounces edits, normalizes newlines, and stores the returned ETag", async () => {
    const client = writingClient();
    const { result } = renderHook(() => useChapterWriting(written(), client));
    expect(result.current.state.status).toBe("saved");
    await act(() => result.current.save());
    expect(client.updateChapterContent).not.toHaveBeenCalled();
    act(() => result.current.edit("甲\r\n乙"));
    expect(result.current.state.status).toBe("dirty");
    await tick(999);
    expect(client.updateChapterContent).not.toHaveBeenCalled();
    act(() => result.current.edit("甲\r乙丙"));
    await tick(999);
    expect(client.updateChapterContent).not.toHaveBeenCalled();
    await tick(1);
    expect(client.updateChapterContent).toHaveBeenCalledTimes(1);
    expect(result.current.state.content).toBe("甲\n乙丙");
    expect(result.current.state.snapshot.etag).toBe('"2"');
    expect(result.current.state.status).toBe("saved");
    act(() => result.current.edit("下一稿"));
    await act(() => result.current.save());
    expect(client.updateChapterContent).toHaveBeenLastCalledWith(
      expect.any(String),
      expect.any(String),
      "下一稿",
      '"2"',
      expect.any(AbortSignal),
    );
    await tick(5000);
    expect(client.updateChapterContent).toHaveBeenCalledTimes(2);
  });

  it("never overlaps requests or reports saved while newer typing is pending", async () => {
    const first = deferred<VersionedChapterContent>();
    const write = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce(written("版本B", 3));
    const { result } = renderHook(() =>
      useChapterWriting(
        written(),
        writingClient({ updateChapterContent: write }),
      ),
    );
    act(() => result.current.edit("版本A"));
    await tick();
    expect(result.current.state.status).toBe("saving");
    act(() => result.current.edit("版本B"));
    await act(() => result.current.save());
    await act(() => result.current.reloadServer());
    await tick(5000);
    expect(write).toHaveBeenCalledTimes(1);
    await flushReact(() => first.resolve(written("版本A", 2)));
    expect(result.current.state.content).toBe("版本B");
    expect(result.current.state.status).toBe("dirty");
    await tick();
    expect(write).toHaveBeenCalledTimes(2);
    expect(write.mock.calls[1][3]).toBe('"2"');
    expect(result.current.state.status).toBe("saved");
    expect(result.current.state.content).toBe("版本B");
  });

  it("stops on 412, retains all local typing, and explicitly reloads server content and ETag", async () => {
    const reload = deferred<VersionedChapterContent>();
    const client = writingClient({
      updateChapterContent: vi
        .fn()
        .mockRejectedValue(structureError("conflict", "安全冲突")),
      getChapterContent: vi.fn().mockReturnValue(reload.promise),
    });
    const { result } = renderHook(() =>
      useChapterWriting(written("旧正文"), client),
    );
    act(() => result.current.edit("本地正文"));
    await tick();
    expect(result.current.state.status).toBe("conflict");
    act(() => result.current.edit("继续保留本地正文"));
    await act(() => result.current.save());
    await tick(5000);
    expect(client.updateChapterContent).toHaveBeenCalledTimes(1);
    expect(result.current.state.content).toBe("继续保留本地正文");
    let reloading!: Promise<void>;
    act(() => {
      reloading = result.current.reloadServer();
    });
    expect(result.current.state.reloading).toBe(true);
    act(() => result.current.edit("不得插入"));
    await act(() => result.current.save());
    await act(() => result.current.reloadServer());
    expect(client.getChapterContent).toHaveBeenCalledTimes(1);
    await act(async () => {
      reload.resolve(written("服务器版本", 8));
      await reloading;
    });
    expect(result.current.state.content).toBe("服务器版本");
    expect(result.current.state.snapshot.etag).toBe('"8"');
    expect(result.current.state.status).toBe("saved");
  });

  it("keeps error drafts without automatic retries and allows manual or edit-driven retry", async () => {
    const write = vi
      .fn()
      .mockRejectedValueOnce(new Error("private"))
      .mockResolvedValueOnce(written("重试", 2))
      .mockRejectedValueOnce(structureError("unavailable", "失败"))
      .mockResolvedValueOnce(written("新编辑", 3));
    const { result } = renderHook(() =>
      useChapterWriting(
        written(),
        writingClient({ updateChapterContent: write }),
      ),
    );
    act(() => result.current.edit("重试"));
    await tick();
    expect(result.current.state.status).toBe("error");
    expect(result.current.state.content).toBe("重试");
    await tick(5000);
    expect(write).toHaveBeenCalledTimes(1);
    await act(() => result.current.save());
    expect(result.current.state.status).toBe("saved");
    act(() => result.current.edit("出错"));
    await tick();
    expect(result.current.state.status).toBe("error");
    act(() => result.current.edit("新编辑"));
    await tick();
    expect(result.current.state.status).toBe("saved");
    expect(write).toHaveBeenCalledTimes(4);
  });

  it("retains conflict on failed reload or changed ownership", async () => {
    const get = vi
      .fn()
      .mockRejectedValueOnce(new Error("private"))
      .mockResolvedValueOnce({
        ...written(),
        resource: { ...written().resource, volume_id: "other-volume" },
      });
    const { result } = renderHook(() =>
      useChapterWriting(
        written("本地"),
        writingClient({ getChapterContent: get }),
      ),
    );
    act(() => result.current.edit("保留"));
    await act(() => result.current.reloadServer());
    expect(result.current.state.reloadFailed).toBe(true);
    expect(result.current.state.content).toBe("保留");
    await act(() => result.current.reloadServer());
    expect(result.current.state.reloadFailed).toBe(true);
    expect(result.current.state.content).toBe("保留");
  });

  it("guards beforeunload only while unsaved and cancels its timer on unmount", async () => {
    const client = writingClient();
    const { result, unmount } = renderHook(() =>
      useChapterWriting(written(), client),
    );
    const saved = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(saved);
    expect(saved.defaultPrevented).toBe(false);
    act(() => result.current.edit("正文"));
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
    await tick();
    const resaved = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(resaved);
    expect(resaved.defaultPrevented).toBe(false);
    act(() => result.current.edit("未发出的稿"));
    unmount();
    await tick();
    expect(client.updateChapterContent).toHaveBeenCalledTimes(1);
  });

  it.each(["save-success", "save-error", "reload-success", "reload-error"])(
    "ignores %s after unmount",
    async (scenario) => {
      const pending = deferred<VersionedChapterContent>();
      const client = writingClient({
        updateChapterContent: vi.fn().mockReturnValue(pending.promise),
        getChapterContent: vi.fn().mockReturnValue(pending.promise),
      });
      const { result, unmount } = renderHook(() =>
        useChapterWriting(written(), client),
      );
      act(() => result.current.edit("离开前的稿"));
      let work!: Promise<void>;
      act(() => {
        work = scenario.startsWith("save")
          ? result.current.save()
          : result.current.reloadServer();
      });
      const before = result.current.state;
      const savedCallback = result.current.save;
      unmount();
      await act(async () => {
        if (scenario.endsWith("success")) pending.resolve(written("服务端", 2));
        else pending.reject(new Error("private"));
        await work;
        await savedCallback();
      });
      expect(result.current.state).toBe(before);
      const operation = scenario.startsWith("save")
        ? client.updateChapterContent
        : client.getChapterContent;
      expect(operation).toHaveBeenCalledTimes(1);
    },
  );
});
