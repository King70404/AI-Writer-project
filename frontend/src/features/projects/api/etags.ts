import type { ProjectResponse, VersionedProjectResource } from "./contracts";
import { ProjectContractError } from "./parsers";

const STRONG_PROJECT_ETAG = /^"([1-9]\d*)"$/u;
const MAX_SIGNED_64_BIT = 9_223_372_036_854_775_807n;

export interface ParsedProjectEtag {
  readonly etag: string;
  readonly version: number;
}

export function parseProjectEtag(value: string | null): ParsedProjectEtag {
  if (value === null) {
    throw new ProjectContractError();
  }
  const match = STRONG_PROJECT_ETAG.exec(value);
  if (match === null || match[1] === undefined) {
    throw new ProjectContractError();
  }
  const integer = BigInt(match[1]);
  if (
    integer > MAX_SIGNED_64_BIT ||
    integer > BigInt(Number.MAX_SAFE_INTEGER)
  ) {
    throw new ProjectContractError();
  }
  return { etag: value, version: Number(integer) };
}

export function createVersionedProjectResource(
  project: ProjectResponse,
  etagHeader: string | null,
): VersionedProjectResource {
  const parsed = parseProjectEtag(etagHeader);
  if (parsed.version !== project.concurrency_version) {
    throw new ProjectContractError();
  }
  return Object.freeze({
    project: Object.freeze({ ...project }),
    etag: parsed.etag,
    version: parsed.version,
  });
}
