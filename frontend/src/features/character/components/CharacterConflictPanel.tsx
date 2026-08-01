import { useEffect, useRef } from "react";

import type { CharacterEditorController } from "../hooks/useCharacterEditor";

export function CharacterConflictPanel({
  controller,
}: {
  readonly controller: CharacterEditorController;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const state = controller.state;
  const resolution =
    state.status === "ready" && state.feedback.status === "resolution"
      ? state.feedback.resolution
      : null;

  useEffect(() => {
    if (resolution !== null) heading.current?.focus();
  }, [resolution]);

  if (resolution === null) return null;
  return (
    <section className="character-conflict" role="alert">
      <h2 ref={heading} tabIndex={-1}>
        {resolution.reason === "version_conflict"
          ? "检测到版本冲突"
          : "保存结果无法确认"}
      </h2>
      {resolution.conflict === null ? null : (
        <p>
          提交版本 {resolution.conflict.expectedVersion}，服务器当前版本{" "}
          {resolution.conflict.actualVersion}。
        </p>
      )}
      <p>本地草稿与旧基线已保留，系统不会自动读取、重试或合并。</p>
      <button
        type="button"
        disabled={resolution.latestStatus === "loading"}
        onClick={() => void controller.loadLatest()}
      >
        {resolution.latestStatus === "loading"
          ? "正在读取…"
          : "读取服务器最新版本"}
      </button>
      {resolution.latestStatus === "error" &&
      resolution.latestError !== null ? (
        <p>{resolution.latestError.message}</p>
      ) : null}
      {resolution.latestStatus === "ready" ? (
        <div>
          <p>
            已读取服务器版本 {resolution.latest?.version}
            。服务器正文不会在此处展示。
          </p>
          <button type="button" onClick={controller.adoptLatest}>
            采用服务器版本
          </button>
          <button
            type="button"
            onClick={controller.keepDraftWithLatestBaseline}
          >
            保留草稿并重建基线
          </button>
        </div>
      ) : null}
    </section>
  );
}
