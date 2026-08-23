export type StructureField = "title" | "summary" | "position";

export interface StructureFieldError {
  readonly field: StructureField;
  readonly message: string;
}

const FORBIDDEN_TITLE = /[\u0000-\u001F\u007F-\u009F\u2028\u2029]/u;
const FORBIDDEN_SUMMARY =
  /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F\u2028\u2029]/u;

export function normalizeStructureTitle(value: string): string {
  return value.trim();
}

export function normalizeStructureSummary(value: string): string {
  return value.replace(/\r\n?/gu, "\n");
}

export function validateStructureInput(
  title: unknown,
  summary: unknown,
  position?: unknown,
): readonly StructureFieldError[] {
  const errors: StructureFieldError[] = [];
  if (
    typeof title !== "string" ||
    FORBIDDEN_TITLE.test(title) ||
    normalizeStructureTitle(typeof title === "string" ? title : "").length <
      1 ||
    normalizeStructureTitle(typeof title === "string" ? title : "").length > 120
  ) {
    errors.push({
      field: "title",
      message: "标题必填，且最多为120个有效字符。",
    });
  }
  if (
    typeof summary !== "string" ||
    FORBIDDEN_SUMMARY.test(
      typeof summary === "string" ? normalizeStructureSummary(summary) : "",
    ) ||
    (typeof summary === "string" &&
      normalizeStructureSummary(summary).length > 2_000)
  ) {
    errors.push({ field: "summary", message: "梗概最多为2000个纯文本字符。" });
  }
  if (
    position !== undefined &&
    (typeof position !== "number" ||
      !Number.isSafeInteger(position) ||
      position < 1)
  ) {
    errors.push({ field: "position", message: "顺序必须是正整数。" });
  }
  return errors;
}

export function fieldError(
  errors: readonly StructureFieldError[],
  field: StructureField,
): string | null {
  return errors.find((error) => error.field === field)?.message ?? null;
}
