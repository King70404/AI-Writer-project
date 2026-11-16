import { ImportWorkbench } from "../../legacy-import/components/ImportWorkbench";
import { chapterWritingPath } from "../../novel-structure/routing";
import { ProjectsPage } from "../../projects";
import type { ProjectApiClient } from "../../projects/api/client";
import { recentChapterForProject } from "../recentWriting";
import { BookshelfOverview } from "../components/BookshelfOverview";

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
    <>
      <BookshelfOverview />
      <ProjectsPage client={client} continueWritingPath={continueWritingPath} />
      <ImportWorkbench />
    </>
  );
}
