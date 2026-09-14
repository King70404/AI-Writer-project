import { useEffect, useRef } from "react";

import type { ProjectRevisionViewerState } from "../hooks/useProjectRevisionHistory";
import { formatProjectTimestamp } from "../formatting";

interface ProjectRevisionViewerProps {
  readonly state: ProjectRevisionViewerState;
  readonly onRetry: () => void;
}

export function ProjectRevisionViewer({
  state,
  onRetry,
}: ProjectRevisionViewerProps) {
  const titleRef = useRef<HTMLHeadingElement | null>(null);

  useEffect(() => {
    if (state.status === "ready") {
      titleRef.current?.focus();
    }
  }, [state]);

  return (
    <section
      className="project-revision-viewer"
      aria-labelledby="project-revision-viewer-title"
    >
      <h2 id="project-revision-viewer-title">修订内容</h2>
      {state.status === "idle" ? (
        <p>尚未选择修订，请从列表中查看内容。</p>
      ) : null}
      {state.status === "loading" ? (
        <p role="status" aria-live="polite">
          正在读取修订 {state.revisionNumber}…
        </p>
      ) : null}
      {state.status === "error" ? (
        <div
          className="project-revision-state project-revision-state--error"
          role="alert"
        >
          <p>{state.error.message}</p>
          {state.error.requestId !== null ? (
            <p className="request-id">请求编号：{state.error.requestId}</p>
          ) : null}
          <button type="button" onClick={onRetry}>
            重试读取该修订
          </button>
        </div>
      ) : null}
      {state.status === "ready" ? (
        <article className="project-revision-viewer__content">
          <h3 ref={titleRef} tabIndex={-1}>
            修订 {state.revision.revision_number}：{state.revision.title}
          </h3>
          <dl>
            <div>
              <dt>状态</dt>
              <dd>{state.revision.is_current ? "当前修订" : "历史修订"}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>
                <time dateTime={state.revision.created_at}>
                  {formatProjectTimestamp(state.revision.created_at)}
                </time>
              </dd>
            </div>
          </dl>
          <h4>项目简介</h4>
          <p className="project-revision-viewer__description">
            {state.revision.description.length === 0
              ? "该修订没有项目简介。"
              : state.revision.description}
          </p>
        </article>
      ) : null}
    </section>
  );
}
