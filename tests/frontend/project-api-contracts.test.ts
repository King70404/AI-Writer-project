import { describe, expect, it } from "vitest";

import {
  parseBackendProjectErrorEnvelope,
  parseProjectListItemResponse,
  parseProjectListResponse,
  parseProjectResponse,
  parseSecuritySessionResponse,
  ProjectContractError,
} from "../../frontend/src/features/projects/api/parsers";

const projectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const secondProjectId = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW";
const revisionId = "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const timestamp = "2026-07-22T08:30:00Z";

function listItem(id = projectId) {
  return {
    project_id: id,
    current_revision_id: revisionId,
    revision_number: 1,
    concurrency_version: 1,
    title: "长篇项目",
    created_at: timestamp,
    updated_at: timestamp,
    revision_created_at: timestamp,
  };
}

function project() {
  return {
    ...listItem(),
    description: "真实简介",
    head_updated_at: timestamp,
  };
}

describe("Project runtime contracts", () => {
  it("accepts exact Project, list and security-session contracts", () => {
    expect(parseProjectResponse(project())).toEqual(project());
    expect(
      parseProjectListResponse({
        items: [listItem(), listItem(secondProjectId)],
        next_cursor: "opaque.cursor/value+safe",
        has_more: true,
      }),
    ).toMatchObject({
      has_more: true,
      next_cursor: "opaque.cursor/value+safe",
    });
    expect(
      parseSecuritySessionResponse({
        csrf_token: "csrf-token-that-is-long-enough-for-contract",
        expires_in_seconds: 3_600,
      }),
    ).toEqual({
      csrf_token: "csrf-token-that-is-long-enough-for-contract",
      expires_in_seconds: 3_600,
    });
  });

  it.each([
    null,
    [],
    "not-an-object",
    { ...project(), description: undefined },
    { ...project(), project_id: "unsafe-id" },
    { ...project(), revision_number: true },
    { ...project(), concurrency_version: 0 },
    { ...project(), updated_at: "2026-07-22T08:30:00" },
    { ...project(), extra: "not allowed" },
  ])("rejects invalid Project responses without echoing input: %#", (value) => {
    expect(() => parseProjectResponse(value)).toThrow(ProjectContractError);
    let thrown: unknown;
    try {
      parseProjectResponse(value);
    } catch (error) {
      thrown = error;
    }
    expect(String(thrown)).not.toContain(JSON.stringify(value));
  });

  it("rejects invalid list arrays, duplicate IDs and cursor invariants", () => {
    expect(() =>
      parseProjectListResponse({
        items: {},
        next_cursor: null,
        has_more: false,
      }),
    ).toThrow(ProjectContractError);
    expect(() =>
      parseProjectListResponse({
        items: [listItem(), listItem()],
        next_cursor: null,
        has_more: false,
      }),
    ).toThrow(ProjectContractError);
    expect(() =>
      parseProjectListResponse({
        items: [listItem()],
        next_cursor: null,
        has_more: true,
      }),
    ).toThrow(ProjectContractError);
    expect(() =>
      parseProjectListResponse({
        items: [listItem()],
        next_cursor: "unexpected",
        has_more: false,
      }),
    ).toThrow(ProjectContractError);
  });

  it("accepts an empty final page and Unicode limits by code point", () => {
    expect(
      parseProjectListResponse({
        items: [],
        next_cursor: null,
        has_more: false,
      }),
    ).toEqual({ items: [], next_cursor: null, has_more: false });
    expect(
      parseProjectListItemResponse({ ...listItem(), title: "😀".repeat(120) }),
    ).toMatchObject({ title: "😀".repeat(120) });
  });

  it("parses only the frozen error envelope and copies nested details", () => {
    const input = {
      error: {
        code: "VALIDATION_ERROR",
        message: "invalid",
        details: { errors: [{ field: "body.title" }] },
        retryable: false,
        suggested_action: null,
      },
      request_id: "req_contract",
    };
    const before = structuredClone(input);
    const parsed = parseBackendProjectErrorEnvelope(input);

    expect(parsed).toEqual(before);
    expect(input).toEqual(before);
    expect(parsed.error.details).not.toBe(input.error.details);
    expect(() =>
      parseBackendProjectErrorEnvelope({
        ...input,
        error: { ...input.error, private_body: "do-not-accept" },
      }),
    ).toThrow(ProjectContractError);
  });

  it("rejects malformed session and list-item primitives", () => {
    expect(() => parseProjectListItemResponse(null)).toThrow(
      ProjectContractError,
    );
    expect(() =>
      parseSecuritySessionResponse({
        csrf_token: "short",
        expires_in_seconds: 1,
      }),
    ).toThrow(ProjectContractError);
    expect(() =>
      parseSecuritySessionResponse({
        csrf_token: "x".repeat(32),
        expires_in_seconds: 0,
      }),
    ).toThrow(ProjectContractError);
    expect(() =>
      parseProjectListItemResponse({ ...listItem(), title: "x".repeat(121) }),
    ).toThrow(ProjectContractError);
  });
});
