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

export function projectStoryBiblePath(projectId: string): string {
  if (!isCanonicalProjectId(projectId)) {
    throw new Error("A canonical Project ID is required for navigation.");
  }
  return `/projects/${encodeURIComponent(projectId)}/story-bible`;
}

export function storyBibleRevisionHistoryPath(projectId: string): string {
  if (!isCanonicalProjectId(projectId)) {
    throw new Error("A canonical Project ID is required for navigation.");
  }
  return `/projects/${encodeURIComponent(projectId)}/story-bible/history`;
}

export function projectCharactersPath(projectId: string): string {
  if (!isCanonicalProjectId(projectId)) {
    throw new Error("A canonical Project ID is required for navigation.");
  }
  return `/projects/${encodeURIComponent(projectId)}/characters`;
}

export function projectStructurePath(projectId: string): string {
  if (!isCanonicalProjectId(projectId)) {
    throw new Error("A canonical Project ID is required for navigation.");
  }
  return `/projects/${encodeURIComponent(projectId)}/structure`;
}
