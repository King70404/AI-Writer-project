import { useEffect, useRef } from "react";

import type { ReviseProjectController } from "../hooks/useReviseProject";

interface ProjectConflictPanelProps {
  readonly controller: ReviseProjectController;
}

export function ProjectConflictPanel({
  controller,
}: ProjectConflictPanelProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const state = controller.state;

  useEffect(() => {
    if (state.kind === "conflict") {
      headingRef.current?.focus();
    }
  }, [state.kind]);

  if (state.kind !== "conflict") {
    return null;
  }
  const conflict = state.conflict;
  const latest = conflict.latestResource;

  return (
    <section
      className="project-conflict"
      aria-labelledby="project-conflict-title"
      role="alert"
    >
      <h3 id="project-conflict-title" ref={headingRef} tabIndex={-1}>
        检测到版本冲突
      </h3>
      <p>
        当前草稿基于版本 {conflict.expectedVersion}，服务端已处于版本{" "}
        {conflict.actualVersion}。草稿尚未保存，也没有被覆盖。
      </p>
      {conflict.requestId === null ? null : (
        <p className="request-id">请求编号：{conflict.requestId}</p>
      )}
      {conflict.latestStatus === "idle" ? (
        <button type="button" onClick={() => void controller.loadLatest()}>
          读取最新版本
        </button>
      ) : null}
      {conflict.latestStatus === "loading" ? (
        <p role="status">正在读取最新版本…</p>
      ) : null}
      {conflict.latestStatus === "error" && conflict.latestError !== null ? (
        <div className="project-conflict__latest-error">
          <p>{conflict.latestError.message}</p>
          {conflict.latestError.requestId === null ? null : (
            <p className="request-id">
              请求编号：{conflict.latestError.requestId}
            </p>
          )}
          <button type="button" onClick={() => void controller.loadLatest()}>
            重试读取最新版本
          </button>
        </div>
      ) : null}
      {latest === null ? null : (
        <div className="project-conflict__comparison">
          <section aria-labelledby="latest-project-preview-title">
            <h4 id="latest-project-preview-title">服务端最新版本</h4>
            <p className="project-conflict__preview-title">
              {latest.project.title}
            </p>
            <p className="project-conflict__preview-description">
              {latest.project.description.length === 0
                ? "暂无项目简介。"
                : latest.project.description}
            </p>
          </section>
          <section aria-labelledby="local-project-draft-title">
            <h4 id="local-project-draft-title">当前本地草稿</h4>
            <p className="project-conflict__preview-title">
              {conflict.draft.title}
            </p>
            <p className="project-conflict__preview-description">
              {conflict.draft.description.length === 0
                ? "暂无项目简介。"
                : conflict.draft.description}
            </p>
          </section>
          <div className="project-conflict__actions">
            <button type="button" onClick={controller.adoptLatest}>
              放弃当前草稿并采用最新版本
            </button>
            <button
              type="button"
              onClick={controller.keepDraftWithLatestBaseline}
            >
              保留草稿并以最新版本建立基线
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
