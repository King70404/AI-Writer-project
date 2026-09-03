import { isCanonicalPrefixedUlid } from "../../api/identifiers";

export function chapterWritingPath(
  projectId: string,
  chapterId: string,
): string {
  if (
    !isCanonicalPrefixedUlid(projectId, "prj") ||
    !isCanonicalPrefixedUlid(chapterId, "chp")
  )
    throw new Error("Invalid Chapter writing route.");
  return `/projects/${projectId}/chapters/${chapterId}/write`;
}
