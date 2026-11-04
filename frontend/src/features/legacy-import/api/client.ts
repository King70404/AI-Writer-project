import { getJson, postJson, putJson } from "../../../api/client";
import { securitySession } from "../../../api/security-session";

export type HeadingMode = "auto" | "chinese" | "markdown" | "single";
export interface ChapterBoundary {
  readonly title: string;
  readonly start: number;
  readonly body_start: number;
  readonly end: number;
}
export interface PreviewChapter extends ChapterBoundary {
  readonly body: string;
}
export interface ImportPreview {
  readonly preview_id: string;
  readonly version: number;
  readonly source_sha256: string;
  readonly chapters: readonly PreviewChapter[];
  readonly expires_at: string;
  readonly original_line_endings_normalized: boolean;
}
export interface ImportReceipt {
  readonly project_id: string;
  readonly first_chapter_id: string;
}
export interface CommitInput {
  readonly preview_version: number;
  readonly source_sha256: string;
  readonly idempotency_key: string;
  readonly title: string;
}
export interface ImportClient {
  readonly preview: (text: string, mode: HeadingMode) => Promise<ImportPreview>;
  readonly getPreview: (id: string) => Promise<ImportPreview>;
  readonly update: (
    id: string,
    version: number,
    chapters: readonly ChapterBoundary[],
  ) => Promise<ImportPreview>;
  readonly commit: (id: string, input: CommitInput) => Promise<ImportReceipt>;
  readonly receipt: (id: string) => Promise<ImportReceipt>;
}
function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error("导入服务返回了无法识别的数据。");
  return value as Record<string, unknown>;
}
function number(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw new Error("导入服务返回了无法识别的数据。");
  return value;
}
function string(value: unknown): string {
  if (typeof value !== "string")
    throw new Error("导入服务返回了无法识别的数据。");
  return value;
}
function preview(value: unknown): ImportPreview {
  const data = object(value);
  if (!Array.isArray(data.chapters))
    throw new Error("导入服务返回了无法识别的数据。");
  const chapters = data.chapters.map((item): PreviewChapter => {
    const row = object(item);
    return {
      title: string(row.title),
      start: number(row.start),
      body_start: number(row.body_start),
      end: number(row.end),
      body: string(row.body),
    };
  });
  return {
    preview_id: string(data.preview_id),
    version: number(data.version),
    source_sha256: string(data.source_sha256),
    expires_at: string(data.expires_at),
    original_line_endings_normalized:
      data.original_line_endings_normalized === true,
    chapters,
  };
}
function receipt(value: unknown): ImportReceipt {
  const data = object(value);
  return {
    project_id: string(data.project_id),
    first_chapter_id: string(data.first_chapter_id),
  };
}
async function write<T>(
  method: "POST" | "PUT",
  path: string,
  body: unknown,
  decode: (value: unknown) => T,
): Promise<T> {
  const proof = await securitySession.getValidSession();
  try {
    const call = method === "POST" ? postJson : putJson;
    return (
      await call(path, body, decode, {
        headers: { "X-CSRF-Token": proof.csrfToken },
      })
    ).data;
  } catch (error) {
    if (
      typeof error === "object" &&
      error !== null &&
      "status" in error &&
      error.status === 403
    )
      securitySession.clear();
    throw error;
  }
}
export const importClient: ImportClient = {
  preview: async (text, mode) => {
    const upload = await write(
      "POST",
      "imports/uploads",
      { mode },
      (value) => ({ upload_id: string(object(value).upload_id) }),
    );
    let offset = 0;
    let chunk: string[] = [];
    const send = async () => {
      if (!chunk.length) return;
      const length = chunk.length;
      const result = await write(
        "PUT",
        `imports/uploads/${encodeURIComponent(upload.upload_id)}/chunks`,
        { offset, text: chunk.join("") },
        (value) => number(object(value).next_offset),
      );
      if (result !== offset + length)
        throw new Error("导入上传进度不一致，请重新预览。");
      offset = result;
      chunk = [];
    };
    for (const character of text) {
      chunk.push(character);
      if (chunk.length === 100_000) await send();
    }
    await send();
    return write(
      "POST",
      `imports/uploads/${encodeURIComponent(upload.upload_id)}/finish`,
      {},
      preview,
    );
  },
  getPreview: (id) =>
    getJson(`imports/${encodeURIComponent(id)}/preview`, preview).then(
      (result) => result.data,
    ),
  update: (id, expected_version, chapters) =>
    write(
      "PUT",
      `imports/${encodeURIComponent(id)}/preview`,
      { expected_version, chapters },
      preview,
    ),
  commit: (id, input) =>
    write("POST", `imports/${encodeURIComponent(id)}/commit`, input, receipt),
  receipt: (id) =>
    getJson(`imports/${encodeURIComponent(id)}/receipt`, receipt).then(
      (result) => result.data,
    ),
};
