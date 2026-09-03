import { vi } from "vitest";
import { act } from "@testing-library/react";

export async function flushReact(action: () => void): Promise<void> {
  await act(async () => {
    action();
    await Promise.resolve();
  });
}

import type { NovelStructureApiClient } from "../../frontend/src/features/novel-structure/api/client";
import type {
  ChapterContentResponse,
  VersionedChapterContent,
} from "../../frontend/src/features/novel-structure/api/contracts";
import { chapterResponse, structureClient } from "./novel-structure-support";

export function contentResponse(
  content = "",
  version = 1,
  overrides: Partial<ChapterContentResponse> = {},
): ChapterContentResponse {
  const chapter = chapterResponse(version);
  return {
    chapter_id: chapter.chapter_id,
    project_id: chapter.project_id,
    volume_id: chapter.volume_id,
    current_revision_id: chapter.current_revision_id,
    revision_number: version,
    concurrency_version: version,
    content,
    updated_at: chapter.updated_at,
    revision_created_at: chapter.revision_created_at,
    ...overrides,
  };
}

export function written(content = "", version = 1): VersionedChapterContent {
  return {
    resource: contentResponse(content, version),
    etag: `"${version}"`,
    version,
  };
}

export function writingClient(
  overrides: Partial<NovelStructureApiClient> = {},
): NovelStructureApiClient {
  return structureClient({
    getChapterContent: vi.fn().mockResolvedValue(written()),
    updateChapterContent: vi
      .fn()
      .mockImplementation((_chapter, _project, content: string, etag: string) =>
        Promise.resolve(written(content, Number(etag.slice(1, -1)) + 1)),
      ),
    ...overrides,
  });
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((accept, fail) => {
    resolve = accept;
    reject = fail;
  });
  return { promise, resolve, reject };
}
