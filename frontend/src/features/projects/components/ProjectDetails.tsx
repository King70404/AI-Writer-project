import type { ProjectResponse } from "../api/contracts";
import { formatProjectTimestamp } from "../formatting";

interface ProjectDetailsProps {
  readonly project: ProjectResponse;
}

function ProjectTime({
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
        <time dateTime={value}>{formatProjectTimestamp(value)}</time>
      </dd>
    </div>
  );
}

export function ProjectDetails({ project }: ProjectDetailsProps) {
  return (
    <section
      className="project-details"
      aria-labelledby="project-current-title"
    >
      <h3 id="project-current-title">当前项目快照</h3>
      <p className="project-details__description">
        {project.description.length === 0
          ? "暂无项目简介。"
          : project.description}
      </p>
      <dl className="project-details__facts">
        <div>
          <dt>项目编号</dt>
          <dd>{project.project_id}</dd>
        </div>
        <div>
          <dt>当前修订编号</dt>
          <dd>{project.current_revision_id}</dd>
        </div>
        <div>
          <dt>当前修订号</dt>
          <dd>{project.revision_number}</dd>
        </div>
        <div>
          <dt>并发版本</dt>
          <dd>{project.concurrency_version}</dd>
        </div>
        <ProjectTime label="项目创建时间" value={project.created_at} />
        <ProjectTime label="项目更新时间" value={project.updated_at} />
        <ProjectTime label="修订创建时间" value={project.revision_created_at} />
        <ProjectTime label="Head更新时间" value={project.head_updated_at} />
      </dl>
    </section>
  );
}
