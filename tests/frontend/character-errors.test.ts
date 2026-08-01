import { describe, expect, it } from "vitest";

import { ApiError } from "../../frontend/src/api/errors";
import {
  characterWriteOutcomeUnknown,
  normalizeCharacterApiError,
  shouldClearCharacterSession,
} from "../../frontend/src/features/character/api/errors";
import { CharacterContractError } from "../../frontend/src/features/character/api/parsers";

function apiError(
  status: number,
  code: string,
  details: Readonly<Record<string, unknown>> = {},
) {
  return new ApiError({
    status,
    code,
    message: "CHARACTER_FRONTEND_SECRET_CANARY",
    details,
    retryable: false,
    suggestedAction: "private",
    requestId: "req_safe",
  });
}

describe("Character safe frontend errors", () => {
  it.each([
    [404, "PROJECT_NOT_FOUND", "project_not_found"],
    [404, "CHARACTER_NOT_FOUND", "character_not_found"],
    [409, "CHARACTER_ID_CONFLICT", "character_id_conflict"],
    [400, "INVALID_CHARACTER_CURSOR", "invalid_cursor"],
    [503, "CHARACTER_PERSISTENCE_UNAVAILABLE", "persistence_unavailable"],
    [503, "CHARACTER_SERVICE_UNAVAILABLE", "service_unavailable"],
    [422, "INVALID_CHARACTER_NAME", "validation"],
    [403, "CSRF_TOKEN_INVALID", "security"],
    [415, "UNSUPPORTED_MEDIA_TYPE", "contract"],
    [418, "OTHER", "unknown"],
  ])("maps %s %s to %s without backend prose", (status, code, kind) => {
    const error = normalizeCharacterApiError(apiError(status, code));
    expect(error.kind).toBe(kind);
    expect(error.message).not.toContain("SECRET_CANARY");
  });

  it("maps abort, network, contract, and unknown values safely", () => {
    expect(
      normalizeCharacterApiError(new DOMException("private", "AbortError"))
        .kind,
    ).toBe("aborted");
    expect(normalizeCharacterApiError(new TypeError("private")).kind).toBe(
      "network",
    );
    expect(normalizeCharacterApiError(new CharacterContractError()).kind).toBe(
      "contract",
    );
    expect(normalizeCharacterApiError({ profile: "private" }).kind).toBe(
      "unknown",
    );
  });

  it("rejects malformed 412 details as a contract failure", () => {
    expect(
      normalizeCharacterApiError(
        apiError(412, "CHARACTER_VERSION_CONFLICT", {
          expected_version: 1,
          actual_version: "2",
        }),
        1,
      ).kind,
    ).toBe("contract");
  });

  it("creates operation-specific outcome-unknown errors and clears only security failures", () => {
    expect(characterWriteOutcomeUnknown("create").code).toContain("CREATE");
    expect(characterWriteOutcomeUnknown("save").code).toContain("SAVE");
    expect(shouldClearCharacterSession(apiError(401, "SESSION_EXPIRED"))).toBe(
      true,
    );
    expect(
      shouldClearCharacterSession(apiError(409, "CHARACTER_ID_CONFLICT")),
    ).toBe(false);
  });
});
