import type { ProjectApiError } from "../api/errors";

export function ProjectRevisionHistoryLoading() {
  return (
    <div className="project-revision-state" role="status" aria-live="polite">
      <p>正在读取修订历史…</p>
    </div>
  );
}

export function ProjectRevisionHistoryInvalid() {
  return (
    <div
      className="project-revision-state project-revision-state--error"
      role="alert"
    >
      <h2>项目地址无效</h2>
      <p>请从项目列表进入修订历史。</p>
    </div>
  );
}

export function ProjectRevisionHistoryError({
  error,
  notFound = false,
  onRetry,
}: {
  readonly error: ProjectApiError;
  readonly notFound?: boolean;
  readonly onRetry?: () => void;
}) {
  return (
    <div
      className="project-revision-state project-revision-state--error"
      role="alert"
    >
      <h2>{notFound ? "项目不存在" : "修订历史读取失败"}</h2>
      <p>{error.message}</p>
      {error.requestId !== null ? (
        <p className="request-id">请求编号：{error.requestId}</p>
      ) : null}
      {onRetry !== undefined ? (
        <button type="button" onClick={onRetry}>
          重新读取历史
        </button>
      ) : null}
    </div>
  );
}
