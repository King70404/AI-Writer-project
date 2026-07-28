const STRONG_VERSION_ETAG = /^"([1-9]\d*)"$/u;
const MAX_SIGNED_64_BIT = 9_223_372_036_854_775_807n;

export class StrongEtagContractError extends Error {
  public constructor() {
    super("The response ETag did not match the strong version contract.");
    this.name = "StrongEtagContractError";
  }
}

export interface ParsedStrongEtag {
  readonly etag: string;
  readonly version: number;
}

export function parseStrongVersionEtag(value: string | null): ParsedStrongEtag {
  if (value === null) {
    throw new StrongEtagContractError();
  }
  const match = STRONG_VERSION_ETAG.exec(value);
  if (match === null || match[1] === undefined) {
    throw new StrongEtagContractError();
  }
  const integer = BigInt(match[1]);
  if (
    integer > MAX_SIGNED_64_BIT ||
    integer > BigInt(Number.MAX_SAFE_INTEGER)
  ) {
    throw new StrongEtagContractError();
  }
  return { etag: value, version: Number(integer) };
}
