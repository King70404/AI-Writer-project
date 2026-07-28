import { isCanonicalPrefixedUlid } from "../../../api/identifiers";
import {
  normalizeStoryBibleContent,
  normalizeStoryBibleTitle,
  validateStoryBibleInput,
} from "../validation";

import type {
  StoryBibleResponse,
  StoryBibleRevisionHistoryItemResponse,
  StoryBibleRevisionHistoryPageResponse,
  StoryBibleRevisionResponse,
} from "./contracts";

export class StoryBibleContractError extends Error {
  public constructor() {
    super("Story Bible API response did not match its contract.");
    this.name = "StoryBibleContractError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return (
    actual.length === expected.length &&
    expected.every((key) => Object.hasOwn(value, key))
  );
}

function requiredPositiveInteger(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value <= 0) {
    throw new StoryBibleContractError();
  }
  return value;
}

const AWARE_RFC3339 =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u;

function requiredTimestamp(value: unknown): string {
  if (
    typeof value !== "string" ||
    value.length > 64 ||
    !AWARE_RFC3339.test(value) ||
    !Number.isFinite(Date.parse(value))
  ) {
    throw new StoryBibleContractError();
  }
  return value;
}

function requiredIdentifier(
  value: unknown,
  prefix: "prj" | "sbl" | "sbr",
): string {
  if (!isCanonicalPrefixedUlid(value, prefix)) {
    throw new StoryBibleContractError();
  }
  return value;
}

export function isCanonicalStoryBibleId(value: unknown): value is string {
  return isCanonicalPrefixedUlid(value, "sbl");
}

export function isCanonicalStoryBibleProjectId(
  value: unknown,
): value is string {
  return isCanonicalPrefixedUlid(value, "prj");
}

const STORY_BIBLE_KEYS = [
  "story_bible_id",
  "project_id",
  "current_revision_id",
  "revision_number",
  "concurrency_version",
  "title",
  "content",
  "created_at",
  "updated_at",
  "revision_created_at",
  "head_updated_at",
] as const;

export interface StoryBibleResponseContext {
  readonly expectedProjectId?: string;
  readonly expectedStoryBibleId?: string;
}

export function parseStoryBibleResponse(
  value: unknown,
  context: StoryBibleResponseContext = {},
): StoryBibleResponse {
  if (!isRecord(value) || !hasExactKeys(value, STORY_BIBLE_KEYS)) {
    throw new StoryBibleContractError();
  }
  const storyBibleId = requiredIdentifier(value.story_bible_id, "sbl");
  const projectId = requiredIdentifier(value.project_id, "prj");
  const currentRevisionId = requiredIdentifier(
    value.current_revision_id,
    "sbr",
  );
  const revisionNumber = requiredPositiveInteger(value.revision_number);
  const concurrencyVersion = requiredPositiveInteger(value.concurrency_version);
  if (
    revisionNumber !== concurrencyVersion ||
    (context.expectedProjectId !== undefined &&
      projectId !== context.expectedProjectId) ||
    (context.expectedStoryBibleId !== undefined &&
      storyBibleId !== context.expectedStoryBibleId) ||
    typeof value.title !== "string" ||
    typeof value.content !== "string" ||
    validateStoryBibleInput(value.title, value.content).length > 0 ||
    normalizeStoryBibleTitle(value.title) !== value.title ||
    normalizeStoryBibleContent(value.content) !== value.content
  ) {
    throw new StoryBibleContractError();
  }
  const createdAt = requiredTimestamp(value.created_at);
  const updatedAt = requiredTimestamp(value.updated_at);
  const revisionCreatedAt = requiredTimestamp(value.revision_created_at);
  const headUpdatedAt = requiredTimestamp(value.head_updated_at);
  const createdMilliseconds = Date.parse(createdAt);
  const updatedMilliseconds = Date.parse(updatedAt);
  if (
    createdMilliseconds > updatedMilliseconds ||
    updatedMilliseconds !== Date.parse(revisionCreatedAt) ||
    updatedMilliseconds !== Date.parse(headUpdatedAt)
  ) {
    throw new StoryBibleContractError();
  }
  return {
    story_bible_id: storyBibleId,
    project_id: projectId,
    current_revision_id: currentRevisionId,
    revision_number: revisionNumber,
    concurrency_version: concurrencyVersion,
    title: value.title,
    content: value.content,
    created_at: createdAt,
    updated_at: updatedAt,
    revision_created_at: revisionCreatedAt,
    head_updated_at: headUpdatedAt,
  };
}

const REVISION_HISTORY_ITEM_KEYS = [
  "revision_id",
  "revision_number",
  "title",
  "created_at",
  "is_current",
] as const;

const REVISION_HISTORY_PAGE_KEYS = [
  "story_bible_id",
  "project_id",
  "current_revision_number",
  "items",
  "next_cursor",
  "has_more",
] as const;

const REVISION_KEYS = [
  "story_bible_id",
  "project_id",
  "revision_id",
  "revision_number",
  "title",
  "content",
  "created_at",
  "is_current",
  "current_revision_number",
] as const;

function canonicalTitle(value: unknown): string {
  if (
    typeof value !== "string" ||
    validateStoryBibleInput(value, "").some(
      (error) => error.field === "title",
    ) ||
    normalizeStoryBibleTitle(value) !== value
  ) {
    throw new StoryBibleContractError();
  }
  return value;
}

function canonicalContent(value: unknown): string {
  if (
    typeof value !== "string" ||
    validateStoryBibleInput("History", value).some(
      (error) => error.field === "content",
    ) ||
    normalizeStoryBibleContent(value) !== value
  ) {
    throw new StoryBibleContractError();
  }
  return value;
}

function parseHistoryItem(
  value: unknown,
): StoryBibleRevisionHistoryItemResponse {
  if (!isRecord(value) || !hasExactKeys(value, REVISION_HISTORY_ITEM_KEYS)) {
    throw new StoryBibleContractError();
  }
  if (typeof value.is_current !== "boolean") {
    throw new StoryBibleContractError();
  }
  return {
    revision_id: requiredIdentifier(value.revision_id, "sbr"),
    revision_number: requiredPositiveInteger(value.revision_number),
    title: canonicalTitle(value.title),
    created_at: requiredTimestamp(value.created_at),
    is_current: value.is_current,
  };
}

export function parseStoryBibleRevisionHistoryPageResponse(
  value: unknown,
  expectedStoryBibleId: string,
  expectedProjectId: string,
): StoryBibleRevisionHistoryPageResponse {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, REVISION_HISTORY_PAGE_KEYS) ||
    !Array.isArray(value.items) ||
    typeof value.has_more !== "boolean" ||
    (value.next_cursor !== null &&
      (typeof value.next_cursor !== "string" ||
        value.next_cursor.length === 0 ||
        value.next_cursor.length > 256 ||
        !/^[\x20-\x7E]+$/u.test(value.next_cursor)))
  ) {
    throw new StoryBibleContractError();
  }
  const storyBibleId = requiredIdentifier(value.story_bible_id, "sbl");
  const projectId = requiredIdentifier(value.project_id, "prj");
  const currentRevisionNumber = requiredPositiveInteger(
    value.current_revision_number,
  );
  if (
    storyBibleId !== expectedStoryBibleId ||
    projectId !== expectedProjectId ||
    value.has_more !== (value.next_cursor !== null)
  ) {
    throw new StoryBibleContractError();
  }
  const items = value.items.map(parseHistoryItem);
  const revisionIds = new Set<string>();
  const revisionNumbers = new Set<number>();
  for (const [index, item] of items.entries()) {
    if (
      revisionIds.has(item.revision_id) ||
      revisionNumbers.has(item.revision_number) ||
      (index > 0 && items[index - 1].revision_number <= item.revision_number) ||
      item.is_current !== (item.revision_number === currentRevisionNumber)
    ) {
      throw new StoryBibleContractError();
    }
    revisionIds.add(item.revision_id);
    revisionNumbers.add(item.revision_number);
  }
  if (items.length === 0 && value.has_more) {
    throw new StoryBibleContractError();
  }
  return {
    story_bible_id: storyBibleId,
    project_id: projectId,
    current_revision_number: currentRevisionNumber,
    items,
    next_cursor: value.next_cursor,
    has_more: value.has_more,
  };
}

export function parseStoryBibleRevisionResponse(
  value: unknown,
  expectedStoryBibleId: string,
  expectedProjectId: string,
  expectedRevisionNumber: number,
): StoryBibleRevisionResponse {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, REVISION_KEYS) ||
    typeof value.is_current !== "boolean"
  ) {
    throw new StoryBibleContractError();
  }
  const storyBibleId = requiredIdentifier(value.story_bible_id, "sbl");
  const projectId = requiredIdentifier(value.project_id, "prj");
  const revisionNumber = requiredPositiveInteger(value.revision_number);
  const currentRevisionNumber = requiredPositiveInteger(
    value.current_revision_number,
  );
  if (
    storyBibleId !== expectedStoryBibleId ||
    projectId !== expectedProjectId ||
    revisionNumber !== expectedRevisionNumber ||
    revisionNumber > currentRevisionNumber ||
    value.is_current !== (revisionNumber === currentRevisionNumber)
  ) {
    throw new StoryBibleContractError();
  }
  return {
    story_bible_id: storyBibleId,
    project_id: projectId,
    revision_id: requiredIdentifier(value.revision_id, "sbr"),
    revision_number: revisionNumber,
    title: canonicalTitle(value.title),
    content: canonicalContent(value.content),
    created_at: requiredTimestamp(value.created_at),
    is_current: value.is_current,
    current_revision_number: currentRevisionNumber,
  };
}
