import { LoadingState } from "../../../components/LoadingState";
import type { ProjectApiError } from "../api/errors";

export function ProjectListLoading() {
  return <LoadingState message="正在读取项目列表。" />;
}

export function ProjectListEmpty() {
  return (
    <div className="project-list-state" role="status">
      <h3>还没有项目</h3>
      <p>使用上方表单创建第一个真实 Project。</p>
    </div>
  );
}

interface ProjectListErrorProps {
  readonly error: ProjectApiError;
  readonly onRetry: () => void;
  readonly retryLabel: string;
}

export function ProjectListError({
  error,
  onRetry,
  retryLabel,
}: ProjectListErrorProps) {
  return (
    <div className="project-list-state project-list-state--error" role="alert">
      <h3>项目列表暂时无法读取</h3>
      <p>{error.message}</p>
      {error.requestId === null ? null : (
        <p className="request-id">请求编号：{error.requestId}</p>
      )}
      <button type="button" onClick={onRetry}>
        {retryLabel}
      </button>
    </div>
  );
}
