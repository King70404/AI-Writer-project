import type { CharacterResponse } from "../api/contracts";

export function CharacterMetadata({
  character,
}: {
  readonly character: CharacterResponse;
}) {
  const times = [
    ["创建时间", character.created_at],
    ["最近保存", character.updated_at],
  ] as const;
  return (
    <section aria-labelledby="character-metadata-title">
      <h2 id="character-metadata-title">角色保存信息</h2>
      <dl className="character-metadata">
        {times.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              <time dateTime={value}>{value}</time>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
