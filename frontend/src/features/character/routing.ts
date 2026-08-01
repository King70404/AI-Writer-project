import {
  isCanonicalCharacterId,
  isCanonicalCharacterProjectId,
} from "./api/parsers";

export function projectCharactersPath(projectId: string): string {
  if (!isCanonicalCharacterProjectId(projectId)) {
    throw new Error("A canonical Project ID is required for navigation.");
  }
  return `/projects/${encodeURIComponent(projectId)}/characters`;
}

export function characterEditorPath(
  projectId: string,
  characterId: string,
): string {
  if (
    !isCanonicalCharacterProjectId(projectId) ||
    !isCanonicalCharacterId(characterId)
  ) {
    throw new Error(
      "Canonical Project and Character IDs are required for navigation.",
    );
  }
  return `/projects/${encodeURIComponent(projectId)}/characters/${encodeURIComponent(characterId)}`;
}
