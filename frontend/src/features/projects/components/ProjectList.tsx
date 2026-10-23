import type { ProjectListController } from "../hooks/useProjectList";

import { ProjectListItem } from "./ProjectListItem";
import {
  ProjectListEmpty,
  ProjectListError,
  ProjectListLoading,
} from "./ProjectListStates";

export type ContinueWritingPath = (projectId: string) => string | null;

interface ProjectListProps {
  readonly controller: ProjectListController;
  readonly continueWritingPath?: ContinueWritingPath;
}

export function ProjectList({
  controller,
  continueWritingPath,
}: ProjectListProps) {
  if (controller.status === "loading") {
    return <ProjectListLoading />;
  }
  if (controller.status === "error" && controller.error !== null) {
    return (
      <ProjectListError
        error={controller.error}
        onRetry={() => void controller.reload()}
        retryLabel="重新加载列表"
      />
    );
  }
  if (controller.items.length === 0) {
    return <ProjectListEmpty />;
  }

  return (
    <div
      className="project-list-region"
      aria-busy={controller.loadMoreStatus === "loading"}
    >
      <ul className="project-list" aria-label="项目列表">
        {controller.items.map((project) => (
          <ProjectListItem
            key={project.project_id}
            project={project}
            continuePath={continueWritingPath?.(project.project_id) ?? null}
          />
        ))}
      </ul>
      {controller.loadMoreStatus === "error" &&
      controller.loadMoreError !== null ? (
        <ProjectListError
          error={controller.loadMoreError}
          onRetry={() => void controller.loadMore()}
          retryLabel="重试加载更多"
        />
      ) : null}
      {controller.hasMore && controller.nextCursor !== null ? (
        <button
          className="project-list__more"
          type="button"
          onClick={() => void controller.loadMore()}
          disabled={controller.loadMoreStatus === "loading"}
        >
          {controller.loadMoreStatus === "loading"
            ? "正在加载更多…"
            : "加载更多"}
        </button>
      ) : (
        <p className="project-list__end" role="status">
          已显示当前全部项目。
        </p>
      )}
    </div>
  );
}
