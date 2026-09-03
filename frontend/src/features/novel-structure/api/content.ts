import { isCanonicalPrefixedUlid } from "../../../api/identifiers";

import type { ChapterContentResponse } from "./contracts";

export function normalizeManuscript(content: string): string {
  return content.replace(/\r\n?/gu, "\n");
}

export function isManuscript(content: unknown): content is string {
  return (
    typeof content === "string" &&
    content.length <= 2_000_000 &&
    !Array.from(content).some((character) => {
      const code = character.charCodeAt(0);
      return (
        (code < 32 && code !== 9 && code !== 10 && code !== 13) ||
        (code >= 127 && code <= 159) ||
        code === 0x2028 ||
        code === 0x2029
      );
    })
  );
}

export function parseChapterContent(
  value: unknown,
  chapterId: string,
  projectId: string,
): ChapterContentResponse {
  const keys = [
    "chapter_id",
    "project_id",
    "volume_id",
    "current_revision_id",
    "revision_number",
    "concurrency_version",
    "content",
    "updated_at",
    "revision_created_at",
  ];
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Invalid Chapter content response.");
  }
  const row = value as Record<string, unknown>;
  const timestamp =
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$/u;
  if (
    Object.keys(row).length !== keys.length ||
    !keys.every((key) => Object.hasOwn(row, key)) ||
    row.chapter_id !== chapterId ||
    row.project_id !== projectId ||
    !isCanonicalPrefixedUlid(row.volume_id, "vol") ||
    !isCanonicalPrefixedUlid(row.current_revision_id, "chv") ||
    typeof row.revision_number !== "number" ||
    !Number.isSafeInteger(row.revision_number) ||
    row.revision_number < 1 ||
    row.concurrency_version !== row.revision_number ||
    !isManuscript(row.content) ||
    normalizeManuscript(row.content) !== row.content ||
    typeof row.updated_at !== "string" ||
    !timestamp.test(row.updated_at) ||
    !Number.isFinite(Date.parse(row.updated_at)) ||
    typeof row.revision_created_at !== "string" ||
    !timestamp.test(row.revision_created_at) ||
    Date.parse(row.updated_at) !== Date.parse(row.revision_created_at)
  ) {
    throw new Error("Invalid Chapter content response.");
  }
  return Object.freeze({ ...row }) as unknown as ChapterContentResponse;
}
