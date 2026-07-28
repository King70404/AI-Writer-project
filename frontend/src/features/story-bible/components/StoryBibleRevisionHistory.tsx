import { useEffect, useRef } from "react";

import type { StoryBibleRevisionHistoryItemResponse } from "../api/contracts";
import type { StoryBibleApiError } from "../api/errors";
import type { StoryBibleRevisionViewerState } from "../hooks/useStoryBibleRevisionHistory";

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function StoryBibleRevisionHistoryStatus({
  kind,
  error,
  onRetry,
}: {
  readonly kind: "invalid" | "loading" | "not_found" | "error";
  readonly error?: StoryBibleApiError;
  readonly onRetry?: () => void;
}) {
  if (kind === "loading") {
    return (
      <div className="project-revision-state" role="status" aria-live="polite">
        <p>正在读取 Story Bible 修订历史…</p>
      </div>
    );
  }
  return (
    <div
      className="project-revision-state project-revision-state--error"
      role="alert"
    >
      <h2>
        {kind === "invalid"
          ? "项目地址无效"
          : kind === "not_found"
            ? "Story Bible 不存在"
            : "修订历史读取失败"}
      </h2>
      <p>
        {kind === "invalid"
          ? "请从项目详情进入 Story Bible 修订历史。"
          : (error?.message ?? "无法读取修订历史。")}
      </p>
      {error?.requestId !== null && error?.requestId !== undefined ? (
        <p className="request-id">请求编号：{error.requestId}</p>
      ) : null}
      {onRetry === undefined ? null : (
        <button type="button" onClick={onRetry}>
          重新读取历史
        </button>
      )}
    </div>
  );
}

export function StoryBibleRevisionHistoryList({
  items,
  selectedRevisionNumber,
  hasMore,
  loadMoreStatus,
  loadMoreError,
  onSelect,
  onLoadMore,
}: {
  readonly items: readonly StoryBibleRevisionHistoryItemResponse[];
  readonly selectedRevisionNumber: number | null;
  readonly hasMore: boolean;
  readonly loadMoreStatus: "idle" | "loading" | "error";
  readonly loadMoreError: StoryBibleApiError | null;
  readonly onSelect: (revisionNumber: number) => void;
  readonly onLoadMore: () => void;
}) {
  return (
    <section
      className="project-revision-history__list"
      aria-labelledby="story-bible-revision-list-title"
    >
      <h2 id="story-bible-revision-list-title">修订记录</h2>
      <ol className="project-revision-list">
        {items.map((item) => (
          <li className="project-revision-card" key={item.revision_id}>
            <div className="project-revision-card__heading">
              <h3>修订 {item.revision_number}</h3>
              <span
                className={
                  item.is_current
                    ? "project-revision-card__current"
                    : "project-revision-card__historical"
                }
              >
                {item.is_current ? "当前修订" : "历史修订"}
              </span>
            </div>
            <p className="project-revision-card__title">{item.title}</p>
            <p>
              创建时间：
              <time dateTime={item.created_at}>
                {formatTimestamp(item.created_at)}
              </time>
            </p>
            <button
              type="button"
              aria-pressed={selectedRevisionNumber === item.revision_number}
              onClick={() => onSelect(item.revision_number)}
            >
              {selectedRevisionNumber === item.revision_number
                ? "重新查看正文"
                : "查看正文"}
            </button>
          </li>
        ))}
      </ol>
      {hasMore ? (
        <button
          className="project-revision-list__more"
          type="button"
          disabled={loadMoreStatus === "loading"}
          onClick={onLoadMore}
        >
          {loadMoreStatus === "loading" ? "正在加载…" : "加载更多"}
        </button>
      ) : (
        <p className="project-revision-list__end">已显示全部可读修订。</p>
      )}
      {loadMoreStatus === "error" && loadMoreError !== null ? (
        <div
          className="project-revision-state project-revision-state--error"
          role="alert"
        >
          <p>{loadMoreError.message}</p>
          <button type="button" onClick={onLoadMore}>
            重试加载更多
          </button>
        </div>
      ) : null}
    </section>
  );
}

export function StoryBibleRevisionViewer({
  state,
  onRetry,
}: {
  readonly state: StoryBibleRevisionViewerState;
  readonly onRetry: () => void;
}) {
  const titleRef = useRef<HTMLHeadingElement | null>(null);
  useEffect(() => {
    if (state.status === "ready") {
      titleRef.current?.focus();
    }
  }, [state]);
  return (
    <section
      className="project-revision-viewer"
      aria-labelledby="story-bible-revision-viewer-title"
    >
      <h2 id="story-bible-revision-viewer-title">修订正文</h2>
      {state.status === "idle" ? (
        <p>尚未选择修订。列表不会预先下载正文。</p>
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
          <p>
            {state.revision.is_current ? "当前修订" : "历史修订"} ·{" "}
            <time dateTime={state.revision.created_at}>
              {formatTimestamp(state.revision.created_at)}
            </time>
          </p>
          <h4>Story Bible 正文</h4>
          <pre className="story-bible-revision-viewer__content">
            {state.revision.content}
          </pre>
        </article>
      ) : null}
    </section>
  );
}
