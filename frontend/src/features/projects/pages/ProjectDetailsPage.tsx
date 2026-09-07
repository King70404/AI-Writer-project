import { Link, useParams } from "react-router";

import type {
  ProjectDeleteApiClient,
  ProjectDetailApiClient,
  ProjectRevisionApiClient,
} from "../api/client";
import { projectApiClient } from "../api/client";
import { DeleteProjectPanel } from "../components/DeleteProjectPanel";
import { ProjectConflictPanel } from "../components/ProjectConflictPanel";
import { ExportManuscriptButton } from "../components/ExportManuscriptButton";
import {
  ProjectDetailError,
  ProjectDetailInvalid,
  ProjectDetailLoading,
} from "../components/ProjectDetailStates";
import { ProjectDetails } from "../components/ProjectDetails";
import { ProjectEditForm } from "../components/ProjectEditForm";
import { useProjectDetails } from "../hooks/useProjectDetails";
import { useReviseProject } from "../hooks/useReviseProject";
import {
  projectCharactersPath,
  projectRevisionHistoryPath,
  projectStoryBiblePath,
  projectStructurePath,
} from "../routing";

interface ProjectDetailsPageProps {
  readonly client?: ProjectDetailApiClient &
    ProjectRevisionApiClient &
    ProjectDeleteApiClient;
}

function ReadyProjectDetails({
  client,
  resource,
  onReloadProject,
}: {
  readonly client: ProjectDetailApiClient &
    ProjectRevisionApiClient &
    ProjectDeleteApiClient;
  readonly resource: Parameters<typeof useReviseProject>[0];
  readonly onReloadProject: () => void;
}) {
  const revision = useReviseProject(resource, client);
  return (
    <>
      <ProjectDetails project={revision.baseline.project} />
      <section aria-labelledby="novel-actions-title">
        <p className="section-kicker">创作入口</p>
        <h3 id="novel-actions-title">继续完善这本小说</h3>
        <div className="project-details-page__links">
          <Link to={projectStructurePath(revision.baseline.project.project_id)}>
            大纲与章节
          </Link>
          <Link to={projectCharactersPath(revision.baseline.project.project_id)}>
            人物
          </Link>
          <Link to={projectStoryBiblePath(revision.baseline.project.project_id)}>
            小说设定
          </Link>
          <Link
            to={projectRevisionHistoryPath(revision.baseline.project.project_id)}
          >
            历史版本
          </Link>
        </div>
      </section>
      <ExportManuscriptButton
        projectId={revision.baseline.project.project_id}
        title={revision.baseline.project.title}
      />
      <ProjectEditForm
        controller={revision}
        onReloadProject={onReloadProject}
      />
      <ProjectConflictPanel controller={revision} />
      <DeleteProjectPanel resource={revision.baseline} client={client} />
    </>
  );
}

function ProjectDetailsRoute({
  projectId,
  client,
}: {
  readonly projectId: string | undefined;
  readonly client: ProjectDetailApiClient &
    ProjectRevisionApiClient &
    ProjectDeleteApiClient;
}) {
  const details = useProjectDetails(projectId, client);
  const state = details.state;

  return (
    <section
      className="project-details-page"
      aria-labelledby="project-details-page-title"
    >
      <header className="project-details-page__header">
        <div>
          <p className="section-kicker">我的小说</p>
          <h2 id="project-details-page-title">
            {state.status === "ready" ? state.resource.project.title : "小说详情"}
          </h2>
        </div>
        <div className="project-details-page__links">
          <Link to="/projects">返回我的小说</Link>
        </div>
      </header>
      {state.status === "invalid" ? <ProjectDetailInvalid /> : null}
      {state.status === "loading" ? <ProjectDetailLoading /> : null}
      {state.status === "not_found" ? (
        <ProjectDetailError error={state.error} notFound />
      ) : null}
      {state.status === "error" ? (
        <ProjectDetailError
          error={state.error}
          onRetry={() => void details.reload()}
        />
      ) : null}
      {state.status === "ready" ? (
        <ReadyProjectDetails
          client={client}
          resource={state.resource}
          onReloadProject={() => void details.reload()}
        />
      ) : null}
    </section>
  );
}

export function ProjectDetailsPage({
  client = projectApiClient,
}: ProjectDetailsPageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <ProjectDetailsRoute
      key={projectId ?? "missing-project-id"}
      projectId={projectId}
      client={client}
    />
  );
}
