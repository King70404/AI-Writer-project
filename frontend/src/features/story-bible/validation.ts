import {
  STORY_BIBLE_CONTENT_MAX_CODE_POINTS,
  STORY_BIBLE_TITLE_MAX_CODE_POINTS,
} from "./constants";

export type StoryBibleFieldName = "title" | "content";

export interface StoryBibleFieldError {
  readonly field: StoryBibleFieldName;
  readonly message: string;
}

function isForbiddenControl(
  value: string,
  allowPlainTextWhitespace: boolean,
): boolean {
  for (const character of value) {
    const codePoint = character.codePointAt(0);
    if (codePoint === undefined) {
      return true;
    }
    if (
      character === "\u2028" ||
      character === "\u2029" ||
      ((codePoint <= 0x1f || (codePoint >= 0x7f && codePoint <= 0x9f)) &&
        !(
          allowPlainTextWhitespace &&
          (character === "\n" || character === "\t")
        ))
    ) {
      return true;
    }
  }
  return false;
}

export function countStoryBibleCodePoints(value: string): number {
  return [...value].length;
}

export function normalizeStoryBibleContent(value: string): string {
  return value.replace(/\r\n?/gu, "\n");
}

export function normalizeStoryBibleTitle(value: string): string {
  return value.trim();
}

export function validateStoryBibleInput(
  title: unknown,
  content: unknown,
): StoryBibleFieldError[] {
  if (typeof title !== "string" || typeof content !== "string") {
    return [
      {
        field: typeof title === "string" ? "content" : "title",
        message: "Story Bible标题和正文必须是文本。",
      },
    ];
  }
  const errors: StoryBibleFieldError[] = [];
  const normalizedTitle = normalizeStoryBibleTitle(title);
  if (normalizedTitle.length === 0 || isForbiddenControl(title, false)) {
    errors.push({
      field: "title",
      message:
        normalizedTitle.length === 0
          ? "请输入Story Bible标题。"
          : "Story Bible标题包含不允许的控制字符。",
    });
  } else if (
    countStoryBibleCodePoints(normalizedTitle) >
    STORY_BIBLE_TITLE_MAX_CODE_POINTS
  ) {
    errors.push({
      field: "title",
      message: "Story Bible标题不能超过120个字符。",
    });
  }
  const normalizedContent = normalizeStoryBibleContent(content);
  if (isForbiddenControl(normalizedContent, true)) {
    errors.push({
      field: "content",
      message: "Story Bible正文包含不允许的控制字符。",
    });
  } else if (
    countStoryBibleCodePoints(normalizedContent) >
    STORY_BIBLE_CONTENT_MAX_CODE_POINTS
  ) {
    errors.push({
      field: "content",
      message: "Story Bible正文不能超过50000个字符。",
    });
  }
  return errors;
}

export function errorForStoryBibleField(
  errors: readonly StoryBibleFieldError[],
  field: StoryBibleFieldName,
): string | null {
  return errors.find((error) => error.field === field)?.message ?? null;
}
