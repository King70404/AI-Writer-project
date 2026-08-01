import { Link, useParams } from "react-router";

import { characterApiClient, type CharacterApiClient } from "../api/client";
import { CharacterCreateForm } from "../components/CharacterCreateForm";
import { CharacterList } from "../components/CharacterList";
import {
  CharacterAlert,
  CharacterErrorAlert,
  CharacterLoading,
} from "../components/CharacterStates";
import { useCharacterList } from "../hooks/useCharacterList";
import { projectDetailsPath } from "../../projects/routing";

function CharacterListRoute({
  projectId,
  client,
}: {
  readonly projectId: string | undefined;
  readonly client: CharacterApiClient;
}) {
  const controller = useCharacterList(projectId, client);
  const state = controller.state;
  return (
    <section className="character-page" aria-labelledby="character-page-title">
      <header className="character-page__header">
        <div>
          <p className="section-kicker">Project · Character</p>
          <h1 id="character-page-title">角色管理</h1>
        </div>
        {projectId === undefined ? null : (
          <Link
            to={
              state.status === "invalid_project"
                ? "/projects"
                : projectDetailsPath(projectId)
            }
          >
            返回Project详情
          </Link>
        )}
      </header>
      {state.status === "invalid_project" ? (
        <CharacterAlert title="Project编号无效" message="无法读取角色列表。" />
      ) : null}
      {state.status === "loading" ? <CharacterLoading /> : null}
      {state.status === "project_not_found" ? (
        <CharacterAlert title="Project不存在" message={state.error.message} />
      ) : null}
      {state.status === "error" ? (
        <CharacterErrorAlert
          error={state.error}
          onRetry={() => void controller.reloadFirstPage()}
        />
      ) : null}
      {projectId === undefined ? null : (
        <>
          <CharacterCreateForm projectId={projectId} controller={controller} />
          <CharacterList projectId={projectId} controller={controller} />
        </>
      )}
    </section>
  );
}

export function CharacterListPage({
  client = characterApiClient,
}: {
  readonly client?: CharacterApiClient;
}) {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <CharacterListRoute
      key={projectId ?? "missing-project"}
      projectId={projectId}
      client={client}
    />
  );
}
