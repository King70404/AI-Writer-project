import type { ProjectFieldError, ProjectFieldName } from "./api/errors";
import {
  PROJECT_DESCRIPTION_MAX_CODE_POINTS,
  PROJECT_TITLE_MAX_CODE_POINTS,
} from "./constants";
import { countUnicodeCodePoints } from "./formatting";

export function validateProjectInput(
  title: string,
  description: string,
): ProjectFieldError[] {
  const errors: ProjectFieldError[] = [];
  if (title.trim().length === 0) {
    errors.push({ field: "title", message: "请输入项目标题。" });
  } else if (countUnicodeCodePoints(title) > PROJECT_TITLE_MAX_CODE_POINTS) {
    errors.push({ field: "title", message: "项目标题不能超过120个字符。" });
  }
  if (
    countUnicodeCodePoints(description) > PROJECT_DESCRIPTION_MAX_CODE_POINTS
  ) {
    errors.push({
      field: "description",
      message: "项目简介不能超过2000个字符。",
    });
  }
  return errors;
}

export function errorForProjectField(
  errors: readonly ProjectFieldError[],
  field: ProjectFieldName,
): string | null {
  return errors.find((error) => error.field === field)?.message ?? null;
}
