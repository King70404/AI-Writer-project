import { chapterWritingPath } from "../../novel-structure/routing";
import { ProjectsPage } from "../../projects";
import type { ProjectApiClient } from "../../projects/api/client";
import { recentChapterForProject } from "../recentWriting";

function continueWritingPath(projectId: string): string | null {
  const recent = recentChapterForProject(projectId);
  return recent ? chapterWritingPath(recent.projectId, recent.chapterId) : null;
}

export function BookshelfPage({
  client,
}: {
  readonly client?: ProjectApiClient;
}) {
  return (
    <ProjectsPage client={client} continueWritingPath={continueWritingPath} />
  );
}
