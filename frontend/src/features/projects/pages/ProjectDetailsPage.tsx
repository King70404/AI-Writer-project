import { Link, useParams } from "react-router";

import type {
  ProjectDetailApiClient,
  ProjectRevisionApiClient,
} from "../api/client";
import { projectApiClient } from "../api/client";
import { ProjectConflictPanel } from "../components/ProjectConflictPanel";
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
} from "../routing";

interface ProjectDetailsPageProps {
  readonly client?: ProjectDetailApiClient & ProjectRevisionApiClient;
}

function ReadyProjectDetails({
  client,
  resource,
  onReloadProject,
}: {
  readonly client: ProjectDetailApiClient & ProjectRevisionApiClient;
  readonly resource: Parameters<typeof useReviseProject>[0];
  readonly onReloadProject: () => void;
}) {
  const revision = useReviseProject(resource, client);
  return (
    <>
      <ProjectDetails project={revision.baseline.project} />
      <ProjectEditForm
        controller={revision}
        onReloadProject={onReloadProject}
      />
      <ProjectConflictPanel controller={revision} />
    </>
  );
}

function ProjectDetailsRoute({
  projectId,
  client,
}: {
  readonly projectId: string | undefined;
  readonly client: ProjectDetailApiClient & ProjectRevisionApiClient;
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
          <p className="section-kicker">Project 当前详情</p>
          <h2 id="project-details-page-title">
            {state.status === "ready"
              ? state.resource.project.title
              : "项目详情"}
          </h2>
        </div>
        <div className="project-details-page__links">
          {state.status === "ready" ? (
            <>
              <Link
                to={projectCharactersPath(state.resource.project.project_id)}
              >
                查看角色
              </Link>
              <Link
                to={projectStoryBiblePath(state.resource.project.project_id)}
              >
                查看 Story Bible
              </Link>
              <Link
                to={projectRevisionHistoryPath(
                  state.resource.project.project_id,
                )}
              >
                查看修订历史
              </Link>
            </>
          ) : null}
          <Link to="/projects">返回项目列表</Link>
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
