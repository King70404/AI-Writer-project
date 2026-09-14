import { Link } from "react-router";

import type { CharacterListItemResponse } from "../api/contracts";
import { characterEditorPath } from "../routing";

export function CharacterListItem({
  projectId,
  character,
}: {
  readonly projectId: string;
  readonly character: CharacterListItemResponse;
}) {
  return (
    <li className="character-card">
      <h3>{character.name}</h3>
      <p>{character.role || "未填写角色定位"}</p>
      <dl className="character-card__facts">
        <div>
          <dt>创建时间</dt>
          <dd>
            <time dateTime={character.created_at}>{character.created_at}</time>
          </dd>
        </div>
        <div>
          <dt>更新时间</dt>
          <dd>
            <time dateTime={character.updated_at}>{character.updated_at}</time>
          </dd>
        </div>
      </dl>
      <Link to={characterEditorPath(projectId, character.character_id)}>
        查看角色：{character.name}
      </Link>
    </li>
  );
}
