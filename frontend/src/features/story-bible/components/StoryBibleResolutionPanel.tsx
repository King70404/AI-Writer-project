import { useEffect, useRef } from "react";

import type { StoryBibleController } from "../hooks/useStoryBible";

export function StoryBibleResolutionPanel({
  controller,
}: {
  readonly controller: StoryBibleController;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const state = controller.state;
  const resolution =
    state.status === "ready" && state.save.kind === "resolution"
      ? state.save.resolution
      : null;

  useEffect(() => {
    if (resolution !== null) {
      headingRef.current?.focus();
    }
  }, [resolution]);

  if (resolution === null) {
    return null;
  }
  const latest = resolution.latestResource;

  return (
    <section
      className="story-bible-resolution"
      aria-labelledby="story-bible-resolution-title"
      role="alert"
    >
      <h3 id="story-bible-resolution-title" ref={headingRef} tabIndex={-1}>
        {resolution.reason === "conflict"
          ? "检测到 Story Bible 版本冲突"
          : "Story Bible 保存结果未确认"}
      </h3>
      <p>{resolution.message}</p>
      {resolution.reason === "conflict" ? (
        <p>
          当前草稿基于版本 {resolution.expectedVersion}，服务端已处于版本{" "}
          {resolution.actualVersion}。草稿尚未保存，也没有被覆盖。
        </p>
      ) : (
        <p>当前草稿和旧基线均已保留；在核实前不会再次发送保存请求。</p>
      )}
      {resolution.requestId === null ? null : (
        <p className="request-id">请求编号：{resolution.requestId}</p>
      )}
      {resolution.latestStatus === "idle" ? (
        <button type="button" onClick={() => void controller.loadLatest()}>
          读取最新版本
        </button>
      ) : null}
      {resolution.latestStatus === "loading" ? (
        <p role="status">正在读取最新版本…</p>
      ) : null}
      {resolution.latestStatus === "error" &&
      resolution.latestError !== null ? (
        <div className="story-bible-resolution__latest-error">
          <p>{resolution.latestError.message}</p>
          {resolution.latestError.requestId === null ? null : (
            <p className="request-id">
              请求编号：{resolution.latestError.requestId}
            </p>
          )}
          <button type="button" onClick={() => void controller.loadLatest()}>
            重试读取最新版本
          </button>
        </div>
      ) : null}
      {latest === null ? null : (
        <div className="story-bible-resolution__comparison">
          <section aria-labelledby="latest-story-bible-title">
            <h4 id="latest-story-bible-title">服务器最新版本</h4>
            <p className="story-bible-resolution__preview-title">
              {latest.storyBible.title}
            </p>
            <pre className="story-bible-resolution__preview-content">
              {latest.storyBible.content}
            </pre>
          </section>
          <section aria-labelledby="local-story-bible-draft-title">
            <h4 id="local-story-bible-draft-title">当前本地草稿</h4>
            <p className="story-bible-resolution__preview-title">
              {resolution.draft.title}
            </p>
            <pre className="story-bible-resolution__preview-content">
              {resolution.draft.content}
            </pre>
          </section>
          <div className="story-bible-resolution__actions">
            <button type="button" onClick={controller.adoptLatest}>
              采用服务器版本
            </button>
            <button
              type="button"
              onClick={controller.keepDraftWithLatestBaseline}
            >
              保留草稿并以服务器版本建立基线
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
