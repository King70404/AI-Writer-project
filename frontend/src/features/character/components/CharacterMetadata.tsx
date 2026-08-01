import type { CharacterResponse } from "../api/contracts";

export function CharacterMetadata({
  character,
}: {
  readonly character: CharacterResponse;
}) {
  const facts = [
    ["Character ID", character.character_id],
    ["Project ID", character.project_id],
    ["Current Revision ID", character.current_revision_id],
    ["RevisionNumber", String(character.revision_number)],
    ["ConcurrencyVersion", String(character.concurrency_version)],
  ] as const;
  const times = [
    ["created_at", character.created_at],
    ["updated_at", character.updated_at],
    ["revision_created_at", character.revision_created_at],
    ["head_updated_at", character.head_updated_at],
  ] as const;
  return (
    <section aria-labelledby="character-metadata-title">
      <h2 id="character-metadata-title">当前资源元数据</h2>
      <dl className="character-metadata">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
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
