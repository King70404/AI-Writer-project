import type { CharacterRevisionHistoryItemResponse } from "../api/contracts";
import type { CharacterApiError } from "../api/errors";

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function CharacterRevisionHistoryStatus({
  kind,
  error,
  onRetry,
}: {
  readonly kind:
    | "invalid_route"
    | "loading_history"
    | "character_not_found"
    | "project_mismatch"
    | "empty"
    | "error";
  readonly error?: CharacterApiError;
  readonly onRetry?: () => void;
}) {
  if (kind === "loading_history") {
    return (
      <div className="project-revision-state" role="status" aria-live="polite">
        <p>正在读取角色修订历史…</p>
      </div>
    );
  }
  const title = {
    invalid_route: "角色地址无效",
    character_not_found: "角色不存在",
    project_mismatch: "Project归属不匹配",
    empty: "暂无修订记录",
    error: "修订历史读取失败",
  }[kind];
  return (
    <div
      className="project-revision-state project-revision-state--error"
      role="alert"
    >
      <h2>{title}</h2>
      <p>
        {kind === "invalid_route"
          ? "请从角色列表重新进入修订历史。"
          : kind === "project_mismatch"
            ? "该角色不属于当前路由中的Project，内容不会显示。"
            : kind === "empty"
              ? "服务端没有返回任何可读修订。"
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

export function CharacterRevisionHistoryList({
  items,
  selectedRevisionNumber,
  hasMore,
  loadMoreStatus,
  loadMoreError,
  onSelect,
  onLoadMore,
  onReload,
}: {
  readonly items: readonly CharacterRevisionHistoryItemResponse[];
  readonly selectedRevisionNumber: number | null;
  readonly hasMore: boolean;
  readonly loadMoreStatus: "idle" | "loading_more" | "load_more_error";
  readonly loadMoreError: CharacterApiError | null;
  readonly onSelect: (revisionNumber: number) => void;
  readonly onLoadMore: () => void;
  readonly onReload: () => void;
}) {
  return (
    <section
      className="project-revision-history__list"
      aria-labelledby="character-revision-list-title"
    >
      <h2 id="character-revision-list-title">修订记录</h2>
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
                {item.is_current ? "当前版本" : "历史版本"}
              </span>
            </div>
            <p className="project-revision-card__title">{item.name}</p>
            <p>{item.role || "未设置角色定位"}</p>
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
              查看此修订
            </button>
          </li>
        ))}
      </ol>
      {hasMore ? (
        <button
          className="project-revision-list__more"
          type="button"
          disabled={loadMoreStatus === "loading_more"}
          onClick={onLoadMore}
        >
          {loadMoreStatus === "loading_more" ? "正在加载…" : "加载更多"}
        </button>
      ) : (
        <p className="project-revision-list__end">已显示全部可读修订。</p>
      )}
      {loadMoreStatus === "load_more_error" && loadMoreError !== null ? (
        <div
          className="project-revision-state project-revision-state--error"
          role="alert"
        >
          <p>{loadMoreError.message}</p>
          <button type="button" onClick={onLoadMore}>
            重试加载更多
          </button>
          {loadMoreError.kind === "invalid_cursor" ? (
            <button type="button" onClick={onReload}>
              重新加载第一页
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
