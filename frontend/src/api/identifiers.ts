const CANONICAL_ULID = /^[0-9A-HJKMNP-TV-Z]{26}$/u;

export type IdentifierPrefix = "prj" | "prv" | "sbl" | "sbr" | "chr" | "crv";

export function isCanonicalPrefixedUlid(
  value: unknown,
  prefix: IdentifierPrefix,
): value is string {
  if (typeof value !== "string") {
    return false;
  }
  const expectedPrefix = `${prefix}_`;
  return (
    value.length === expectedPrefix.length + 26 &&
    value.startsWith(expectedPrefix) &&
    CANONICAL_ULID.test(value.slice(expectedPrefix.length))
  );
}
