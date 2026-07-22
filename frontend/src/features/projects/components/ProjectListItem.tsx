import { Link } from "react-router-dom";

import type { ProjectListItemResponse } from "../api/contracts";
import { formatProjectTimestamp } from "../formatting";
import { projectDetailsPath } from "../routing";

interface ProjectListItemProps {
  readonly project: ProjectListItemResponse;
}

export function ProjectListItem({ project }: ProjectListItemProps) {
  return (
    <li className="project-card" data-project-id={project.project_id}>
      <h3>{project.title}</h3>
      <p className="project-card__id">{project.project_id}</p>
      <dl className="project-card__facts">
        <div>
          <dt>当前修订</dt>
          <dd>{project.revision_number}</dd>
        </div>
        <div>
          <dt>并发版本</dt>
          <dd>{project.concurrency_version}</dd>
        </div>
        <div>
          <dt>创建时间</dt>
          <dd>
            <time dateTime={project.created_at}>
              {formatProjectTimestamp(project.created_at)}
            </time>
          </dd>
        </div>
        <div>
          <dt>更新时间</dt>
          <dd>
            <time dateTime={project.updated_at}>
              {formatProjectTimestamp(project.updated_at)}
            </time>
          </dd>
        </div>
      </dl>
      <Link
        className="project-card__details-link"
        to={projectDetailsPath(project.project_id)}
      >
        查看详情
      </Link>
    </li>
  );
}
