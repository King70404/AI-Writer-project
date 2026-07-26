import type { ProjectRevisionHistoryItemResponse } from "../api/contracts";
import { formatProjectTimestamp } from "../formatting";

interface ProjectRevisionHistoryItemProps {
  readonly item: ProjectRevisionHistoryItemResponse;
  readonly selected: boolean;
  readonly onSelect: (revisionNumber: number) => void;
}

export function ProjectRevisionHistoryItem({
  item,
  selected,
  onSelect,
}: ProjectRevisionHistoryItemProps) {
  return (
    <li className="project-revision-card">
      <div className="project-revision-card__heading">
        <h3>修订 {item.revision_number}</h3>
        {item.is_current ? (
          <span className="project-revision-card__current">当前修订</span>
        ) : (
          <span className="project-revision-card__historical">历史修订</span>
        )}
      </div>
      <p className="project-revision-card__title">{item.title}</p>
      <p>
        创建时间：
        <time dateTime={item.created_at}>
          {formatProjectTimestamp(item.created_at)}
        </time>
      </p>
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect(item.revision_number)}
      >
        {selected ? "重新查看内容" : "查看内容"}
      </button>
    </li>
  );
}
