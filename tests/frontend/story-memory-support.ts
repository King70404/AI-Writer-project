import { vi } from "vitest";
import type {
  MemoryFact,
  MemoryReview,
  MemoryWorkspace,
  StoryMemoryClient,
} from "../../frontend/src/features/novel-structure/api/story-memory";
import { chapterId, structureProjectId } from "./novel-structure-support";

export function memoryFact(patch: Partial<MemoryFact> = {}): MemoryFact {
  return {
    id: "fact-one",
    revision_id: "fact-revision-one",
    project_id: structureProjectId,
    chapter_id: chapterId,
    version: 1,
    source_revision: "chapter-revision-one",
    title: "天气",
    text: "渡口正在下雨",
    quote: "渡口正在下雨。",
    status: "pending",
    stale: false,
    ...patch,
  };
}
export function memoryReview(patch: Partial<MemoryReview> = {}): MemoryReview {
  return {
    id: "review-one",
    chapter_id: chapterId,
    source_revision: "chapter-revision-one",
    version: 1,
    content: "渡口正在下雨。",
    content_truncated: false,
    facts: [],
    omitted_facts: 0,
    model: {
      name: "评审模型",
      kind: "cloud",
      base_url: "https://example.invalid/v1",
    },
    status: "ready",
    attempts: 0,
    last_error: null,
    stale: false,
    result: null,
    ...patch,
  };
}
export function memoryWorkspace(
  patch: Partial<MemoryWorkspace> = {},
): MemoryWorkspace {
  return {
    project_id: structureProjectId,
    chapter_id: chapterId,
    source_revision: "chapter-revision-one",
    facts: [memoryFact()],
    reviews: [memoryReview()],
    recalled_facts: [],
    omitted_facts: 0,
    impacts: [],
    ...patch,
  };
}
export function memoryClient(
  patch: Partial<StoryMemoryClient> = {},
): StoryMemoryClient {
  return {
    workspace: vi.fn().mockResolvedValue(memoryWorkspace()),
    fact: vi.fn().mockResolvedValue(memoryFact()),
    prepare: vi.fn().mockResolvedValue(memoryReview()),
    send: vi.fn().mockResolvedValue(memoryReview({ status: "completed" })),
    ...patch,
  };
}
