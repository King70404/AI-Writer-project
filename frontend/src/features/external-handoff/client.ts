import { API_BASE_URL, getJson, postJson } from "../../api/client";
import { securitySession } from "../../api/security-session";

export interface HandoffCandidate {
  readonly candidate_id: string;
  readonly text: string;
  readonly status: "pending" | "needs_recheck" | "adopted";
  readonly base_version: number;
}
export interface Handoff {
  readonly handoff_id: string;
  readonly chapter_id: string;
  readonly base_version: number;
  readonly context_sha256: string;
  readonly context: string;
  readonly candidates: readonly HandoffCandidate[];
}
export interface Preview {
  readonly handoff_id: string | null;
  readonly chapter_id: string;
  readonly base_version: number;
  readonly context_sha256: string;
  readonly context: string;
}
export interface HandoffInput {
  readonly instruction: string;
  readonly include_manuscript: boolean;
  readonly include_plan?: boolean;
  readonly rule_revision_ids?: readonly string[];
  readonly fact_revision_ids?: readonly string[];
  readonly context_sha256?: string;
}
export interface HandoffClient {
  readonly preview: (chapter: string, input: HandoffInput) => Promise<Preview>;
  readonly create: (chapter: string, input: HandoffInput) => Promise<Preview>;
  readonly list: (chapter: string) => Promise<readonly Handoff[]>;
  readonly download: (chapter: string, id: string) => Promise<Blob>;
  readonly candidate: (
    chapter: string,
    id: string,
    raw: string,
  ) => Promise<HandoffCandidate>;
  readonly adopt: (
    chapter: string,
    id: string,
    candidateId: string,
    etag: string,
    key: string,
  ) => Promise<void>;
}
const path = (chapter: string) =>
  `chapters/${encodeURIComponent(chapter)}/handoffs`;
function obj(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("交接数据无法读取。");
  return value as Record<string, unknown>;
}
function str(value: unknown): string {
  if (typeof value !== "string") throw new Error("交接数据无法读取。");
  return value;
}
function num(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw new Error("交接数据无法读取。");
  return value;
}
function parsePreview(value: unknown): Preview {
  const d = obj(value);
  return {
    handoff_id: d.handoff_id === null ? null : str(d.handoff_id),
    chapter_id: str(d.chapter_id),
    base_version: num(d.base_version),
    context_sha256: str(d.context_sha256),
    context: str(d.context),
  };
}
function parseCandidate(value: unknown): HandoffCandidate {
  const d = obj(value);
  if (
    d.status !== "pending" &&
    d.status !== "needs_recheck" &&
    d.status !== "adopted"
  )
    throw new Error("交接数据无法读取。");
  return {
    candidate_id: str(d.candidate_id),
    text: str(d.text),
    status: d.status,
    base_version: num(d.base_version),
  };
}
function parseList(value: unknown): readonly Handoff[] {
  if (!Array.isArray(value)) throw new Error("交接数据无法读取。");
  return value.map((item): Handoff => {
    const d = obj(item);
    const p = parsePreview(d);
    if (p.handoff_id === null || !Array.isArray(d.candidates))
      throw new Error("交接数据无法读取。");
    return {
      ...p,
      handoff_id: p.handoff_id,
      candidates: d.candidates.map(parseCandidate),
    };
  });
}
async function write<T>(
  url: string,
  body: unknown,
  decoder: (value: unknown) => T,
  headers: Record<string, string> = {},
): Promise<T> {
  const proof = await securitySession.getValidSession();
  return (
    await postJson(url, body, decoder, {
      headers: { "X-CSRF-Token": proof.csrfToken, ...headers },
    })
  ).data;
}
export const handoffClient: HandoffClient = {
  preview: (chapter, input) =>
    write(`${path(chapter)}/preview`, input, parsePreview),
  create: (chapter, input) => write(path(chapter), input, parsePreview),
  list: (chapter) => getJson(path(chapter), parseList).then((r) => r.data),
  download: async (chapter, id) => {
    const response = await fetch(
      `${API_BASE_URL}/${path(chapter)}/${encodeURIComponent(id)}/download`,
      { credentials: "same-origin" },
    );
    if (!response.ok) throw new Error("交接包下载失败，请检查连接后重试。");
    return response.blob();
  },
  candidate: async (chapter, id, raw) => {
    const proof = await securitySession.getValidSession();
    const response = await fetch(
      `${API_BASE_URL}/${path(chapter)}/${encodeURIComponent(id)}/candidates`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": proof.csrfToken,
        },
        body: raw,
      },
    );
    if (!response.ok)
      throw new Error("导入失败：请检查文件格式、任务归属、长度及正文版本。");
    return parseCandidate((await response.json()) as unknown);
  },
  adopt: async (chapter, id, candidateId, etag, key) => {
    await write(
      `${path(chapter)}/${encodeURIComponent(id)}/candidates/${encodeURIComponent(candidateId)}/adopt`,
      { idempotency_key: key },
      parseCandidate,
      { "If-Match": etag },
    );
  },
};
