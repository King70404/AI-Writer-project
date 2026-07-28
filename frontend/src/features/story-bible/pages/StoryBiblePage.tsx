import { Link, useParams } from "react-router";

import { storyBibleApiClient, type StoryBibleApiClient } from "../api/client";
import { StoryBibleCreateForm } from "../components/StoryBibleCreateForm";
import { StoryBibleEditor } from "../components/StoryBibleEditor";
import { StoryBibleMetadata } from "../components/StoryBibleMetadata";
import { StoryBibleResolutionPanel } from "../components/StoryBibleResolutionPanel";
import {
  StoryBibleInvalidProject,
  StoryBibleLoadError,
  StoryBibleLoading,
  StoryBibleProjectNotFound,
} from "../components/StoryBibleStates";
import { useStoryBible } from "../hooks/useStoryBible";
import { projectDetailsPath } from "../../projects/routing";

interface StoryBiblePageProps {
  readonly client?: StoryBibleApiClient;
}

function StoryBibleRoute({
  projectId,
  client,
}: {
  readonly projectId: string | undefined;
  readonly client: StoryBibleApiClient;
}) {
  const controller = useStoryBible(projectId, client);
  const state = controller.state;

  return (
    <section
      className="story-bible-page"
      aria-labelledby="story-bible-page-title"
    >
      <header className="story-bible-page__header">
        <div>
          <p className="section-kicker">Story Bible · 纯文本设定集</p>
          <h2 id="story-bible-page-title">
            {state.status === "ready"
              ? state.baseline.storyBible.title
              : "Story Bible"}
          </h2>
        </div>
        <div className="story-bible-page__links">
          {projectId === undefined ? null : (
            <Link
              to={
                state.status === "invalid_project"
                  ? "/projects"
                  : projectDetailsPath(projectId)
              }
            >
              返回Project详情
            </Link>
          )}
          <Link to="/projects">返回项目列表</Link>
        </div>
      </header>
      {state.status === "invalid_project" ? <StoryBibleInvalidProject /> : null}
      {state.status === "loading" ? <StoryBibleLoading /> : null}
      {state.status === "project_not_found" ? (
        <StoryBibleProjectNotFound error={state.error} />
      ) : null}
      {state.status === "error" ? (
        <StoryBibleLoadError
          error={state.error}
          onRetry={() => void controller.reload()}
        />
      ) : null}
      <StoryBibleCreateForm controller={controller} />
      {state.status === "ready" ? (
        <StoryBibleMetadata storyBible={state.baseline.storyBible} />
      ) : null}
      <StoryBibleEditor controller={controller} />
      <StoryBibleResolutionPanel controller={controller} />
    </section>
  );
}

export function StoryBiblePage({
  client = storyBibleApiClient,
}: StoryBiblePageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  return (
    <StoryBibleRoute
      key={projectId ?? "missing-project-id"}
      projectId={projectId}
      client={client}
    />
  );
}
