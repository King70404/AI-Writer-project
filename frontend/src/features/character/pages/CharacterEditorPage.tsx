import { Link, useParams } from "react-router";

import { characterApiClient, type CharacterApiClient } from "../api/client";
import { CharacterConflictPanel } from "../components/CharacterConflictPanel";
import { CharacterEditor } from "../components/CharacterEditor";
import { CharacterMetadata } from "../components/CharacterMetadata";
import {
  CharacterAlert,
  CharacterErrorAlert,
  CharacterLoading,
} from "../components/CharacterStates";
import { useCharacterEditor } from "../hooks/useCharacterEditor";
import {
  characterRevisionHistoryPath,
  projectCharactersPath,
} from "../routing";
import { NotFoundPage } from "../../../pages/NotFoundPage";

function CharacterEditorRoute({
  projectId,
  characterId,
  client,
}: {
  readonly projectId: string | undefined;
  readonly characterId: string | undefined;
  readonly client: CharacterApiClient;
}) {
  const controller = useCharacterEditor(projectId, characterId, client);
  const state = controller.state;
  return (
    <section className="character-page" aria-labelledby="character-page-title">
      <header className="character-page__header">
        <div>
          <p className="section-kicker">角色 · 当前版本</p>
          <h1 id="character-page-title">
            {state.status === "ready"
              ? state.baseline.resource.name
              : "角色编辑"}
          </h1>
        </div>
        {projectId === undefined ? null : (
          <nav aria-label="角色编辑导航">
            {state.status === "ready" && characterId !== undefined ? (
              <Link to={characterRevisionHistoryPath(projectId, characterId)}>
                查看修订历史
              </Link>
            ) : null}{" "}
            <Link
              to={
                state.status === "invalid_route"
                  ? "/projects"
                  : projectCharactersPath(projectId)
              }
            >
              返回角色列表
            </Link>
          </nav>
        )}
      </header>
      {state.status === "invalid_route" ? (
        <CharacterAlert title="角色地址无效" message="请从角色列表重新进入。" />
      ) : null}
      {state.status === "loading" ? (
        <CharacterLoading message="正在读取角色…" />
      ) : null}
      {state.status === "character_not_found" ? (
        <CharacterAlert title="角色不存在" message={state.error.message} />
      ) : null}
      {state.status === "project_mismatch" ? (
        <CharacterAlert
          title="Project归属不匹配"
          message="该角色不属于当前路由中的Project，内容不会显示。"
        />
      ) : null}
      {state.status === "error" ? (
        <CharacterErrorAlert
          error={state.error}
          onRetry={() => void controller.reload()}
        />
      ) : null}
      {state.status === "ready" ? (
        <>
          <CharacterMetadata character={state.baseline.resource} />
          <CharacterEditor controller={controller} />
          <CharacterConflictPanel controller={controller} />
        </>
      ) : null}
    </section>
  );
}

export function CharacterEditorPage({
  client = characterApiClient,
}: {
  readonly client?: CharacterApiClient;
}) {
  const { projectId, characterId } = useParams<{
    projectId: string;
    characterId: string;
  }>();
  if (characterId === "history") {
    return <NotFoundPage />;
  }
  return (
    <CharacterEditorRoute
      key={`${projectId ?? "missing-project"}:${characterId ?? "missing-character"}`}
      projectId={projectId}
      characterId={characterId}
      client={client}
    />
  );
}
