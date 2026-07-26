import type { ProjectRevisionHistoryItemResponse } from "../api/contracts";
import type { ProjectApiError } from "../api/errors";
import { ProjectRevisionHistoryItem } from "./ProjectRevisionHistoryItem";

interface ProjectRevisionHistoryListProps {
  readonly items: readonly ProjectRevisionHistoryItemResponse[];
  readonly selectedRevisionNumber: number | null;
  readonly hasMore: boolean;
  readonly loadMoreStatus: "idle" | "loading" | "error";
  readonly loadMoreError: ProjectApiError | null;
  readonly onSelect: (revisionNumber: number) => void;
  readonly onLoadMore: () => void;
}

export function ProjectRevisionHistoryList({
  items,
  selectedRevisionNumber,
  hasMore,
  loadMoreStatus,
  loadMoreError,
  onSelect,
  onLoadMore,
}: ProjectRevisionHistoryListProps) {
  return (
    <section
      className="project-revision-history__list"
      aria-labelledby="project-revision-history-list-title"
    >
      <h2 id="project-revision-history-list-title">修订记录</h2>
      <ol className="project-revision-list">
        {items.map((item) => (
          <ProjectRevisionHistoryItem
            key={item.revision_id}
            item={item}
            selected={selectedRevisionNumber === item.revision_number}
            onSelect={onSelect}
          />
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
        <p className="project-revision-list__end">
          已显示当前可读取的全部修订。
        </p>
      )}
      {loadMoreStatus === "error" && loadMoreError !== null ? (
        <div
          className="project-revision-state project-revision-state--error"
          role="alert"
        >
          <p>{loadMoreError.message}</p>
          {loadMoreError.requestId !== null ? (
            <p className="request-id">请求编号：{loadMoreError.requestId}</p>
          ) : null}
          <button type="button" onClick={onLoadMore}>
            重试加载更多
          </button>
        </div>
      ) : null}
    </section>
  );
}
