export const CHARACTER_NAME_MAX_CODE_POINTS = 120;
export const CHARACTER_ROLE_MAX_CODE_POINTS = 120;
export const CHARACTER_PROFILE_MAX_CODE_POINTS = 50_000;

export type CharacterFieldName = "name" | "role" | "profile";

export interface CharacterFieldError {
  readonly field: CharacterFieldName;
  readonly message: string;
}

const FORBIDDEN_NAME_OR_ROLE = /[\u0000-\u001F\u007F-\u009F\u2028\u2029]/u;
const FORBIDDEN_PROFILE =
  /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F\u2028\u2029]/u;

export function countCharacterCodePoints(value: string): number {
  return [...value].length;
}

export function normalizeCharacterName(value: string): string {
  return value.trim();
}

export function normalizeCharacterRole(value: string): string {
  return value.trim();
}

export function normalizeCharacterProfile(value: string): string {
  return value.replace(/\r\n?/gu, "\n");
}

export function validateCharacterInput(
  name: unknown,
  role: unknown,
  profile: unknown,
): readonly CharacterFieldError[] {
  const errors: CharacterFieldError[] = [];
  if (
    typeof name !== "string" ||
    FORBIDDEN_NAME_OR_ROLE.test(name) ||
    countCharacterCodePoints(normalizeCharacterName(name)) < 1 ||
    countCharacterCodePoints(normalizeCharacterName(name)) >
      CHARACTER_NAME_MAX_CODE_POINTS
  ) {
    errors.push({
      field: "name",
      message: "角色名称必填，且最多为120个有效字符。",
    });
  }
  if (
    typeof role !== "string" ||
    FORBIDDEN_NAME_OR_ROLE.test(role) ||
    countCharacterCodePoints(normalizeCharacterRole(role)) >
      CHARACTER_ROLE_MAX_CODE_POINTS
  ) {
    errors.push({
      field: "role",
      message: "角色定位最多为120个有效字符。",
    });
  }
  if (
    typeof profile !== "string" ||
    FORBIDDEN_PROFILE.test(
      typeof profile === "string" ? normalizeCharacterProfile(profile) : "",
    ) ||
    (typeof profile === "string" &&
      countCharacterCodePoints(normalizeCharacterProfile(profile)) >
        CHARACTER_PROFILE_MAX_CODE_POINTS)
  ) {
    errors.push({
      field: "profile",
      message: "角色档案最多为50000个纯文本字符。",
    });
  }
  return errors;
}

export function errorForCharacterField(
  errors: readonly CharacterFieldError[],
  field: CharacterFieldName,
): string | null {
  return errors.find((error) => error.field === field)?.message ?? null;
}
