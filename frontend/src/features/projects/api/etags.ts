import type { ProjectResponse, VersionedProjectResource } from "./contracts";
import { ProjectContractError } from "./parsers";
import { parseStrongVersionEtag } from "../../../api/etags";

export interface ParsedProjectEtag {
  readonly etag: string;
  readonly version: number;
}

export function parseProjectEtag(value: string | null): ParsedProjectEtag {
  try {
    return parseStrongVersionEtag(value);
  } catch {
    throw new ProjectContractError();
  }
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
