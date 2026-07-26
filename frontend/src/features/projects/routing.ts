import { isCanonicalProjectId } from "./api/parsers";

export function projectDetailsPath(projectId: string): string {
  if (!isCanonicalProjectId(projectId)) {
    throw new Error("A canonical Project ID is required for navigation.");
  }
  return `/projects/${encodeURIComponent(projectId)}`;
}

export function projectRevisionHistoryPath(projectId: string): string {
  if (!isCanonicalProjectId(projectId)) {
    throw new Error("A canonical Project ID is required for navigation.");
  }
  return `/projects/${encodeURIComponent(projectId)}/history`;
}
