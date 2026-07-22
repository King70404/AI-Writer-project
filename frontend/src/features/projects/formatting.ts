export function countUnicodeCodePoints(value: string): number {
  return [...value].length;
}

const projectDateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatProjectTimestamp(value: string): string {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp)
    ? projectDateTimeFormatter.format(new Date(timestamp))
    : "时间不可用";
}
