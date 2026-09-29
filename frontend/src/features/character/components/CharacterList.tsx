import type { CharacterListController } from "../hooks/useCharacterList";

import { CharacterListItem } from "./CharacterListItem";

export function CharacterList({
  projectId,
  controller,
}: {
  readonly projectId: string;
  readonly controller: CharacterListController;
}) {
  const state = controller.state;
  if (state.status !== "ready" && state.status !== "empty") return null;
  if (state.status === "empty") {
    return (
      <section aria-labelledby="character-list-title">
        <h2 id="character-list-title">角色列表</h2>
        <p>这部小说尚未创建角色。</p>
      </section>
    );
  }
  return (
    <section aria-labelledby="character-list-title">
      <h2 id="character-list-title">角色列表</h2>
      <ul className="character-list">
        {state.items.map((character) => (
          <CharacterListItem
            key={character.character_id}
            projectId={projectId}
            character={character}
          />
        ))}
      </ul>
      {state.listError === null ? null : (
        <div role="alert" className="character-alert">
          <p>{state.listError.message}</p>
          {state.listError.kind === "invalid_cursor" ? (
            <button
              type="button"
              onClick={() => void controller.reloadFirstPage()}
            >
              重新加载第一页
            </button>
          ) : (
            <button type="button" onClick={() => void controller.loadMore()}>
              使用同一分页位置重试
            </button>
          )}
        </div>
      )}
      {state.hasMore ? (
        <button
          type="button"
          disabled={state.loadingMore}
          onClick={() => void controller.loadMore()}
        >
          {state.loadingMore ? "正在加载更多…" : "加载更多"}
        </button>
      ) : null}
    </section>
  );
}
