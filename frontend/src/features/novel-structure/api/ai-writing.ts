import { postJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { isCanonicalPrefixedUlid } from "../../../api/identifiers";
import {
  securitySession,
  type SecuritySessionManager,
} from "../../../api/security-session";
import { isManuscript } from "./content";

export type AIOperation = "continue" | "rewrite";
export interface AICandidate {
  readonly operation: AIOperation;
  readonly text: string;
  readonly model: string;
  readonly context: {
    readonly included_sources: readonly string[];
    readonly omitted_sources: readonly string[];
    readonly truncated: boolean;
    readonly character_count: number;
  };
}

export class AIWritingError extends Error {}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
const SOURCES = [
  "current_chapter",
  "outline",
  "story_bible",
  "volume",
  "previous_chapter",
  "characters",
  "project",
];
function sources(value: unknown): value is string[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item: unknown) => typeof item === "string" && SOURCES.includes(item),
    )
  );
}

export function parseAICandidate(
  value: unknown,
  operation: AIOperation,
): AICandidate {
  if (
    !record(value) ||
    value.operation !== operation ||
    !isManuscript(value.text) ||
    !value.text.trim() ||
    Array.from(value.text).length > 50_000 ||
    typeof value.model !== "string" ||
    !/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$/u.test(value.model) ||
    !record(value.context) ||
    !sources(value.context.included_sources) ||
    !sources(value.context.omitted_sources) ||
    typeof value.context.truncated !== "boolean" ||
    typeof value.context.character_count !== "number" ||
    !Number.isInteger(value.context.character_count) ||
    value.context.character_count < 0 ||
    value.context.character_count > 60_000
  ) {
    throw new AIWritingError("本地AI服务返回了无法安全读取的候选。");
  }
  return {
    operation,
    text: value.text,
    model: value.model,
    context: {
      included_sources: [...value.context.included_sources],
      omitted_sources: [...value.context.omitted_sources],
      truncated: value.context.truncated,
      character_count: value.context.character_count,
    },
  };
}

export interface AIWritingClient {
  readonly continueChapter: (
    chapterId: string,
    instruction: string,
    signal?: AbortSignal,
  ) => Promise<AICandidate>;
  readonly rewriteChapterText: (
    chapterId: string,
    text: string,
    instruction: string,
    signal?: AbortSignal,
  ) => Promise<AICandidate>;
}

export function createAIWritingClient(
  session: SecuritySessionManager = securitySession,
): AIWritingClient {
  const generate = async (
    operation: AIOperation,
    chapterId: string,
    instruction: string,
    text: string,
    signal?: AbortSignal,
  ): Promise<AICandidate> => {
    if (
      !isCanonicalPrefixedUlid(chapterId, "chp") ||
      !isManuscript(instruction) ||
      Array.from(instruction).length > 4000 ||
      (operation === "rewrite" &&
        (!isManuscript(text) ||
          !text.trim() ||
          Array.from(text).length > 50_000))
    )
      throw new AIWritingError(
        "输入无效，请检查额外要求或选中文本的长度与内容。",
      );
    try {
      const proof = await session.getValidSession(signal);
      const result = await postJson(
        `chapters/${chapterId}/ai/${operation}`,
        {
          instruction: instruction.trim(),
          ...(operation === "rewrite" ? { text } : {}),
        },
        (value) => parseAICandidate(value, operation),
        { signal, headers: { "X-CSRF-Token": proof.csrfToken } },
      );
      return result.data;
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401 || error.status === 403) session.clear();
        const messages: Record<number, string> = {
          503: "本地AI尚未配置或配置无效。请配置本机OpenAI-compatible服务后再试。",
          502: "无法连接本地AI服务，或AI服务返回了无效响应。",
          504: "本地AI生成超时，请稍后重试。",
          404: "章节不存在或不属于当前项目。",
          422: "输入无效，请检查额外要求或选中文本的长度与内容。",
          409: "小说上下文已更新，请重新生成。",
        };
        throw new AIWritingError(
          messages[error.status] ?? "AI请求未能完成，请检查后手动重试。",
        );
      }
      throw new AIWritingError("AI请求未能完成，请检查本地连接后手动重试。");
    }
  };
  return {
    continueChapter: (id, instruction, signal) =>
      generate("continue", id, instruction, "", signal),
    rewriteChapterText: (id, text, instruction, signal) =>
      generate("rewrite", id, instruction, text, signal),
  };
}
export const aiWritingClient = createAIWritingClient();
