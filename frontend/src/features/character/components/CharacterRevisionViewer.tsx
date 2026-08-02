import { useEffect, useRef } from "react";

import type { CharacterRevisionViewerState } from "../hooks/useCharacterRevisionHistory";

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function CharacterRevisionViewer({
  state,
  onRetry,
}: {
  readonly state: CharacterRevisionViewerState;
  readonly onRetry: () => void;
}) {
  const titleRef = useRef<HTMLHeadingElement | null>(null);
  useEffect(() => {
    if (state.status === "ready") titleRef.current?.focus();
  }, [state]);
  return (
    <section
      className="project-revision-viewer"
      aria-labelledby="character-revision-viewer-title"
    >
      <h2 id="character-revision-viewer-title">角色卡修订内容</h2>
      {state.status === "idle" ? <p>请选择一个修订查看角色卡。</p> : null}
      {state.status === "loading_revision" ? (
        <p role="status" aria-live="polite">
          正在读取修订 {state.revisionNumber}…
        </p>
      ) : null}
      {state.status === "revision_error" ? (
        <div
          className="project-revision-state project-revision-state--error"
          role="alert"
        >
          <p>{state.error.message}</p>
          <button type="button" onClick={onRetry}>
            重试读取该修订
          </button>
        </div>
      ) : null}
      {state.status === "ready" ? (
        <article className="project-revision-viewer__content">
          <h3 ref={titleRef} tabIndex={-1}>
            修订 {state.revision.revision_number}：{state.revision.name}
          </h3>
          <p>
            {state.revision.is_current ? "当前版本" : "历史版本"} ·{" "}
            <time dateTime={state.revision.created_at}>
              {formatTimestamp(state.revision.created_at)}
            </time>
          </p>
          <h4>角色定位</h4>
          <p>{state.revision.role || "未设置角色定位"}</p>
          <h4>角色档案</h4>
          <pre className="story-bible-revision-viewer__content">
            {state.revision.profile}
          </pre>
        </article>
      ) : null}
    </section>
  );
}
