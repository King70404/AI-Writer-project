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
      <h3 id="story-bible-metadata-title">设定保存信息</h3>
      <dl className="story-bible-metadata__facts">
        <StoryBibleTime label="创建时间" value={storyBible.created_at} />
        <StoryBibleTime label="最近保存" value={storyBible.updated_at} />
      </dl>
    </section>
  );
}
