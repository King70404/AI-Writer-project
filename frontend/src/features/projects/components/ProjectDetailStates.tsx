import { Link } from "react-router";

import { LoadingState } from "../../../components/LoadingState";
import type { ProjectApiError } from "../api/errors";

export function ProjectDetailLoading() {
  return <LoadingState message="正在读取项目详情…" />;
}

export function ProjectDetailInvalid() {
  return (
    <div className="project-detail-state" role="alert">
      <h3>项目地址无效</h3>
      <p>项目编号不符合规范，未向服务端发送请求。</p>
      <Link to="/projects">返回项目列表</Link>
    </div>
  );
}

interface ProjectDetailErrorProps {
  readonly error: ProjectApiError;
  readonly notFound?: boolean;
  readonly onRetry?: () => void;
}

export function ProjectDetailError({
  error,
  notFound = false,
  onRetry,
}: ProjectDetailErrorProps) {
  return (
    <div className="project-detail-state" role="alert">
      <h3>{notFound ? "项目不存在" : "无法读取项目详情"}</h3>
      <p>{error.message}</p>
      {error.requestId === null ? null : (
        <p className="request-id">请求编号：{error.requestId}</p>
      )}
      <div className="project-detail-state__actions">
        {onRetry === undefined ? null : (
          <button type="button" onClick={onRetry}>
            重新加载项目
          </button>
        )}
        <Link to="/projects">返回项目列表</Link>
      </div>
    </div>
  );
}
