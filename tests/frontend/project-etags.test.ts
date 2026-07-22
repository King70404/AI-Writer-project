import { describe, expect, it } from "vitest";

import {
  createVersionedProjectResource,
  parseProjectEtag,
} from "../../frontend/src/features/projects/api/etags";
import { ProjectContractError } from "../../frontend/src/features/projects/api/parsers";
import { projectResponse } from "./project-detail-support";

describe("Project strong ETag contract", () => {
  it.each([
    ['"1"', 1],
    [`"${Number.MAX_SAFE_INTEGER}"`, Number.MAX_SAFE_INTEGER],
  ] as const)("accepts canonical safe ETag %s", (etag, version) => {
    expect(parseProjectEtag(etag)).toEqual({ etag, version });
  });

  it.each([
    null,
    "",
    "1",
    'W/"1"',
    "*",
    '"0"',
    '"-1"',
    '"1.0"',
    '"1e2"',
    '"true"',
    '"01"',
    '"1", "2"',
    '"1","2"',
    ' "1"',
    '"1" ',
    '"9223372036854775808"',
    '"9007199254740992"',
  ])("rejects non-canonical or unsafe ETag without echoing it: %s", (etag) => {
    let thrown: unknown;
    try {
      parseProjectEtag(etag);
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(ProjectContractError);
    expect(String(thrown)).toBe(
      "ProjectContractError: Project API response did not match its contract.",
    );
  });

  it("creates an immutable resource only when ETag and body versions agree", () => {
    const resource = createVersionedProjectResource(projectResponse(2), '"2"');
    expect(resource).toMatchObject({ etag: '"2"', version: 2 });
    expect(Object.isFrozen(resource)).toBe(true);
    expect(Object.isFrozen(resource.project)).toBe(true);
    expect(() =>
      createVersionedProjectResource(projectResponse(2), '"1"'),
    ).toThrow(ProjectContractError);
    expect(() =>
      createVersionedProjectResource(projectResponse(1), null),
    ).toThrow(ProjectContractError);
  });
});
