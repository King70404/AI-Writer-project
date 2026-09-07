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
      <h3 id="project-current-title">小说简介</h3>
      <p className="project-details__description">
        {project.description.length === 0
          ? "暂未填写简介。"
          : project.description}
      </p>
      <dl className="project-details__facts">
        <ProjectTime label="创建时间" value={project.created_at} />
        <ProjectTime label="最近更新" value={project.updated_at} />
      </dl>
    </section>
  );
}
