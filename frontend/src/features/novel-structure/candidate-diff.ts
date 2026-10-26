/**
 * 原文/候选的本地只读差异（B1）。完全在浏览器内计算，不发送任何请求、不调用模型，
 * 也不修改原文或模型原始候选。
 *
 * 切分规则：中日韩等非 ASCII 字符按单个 Unicode 码点比较（代理对不会被拆开），
 * 连续的 ASCII 字母数字视为一个词，连续空白视为一段，其余符号逐个比较。
 * 先去掉公共前后缀，再用 Myers 最短编辑脚本；编辑量或长度超过上限时不再细分，
 * 整段标为“删除原文 / 插入候选”，并通过 `approximate` 明确告知。
 */

export type DiffSegmentType = "equal" | "delete" | "insert";

export interface DiffSegment {
  readonly type: DiffSegmentType;
  readonly text: string;
}

export interface TextDiff {
  readonly segments: readonly DiffSegment[];
  /** 被删除/新增的非空白字符数（与正文字数口径一致）。 */
  readonly deletedCharacters: number;
  readonly insertedCharacters: number;
  /** 超出比较上限时为 true：仅整体对照，没有逐字标记。 */
  readonly approximate: boolean;
}

export const MAX_DIFF_TOKENS = 20_000;
export const MAX_DIFF_EDITS = 2_000;

const TOKEN = /[A-Za-z0-9_]+|\s+|[\s\S]/gu;

export function tokenize(text: string): string[] {
  return text.match(TOKEN) ?? [];
}

function nonWhitespace(text: string): number {
  let count = 0;
  for (const character of text) if (!/\s/u.test(character)) count += 1;
  return count;
}

function push(segments: DiffSegment[], type: DiffSegmentType, text: string) {
  if (!text) return;
  const last = segments[segments.length - 1];
  if (last && last.type === type) {
    segments[segments.length - 1] = { type, text: last.text + text };
  } else {
    segments.push({ type, text });
  }
}

/** Myers 差异；返回 null 表示编辑量超过上限。 */
function myers(
  a: readonly string[],
  b: readonly string[],
  maxEdits: number,
): { type: DiffSegmentType; token: string }[] | null {
  const n = a.length;
  const m = b.length;
  const max = Math.min(n + m, maxEdits);
  const offset = max + 1;
  const v = new Int32Array(2 * max + 3);
  const trace: Int32Array[] = [];
  let found = -1;
  for (let d = 0; d <= max; d += 1) {
    trace.push(v.slice());
    for (let k = -d; k <= d; k += 2) {
      let x =
        k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1])
          ? v[offset + k + 1]
          : v[offset + k - 1] + 1;
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) {
        x += 1;
        y += 1;
      }
      v[offset + k] = x;
      if (x >= n && y >= m) {
        found = d;
        break;
      }
    }
    if (found >= 0) break;
  }
  if (found < 0) return null;
  const edits: { type: DiffSegmentType; token: string }[] = [];
  let x = n;
  let y = m;
  for (let d = found; d > 0; d -= 1) {
    const previous = trace[d];
    const k = x - y;
    const down =
      k === -d ||
      (k !== d && previous[offset + k - 1] < previous[offset + k + 1]);
    const previousK = down ? k + 1 : k - 1;
    const previousX = previous[offset + previousK];
    const previousY = previousX - previousK;
    while (x > previousX && y > previousY) {
      x -= 1;
      y -= 1;
      edits.push({ type: "equal", token: a[x] });
    }
    if (down) {
      y -= 1;
      edits.push({ type: "insert", token: b[y] });
    } else {
      x -= 1;
      edits.push({ type: "delete", token: a[x] });
    }
  }
  while (x > 0 && y > 0) {
    x -= 1;
    y -= 1;
    edits.push({ type: "equal", token: a[x] });
  }
  return edits.reverse();
}

export function diffText(
  original: string,
  candidate: string,
  limits: { readonly maxTokens?: number; readonly maxEdits?: number } = {},
): TextDiff {
  const maxTokens = limits.maxTokens ?? MAX_DIFF_TOKENS;
  const maxEdits = limits.maxEdits ?? MAX_DIFF_EDITS;
  const a = tokenize(original);
  const b = tokenize(candidate);
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start])
    start += 1;
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA -= 1;
    endB -= 1;
  }
  const middleA = a.slice(start, endA);
  const middleB = b.slice(start, endB);
  const segments: DiffSegment[] = [];
  push(segments, "equal", a.slice(0, start).join(""));
  const edits =
    middleA.length + middleB.length > maxTokens
      ? null
      : myers(middleA, middleB, maxEdits);
  const approximate = edits === null;
  if (edits === null) {
    push(segments, "delete", middleA.join(""));
    push(segments, "insert", middleB.join(""));
  } else {
    for (const edit of edits) push(segments, edit.type, edit.token);
  }
  push(segments, "equal", a.slice(endA).join(""));
  let deletedCharacters = 0;
  let insertedCharacters = 0;
  for (const segment of segments) {
    if (segment.type === "delete")
      deletedCharacters += nonWhitespace(segment.text);
    if (segment.type === "insert")
      insertedCharacters += nonWhitespace(segment.text);
  }
  return { segments, deletedCharacters, insertedCharacters, approximate };
}
