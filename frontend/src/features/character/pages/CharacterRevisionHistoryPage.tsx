import { Link, useParams } from "react-router";

import {
  characterRevisionHistoryApiClient,
  type CharacterRevisionHistoryApiClient,
} from "../api/history";
import {
  CharacterRevisionHistoryList,
  CharacterRevisionHistoryStatus,
} from "../components/CharacterRevisionHistory";
import { CharacterRevisionViewer } from "../components/CharacterRevisionViewer";
import { useCharacterRevisionHistory } from "../hooks/useCharacterRevisionHistory";
import { characterEditorPath, projectCharactersPath } from "../routing";

function CharacterRevisionHistoryRoute({
  projectId,
  characterId,
  client,
}: {
  readonly projectId: string | undefined;
  readonly characterId: string | undefined;
  readonly client: CharacterRevisionHistoryApiClient;
}) {
  const controller = useCharacterRevisionHistory(
    projectId,
    characterId,
    client,
  );
  const { history, viewer } = controller;
  const selectedRevisionNumber =
    viewer.status === "idle" ? null : viewer.revisionNumber;
  const validNavigation =
    history.status !== "invalid_route" &&
    projectId !== undefined &&
    characterId !== undefined;
  return (
    <section
      className="project-revision-history character-revision-history"
      aria-labelledby="character-revision-history-title"
    >
      <header className="project-revision-history__header">
        <div>
          <p className="section-kicker">Character · 只读历史</p>
          <h1 id="character-revision-history-title">角色修订历史</h1>
          {validNavigation ? (
            <p className="project-revision-history__id">
              角色编号：{characterId}
            </p>
          ) : null}
        </div>
        <nav aria-label="角色历史导航">
          {validNavigation ? (
            <>
              <Link to={characterEditorPath(projectId, characterId)}>
                返回当前角色
              </Link>{" "}
              <Link to={projectCharactersPath(projectId)}>返回角色列表</Link>
            </>
          ) : (
            <Link to="/projects">返回项目列表</Link>
          )}
        </nav>
      </header>
      {history.status === "invalid_route" ? (
        <CharacterRevisionHistoryStatus kind="invalid_route" />
      ) : null}
      {history.status === "loading_history" ? (
        <CharacterRevisionHistoryStatus kind="loading_history" />
      ) : null}
      {history.status === "character_not_found" ? (
        <CharacterRevisionHistoryStatus
          kind="character_not_found"
          error={history.error ?? undefined}
        />
      ) : null}
      {history.status === "project_mismatch" ? (
        <CharacterRevisionHistoryStatus kind="project_mismatch" />
      ) : null}
      {history.status === "empty" ? (
        <CharacterRevisionHistoryStatus kind="empty" />
      ) : null}
      {history.status === "error" ? (
        <CharacterRevisionHistoryStatus
          kind="error"
          error={history.error ?? undefined}
          onRetry={() => void controller.reload()}
        />
      ) : null}
      {history.status === "ready" ? (
        <div className="project-revision-history__content">
          <CharacterRevisionHistoryList
            items={history.items}
            selectedRevisionNumber={selectedRevisionNumber}
            hasMore={history.hasMore}
            loadMoreStatus={history.loadMoreStatus}
            loadMoreError={history.loadMoreError}
            onSelect={(revisionNumber) =>
              void controller.selectRevision(revisionNumber)
            }
            onLoadMore={() => void controller.loadMore()}
            onReload={() => void controller.reload()}
          />
          <CharacterRevisionViewer
            state={viewer}
            onRetry={() => void controller.retrySelectedRevision()}
          />
        </div>
      ) : null}
    </section>
  );
}

export function CharacterRevisionHistoryPage({
  client = characterRevisionHistoryApiClient,
}: {
  readonly client?: CharacterRevisionHistoryApiClient;
}) {
  const { projectId, characterId } = useParams<{
    projectId: string;
    characterId: string;
  }>();
  return (
    <CharacterRevisionHistoryRoute
      key={`${projectId ?? "missing-project"}:${characterId ?? "missing-character"}`}
      projectId={projectId}
      characterId={characterId}
      client={client}
    />
  );
}
