import { Link, useParams } from "react-router";

import { projectStoryBiblePath } from "../../projects/routing";
import {
  storyBibleApiClient,
  storyBibleRevisionHistoryApiClient,
  type StoryBibleApiClient,
  type StoryBibleRevisionHistoryApiClient,
} from "../api/client";
import {
  StoryBibleRevisionHistoryList,
  StoryBibleRevisionHistoryStatus,
  StoryBibleRevisionViewer,
} from "../components/StoryBibleRevisionHistory";
import { useStoryBibleRevisionHistory } from "../hooks/useStoryBibleRevisionHistory";

interface StoryBibleRevisionHistoryPageProps {
  readonly currentClient?: StoryBibleApiClient;
  readonly historyClient?: StoryBibleRevisionHistoryApiClient;
}

function StoryBibleRevisionHistoryRoute({
  projectId,
  currentClient,
  historyClient,
}: {
  readonly projectId: string | undefined;
  readonly currentClient: StoryBibleApiClient;
  readonly historyClient: StoryBibleRevisionHistoryApiClient;
}) {
  const controller = useStoryBibleRevisionHistory(
    projectId,
    currentClient,
    historyClient,
  );
  const history = controller.history;
  const selectedRevisionNumber =
    controller.viewer.status === "idle"
      ? null
      : controller.viewer.revisionNumber;
  return (
    <section
      className="project-revision-history story-bible-revision-history"
      aria-labelledby="story-bible-revision-history-title"
    >
      <header className="project-revision-history__header">
        <div>
          <p className="section-kicker">Story Bible · 只读历史</p>
          <h2 id="story-bible-revision-history-title">Story Bible 修订历史</h2>
          {history.storyBibleId === null ? null : (
            <p className="project-revision-history__id">
              Story Bible 编号：{history.storyBibleId}
            </p>
          )}
        </div>
        {projectId === undefined || history.status === "invalid" ? (
          <Link to="/projects">返回项目列表</Link>
        ) : (
          <Link to={projectStoryBiblePath(projectId)}>
            返回 Story Bible 编辑页
          </Link>
        )}
      </header>
      {history.status === "invalid" ? (
        <StoryBibleRevisionHistoryStatus kind="invalid" />
      ) : null}
      {history.status === "loading" ? (
        <StoryBibleRevisionHistoryStatus kind="loading" />
      ) : null}
      {history.status === "not_found" ? (
        <StoryBibleRevisionHistoryStatus
          kind="not_found"
          error={history.error ?? undefined}
        />
      ) : null}
      {history.status === "error" ? (
        <StoryBibleRevisionHistoryStatus
          kind="error"
          error={history.error ?? undefined}
          onRetry={() => void controller.reload()}
        />
      ) : null}
      {history.status === "ready" ? (
        <div className="project-revision-history__content">
          <StoryBibleRevisionHistoryList
            items={history.items}
            selectedRevisionNumber={selectedRevisionNumber}
            hasMore={history.hasMore}
            loadMoreStatus={history.loadMoreStatus}
            loadMoreError={history.loadMoreError}
            onSelect={(revisionNumber) =>
              void controller.selectRevision(revisionNumber)
            }
            onLoadMore={() => void controller.loadMore()}
          />
          <StoryBibleRevisionViewer
            state={controller.viewer}
            onRetry={() => void controller.retrySelectedRevision()}
          />
        </div>
      ) : null}
    </section>
  );
}

export function StoryBibleRevisionHistoryPage({
  currentClient = storyBibleApiClient,
  historyClient = storyBibleRevisionHistoryApiClient,
}: StoryBibleRevisionHistoryPageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <StoryBibleRevisionHistoryRoute
      key={projectId ?? "missing-project-id"}
      projectId={projectId}
      currentClient={currentClient}
      historyClient={historyClient}
    />
  );
}
