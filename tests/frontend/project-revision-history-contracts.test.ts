import { describe, expect, it } from "vitest";

import {
  parseProjectRevisionHistoryResponse,
  parseProjectRevisionResponse,
} from "../../frontend/src/features/projects/api/parsers";
import { projectId, timestamp } from "./project-detail-support";

const revisionIds = [
  "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "prv_01ARZ3NDEKTSV4RRFFQ69G5FAW",
  "prv_01ARZ3NDEKTSV4RRFFQ69G5FAX",
] as const;

function item(number: number, current = false) {
  return {
    revision_id: revisionIds[number - 1],
    revision_number: number,
    title: `修订标题 ${number}`,
    created_at: timestamp,
    is_current: current,
  };
}

function page(overrides: Record<string, unknown> = {}) {
  return {
    project_id: projectId,
    current_revision_number: 3,
    items: [item(3, true), item(2), item(1)],
    next_cursor: null,
    has_more: false,
    ...overrides,
  };
}

function snapshot(overrides: Record<string, unknown> = {}) {
  return {
    project_id: projectId,
    revision_id: revisionIds[1],
    revision_number: 2,
    title: "修订标题 2",
    description: "第一行\n第二行",
    created_at: timestamp,
    is_current: false,
    current_revision_number: 3,
    ...overrides,
  };
}

describe("Project revision history response contracts", () => {
  it("accepts the exact descending summary page without descriptions", () => {
    expect(parseProjectRevisionHistoryResponse(page(), projectId)).toEqual(
      page(),
    );
  });

  it("accepts an exact selected immutable snapshot", () => {
    expect(parseProjectRevisionResponse(snapshot(), projectId, 2)).toEqual(
      snapshot(),
    );
  });

  it.each([
    page({ extra: "not-allowed" }),
    page({ items: [{ ...item(3, true), description: "must not leak" }] }),
    page({ items: [item(2), item(3, true)] }),
    page({ items: [item(3, true), item(3, true)] }),
    page({ items: [item(3, false)] }),
    page({ has_more: true, next_cursor: null }),
    page({ has_more: false, next_cursor: "opaque" }),
    page({ project_id: "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW" }),
    page({ items: [{ ...item(3, true), created_at: "2026-07-22T08:30:00" }] }),
  ])("rejects a malformed history page %#", (response) => {
    expect(() =>
      parseProjectRevisionHistoryResponse(response, projectId),
    ).toThrow("Project API response did not match its contract.");
  });

  it.each([
    snapshot({ extra: true }),
    snapshot({ project_id: "prj_01ARZ3NDEKTSV4RRFFQ69G5FAW" }),
    snapshot({ revision_number: 1 }),
    snapshot({ is_current: true }),
    snapshot({ created_at: "2026-07-22T08:30:00" }),
  ])("rejects a malformed revision snapshot %#", (response) => {
    expect(() => parseProjectRevisionResponse(response, projectId, 2)).toThrow(
      "Project API response did not match its contract.",
    );
  });
});
