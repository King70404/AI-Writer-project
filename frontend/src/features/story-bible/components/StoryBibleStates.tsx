import { Link } from "react-router";

import { LoadingState } from "../../../components/LoadingState";
import type { StoryBibleApiError } from "../api/errors";

export function StoryBibleLoading() {
  return <LoadingState message="正在读取 Story Bible…" />;
}

export function StoryBibleInvalidProject() {
  return (
    <div className="story-bible-state" role="alert">
      <h3>项目地址无效</h3>
      <p>项目编号不符合规范，未向服务端发送请求。</p>
      <Link to="/projects">返回项目列表</Link>
    </div>
  );
}

export function StoryBibleProjectNotFound({
  error,
}: {
  readonly error: StoryBibleApiError;
}) {
  return (
    <div className="story-bible-state" role="alert">
      <h3>项目不存在</h3>
      <p>{error.message}</p>
      {error.requestId === null ? null : (
        <p className="request-id">请求编号：{error.requestId}</p>
      )}
      <Link to="/projects">返回项目列表</Link>
    </div>
  );
}

export function StoryBibleLoadError({
  error,
  onRetry,
}: {
  readonly error: StoryBibleApiError;
  readonly onRetry: () => void;
}) {
  return (
    <div className="story-bible-state" role="alert">
      <h3>无法读取 Story Bible</h3>
      <p>{error.message}</p>
      {error.requestId === null ? null : (
        <p className="request-id">请求编号：{error.requestId}</p>
      )}
      <button type="button" onClick={onRetry}>
        重新加载
      </button>
    </div>
  );
}
