import type { StoryBibleResponse } from "../api/contracts";

const timestampFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function StoryBibleTime({
  label,
  value,
}: {
  readonly label: string;
  readonly value: string;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        <time dateTime={value}>
          {timestampFormatter.format(new Date(value))}
        </time>
      </dd>
    </div>
  );
}

export function StoryBibleMetadata({
  storyBible,
}: {
  readonly storyBible: StoryBibleResponse;
}) {
  return (
    <section
      className="story-bible-metadata"
      aria-labelledby="story-bible-metadata-title"
    >
      <h3 id="story-bible-metadata-title">当前设定集快照</h3>
      <dl className="story-bible-metadata__facts">
        <div>
          <dt>Story Bible编号</dt>
          <dd>{storyBible.story_bible_id}</dd>
        </div>
        <div>
          <dt>Project编号</dt>
          <dd>{storyBible.project_id}</dd>
        </div>
        <div>
          <dt>当前修订编号</dt>
          <dd>{storyBible.current_revision_id}</dd>
        </div>
        <div>
          <dt>当前修订号</dt>
          <dd>{storyBible.revision_number}</dd>
        </div>
        <div>
          <dt>并发版本</dt>
          <dd>{storyBible.concurrency_version}</dd>
        </div>
        <StoryBibleTime label="创建时间" value={storyBible.created_at} />
        <StoryBibleTime label="更新时间" value={storyBible.updated_at} />
        <StoryBibleTime
          label="修订创建时间"
          value={storyBible.revision_created_at}
        />
        <StoryBibleTime
          label="Head更新时间"
          value={storyBible.head_updated_at}
        />
      </dl>
    </section>
  );
}
