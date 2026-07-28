import { parseStrongVersionEtag } from "../../../api/etags";

import type {
  StoryBibleResponse,
  VersionedStoryBibleResource,
} from "./contracts";
import { StoryBibleContractError } from "./parsers";

export function parseStoryBibleEtag(value: string | null) {
  try {
    return parseStrongVersionEtag(value);
  } catch {
    throw new StoryBibleContractError();
  }
}

export function createVersionedStoryBibleResource(
  storyBible: StoryBibleResponse,
  etagHeader: string | null,
): VersionedStoryBibleResource {
  const parsed = parseStoryBibleEtag(etagHeader);
  if (
    parsed.version !== storyBible.concurrency_version ||
    storyBible.revision_number !== storyBible.concurrency_version
  ) {
    throw new StoryBibleContractError();
  }
  return Object.freeze({
    storyBible: Object.freeze({ ...storyBible }),
    etag: parsed.etag,
    version: parsed.version,
  });
}
