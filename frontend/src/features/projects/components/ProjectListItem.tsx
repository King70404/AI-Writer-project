import { Link } from "react-router";

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
      <dl className="project-card__facts">
        <div>
          <dt>创建时间</dt>
          <dd>
            <time dateTime={project.created_at}>
              {formatProjectTimestamp(project.created_at)}
            </time>
          </dd>
        </div>
        <div>
          <dt>最近编辑</dt>
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
        打开小说
      </Link>
    </li>
  );
}
