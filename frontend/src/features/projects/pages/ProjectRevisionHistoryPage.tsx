import { Link, useParams } from "react-router";

import {
  projectApiClient,
  type ProjectRevisionHistoryApiClient,
} from "../api/client";
import {
  ProjectRevisionHistoryError,
  ProjectRevisionHistoryInvalid,
  ProjectRevisionHistoryLoading,
} from "../components/ProjectRevisionHistoryStates";
import { ProjectRevisionHistoryList } from "../components/ProjectRevisionHistoryList";
import { ProjectRevisionViewer } from "../components/ProjectRevisionViewer";
import { useProjectRevisionHistory } from "../hooks/useProjectRevisionHistory";
import { projectDetailsPath } from "../routing";

interface ProjectRevisionHistoryPageProps {
  readonly client?: ProjectRevisionHistoryApiClient;
}

function ProjectRevisionHistoryRoute({
  projectId,
  client,
}: {
  readonly projectId: string | undefined;
  readonly client: ProjectRevisionHistoryApiClient;
}) {
  const controller = useProjectRevisionHistory(projectId, client);
  const selectedRevisionNumber =
    controller.viewer.status === "idle"
      ? null
      : controller.viewer.revisionNumber;
  const history = controller.history;

  return (
    <section
      className="project-revision-history"
      aria-labelledby="project-revision-history-title"
    >
      <header className="project-revision-history__header">
        <div>
          <p className="section-kicker">小说 · 只读历史</p>
          <h2 id="project-revision-history-title">小说修订历史</h2>
        </div>
        {history.status !== "invalid" && projectId !== undefined ? (
          <Link to={projectDetailsPath(projectId)}>返回小说详情</Link>
        ) : (
          <Link to="/projects">返回小说列表</Link>
        )}
      </header>

      {history.status === "invalid" ? <ProjectRevisionHistoryInvalid /> : null}
      {history.status === "loading" ? <ProjectRevisionHistoryLoading /> : null}
      {history.status === "not_found" && history.error !== null ? (
        <ProjectRevisionHistoryError error={history.error} notFound />
      ) : null}
      {history.status === "error" && history.error !== null ? (
        <ProjectRevisionHistoryError
          error={history.error}
          onRetry={() => void controller.reload()}
        />
      ) : null}
      {history.status === "ready" ? (
        <div className="project-revision-history__content">
          <ProjectRevisionHistoryList
            items={history.items}
            selectedRevisionNumber={selectedRevisionNumber}
            hasMore={history.hasMore}
            loadMoreStatus={history.loadMoreStatus}
            loadMoreError={history.loadMoreError}
            onSelect={(number) => void controller.selectRevision(number)}
            onLoadMore={() => void controller.loadMore()}
          />
          <ProjectRevisionViewer
            state={controller.viewer}
            onRetry={() => void controller.retrySelectedRevision()}
          />
        </div>
      ) : null}
    </section>
  );
}

export function ProjectRevisionHistoryPage({
  client = projectApiClient,
}: ProjectRevisionHistoryPageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <ProjectRevisionHistoryRoute
      key={projectId ?? "missing-project-id"}
      projectId={projectId}
      client={client}
    />
  );
}
