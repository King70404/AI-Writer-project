import { parseStrongVersionEtag } from "../../../api/etags";

import type {
  CharacterResponse,
  VersionedCharacterResource,
} from "./contracts";
import { CharacterContractError } from "./parsers";

export function parseCharacterEtag(value: string | null) {
  try {
    return parseStrongVersionEtag(value);
  } catch {
    throw new CharacterContractError();
  }
}

export function versionedCharacter(
  character: CharacterResponse,
  header: string | null,
): VersionedCharacterResource {
  const parsed = parseCharacterEtag(header);
  if (
    parsed.version !== character.concurrency_version ||
    character.revision_number !== character.concurrency_version
  ) {
    throw new CharacterContractError();
  }
  return Object.freeze({
    character: Object.freeze({ ...character }),
    etag: parsed.etag,
    version: parsed.version,
  });
}
