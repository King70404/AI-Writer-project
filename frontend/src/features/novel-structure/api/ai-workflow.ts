import { getJson, postJson, putJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";
import { isManuscript } from "./content";
import { AIWritingError, type AIOperation } from "./ai-writing";

export interface ModelProfile {
  readonly id: string;
  readonly name: string;
  readonly kind: "local" | "cloud";
  readonly base_url: string;
  readonly model: string;
  readonly max_output_tokens: number;
  readonly has_key: boolean;
}
export interface ModelInput {
  readonly name: string;
  readonly kind: "local" | "cloud";
  readonly base_url: string;
  readonly model: string;
  readonly max_output_tokens: number;
  readonly api_key?: string;
  readonly clear_key?: boolean;
}
export interface WorkflowCandidate {
  readonly candidate_id: string;
  readonly sequence: number;
  readonly text: string;
  readonly model: string;
  readonly character_count: number;
  readonly status: "pending" | "adopted" | "discarded";
  readonly adopted_revision_id: string | null;
  readonly adopted_version: number | null;
}
export interface WorkflowContextSource {
  readonly source: string;
  readonly references: readonly (readonly [string, string])[];
  readonly text: string;
  readonly reason: string;
  readonly omitted_reason: string | null;
  readonly truncated: boolean;
}
export interface WorkflowRun {
  readonly model_snapshot: ModelProfile | null;
  readonly run_id: string;
  readonly chapter_id: string;
  readonly operation: AIOperation;
  readonly status:
    "ready" | "generating" | "paused" | "interrupted" | "completed";
  readonly base_revision_id: string;
  readonly base_version: number;
  readonly current_revision_id: string;
  readonly current_version: number;
  readonly instruction: string;
  readonly selected_text: string;
  readonly profile_id: string | null;
  readonly max_steps: number;
  readonly max_output_characters: number;
  readonly generated_steps: number;
  readonly generated_characters: number;
  readonly context: {
    readonly text: string;
    readonly sha256: string;
    readonly manifest: {
      readonly included_sources: readonly string[];
      readonly omitted_sources: readonly string[];
      readonly truncated: boolean;
      readonly character_count: number;
      readonly sources: readonly WorkflowContextSource[];
    };
  };
  readonly candidates: readonly WorkflowCandidate[];
  readonly last_error: string | null;
}
export interface RunInput {
  readonly operation: AIOperation;
  readonly instruction: string;
  readonly profile_id: string;
  readonly selected_text: string;
  readonly selection_start: number | null;
  readonly selection_end: number | null;
  readonly max_steps: number;
  readonly max_output_characters: number;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function integer(value: unknown, minimum = 0): value is number {
  return (
    typeof value === "number" && Number.isSafeInteger(value) && value >= minimum
  );
}
function identifier(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9_-]{1,80}$/u.test(value);
}
function strings(value: unknown): value is string[] {
  return (
    Array.isArray(value) &&
    value.every((item: unknown) => typeof item === "string")
  );
}
function invalid(): never {
  throw new AIWritingError("AI协作数据无法安全读取，请刷新后重试。");
}
export function parseModelProfile(value: unknown): ModelProfile {
  if (
    !record(value) ||
    !identifier(value.id) ||
    typeof value.name !== "string" ||
    !["local", "cloud"].includes(String(value.kind)) ||
    typeof value.base_url !== "string" ||
    typeof value.model !== "string" ||
    !integer(value.max_output_tokens, 1) ||
    typeof value.has_key !== "boolean" ||
    Object.hasOwn(value, "api_key")
  )
    invalid();
  return {
    id: value.id,
    name: value.name,
    kind: value.kind as ModelProfile["kind"],
    base_url: value.base_url,
    model: value.model,
    max_output_tokens: value.max_output_tokens,
    has_key: value.has_key,
  };
}
function parseCandidate(value: unknown): WorkflowCandidate {
  if (
    !record(value) ||
    !identifier(value.candidate_id) ||
    !integer(value.sequence, 1) ||
    !isManuscript(value.text) ||
    !value.text.trim() ||
    typeof value.model !== "string" ||
    !integer(value.character_count, 200) ||
    value.character_count > 300 ||
    !["pending", "adopted", "discarded"].includes(String(value.status)) ||
    !(
      value.adopted_revision_id === null ||
      identifier(value.adopted_revision_id)
    ) ||
    !(value.adopted_version === null || integer(value.adopted_version, 1))
  )
    invalid();
  return {
    candidate_id: value.candidate_id,
    sequence: value.sequence,
    text: value.text,
    model: value.model,
    character_count: value.character_count,
    status: value.status as WorkflowCandidate["status"],
    adopted_revision_id: value.adopted_revision_id,
    adopted_version: value.adopted_version,
  };
}
function parseContextSource(value: unknown): WorkflowContextSource {
  if (
    !record(value) ||
    typeof value.source !== "string" ||
    !Array.isArray(value.references) ||
    typeof value.text !== "string" ||
    typeof value.reason !== "string" ||
    !(
      value.omitted_reason === null || typeof value.omitted_reason === "string"
    ) ||
    typeof value.truncated !== "boolean"
  )
    invalid();
  const references = value.references.map(
    (reference: unknown): readonly [string, string] => {
      if (
        !Array.isArray(reference) ||
        reference.length !== 2 ||
        !identifier(reference[0]) ||
        !identifier(reference[1])
      )
        invalid();
      return [reference[0], reference[1]];
    },
  );
  return {
    source: value.source,
    references,
    text: value.text,
    reason: value.reason,
    omitted_reason: value.omitted_reason,
    truncated: value.truncated,
  };
}
export function parseWorkflowRun(
  value: unknown,
  chapterId: string,
): WorkflowRun {
  if (
    !record(value) ||
    !identifier(value.run_id) ||
    value.chapter_id !== chapterId ||
    !["continue", "rewrite"].includes(String(value.operation)) ||
    !["ready", "generating", "paused", "interrupted", "completed"].includes(
      String(value.status),
    ) ||
    !identifier(value.base_revision_id) ||
    !integer(value.base_version, 1) ||
    !identifier(value.current_revision_id) ||
    !integer(value.current_version, 1) ||
    typeof value.instruction !== "string" ||
    !isManuscript(value.selected_text) ||
    (value.operation === "rewrite" && !value.selected_text.trim()) ||
    !(value.profile_id === null || identifier(value.profile_id)) ||
    !integer(value.max_steps, 1) ||
    value.max_steps > 10 ||
    !integer(value.max_output_characters, 200) ||
    value.max_output_characters > 3000 ||
    !integer(value.generated_steps) ||
    !integer(value.generated_characters) ||
    !record(value.context) ||
    typeof value.context.text !== "string" ||
    typeof value.context.sha256 !== "string" ||
    !/^[a-f0-9]{64}$/u.test(value.context.sha256) ||
    !record(value.context.manifest) ||
    !strings(value.context.manifest.included_sources) ||
    !strings(value.context.manifest.omitted_sources) ||
    typeof value.context.manifest.truncated !== "boolean" ||
    !integer(value.context.manifest.character_count) ||
    !Array.isArray(value.context.manifest.sources) ||
    !Array.isArray(value.candidates) ||
    !(value.last_error === null || typeof value.last_error === "string")
  )
    invalid();
  return {
    model_snapshot:
      value.model_snapshot === null || value.model_snapshot === undefined
        ? null
        : parseModelProfile(
            record(value.model_snapshot)
              ? { ...value.model_snapshot, has_key: false }
              : null,
          ),
    run_id: value.run_id,
    chapter_id: chapterId,
    operation: value.operation as AIOperation,
    status: value.status as WorkflowRun["status"],
    base_revision_id: value.base_revision_id,
    base_version: value.base_version,
    current_revision_id: value.current_revision_id,
    current_version: value.current_version,
    instruction: value.instruction,
    selected_text: value.selected_text,
    profile_id: value.profile_id,
    max_steps: value.max_steps,
    max_output_characters: value.max_output_characters,
    generated_steps: value.generated_steps,
    generated_characters: value.generated_characters,
    context: {
      text: value.context.text,
      sha256: value.context.sha256,
      manifest: {
        included_sources: value.context.manifest.included_sources,
        omitted_sources: value.context.manifest.omitted_sources,
        truncated: value.context.manifest.truncated,
        character_count: value.context.manifest.character_count,
        sources: value.context.manifest.sources.map(parseContextSource),
      },
    },
    candidates: value.candidates.map(parseCandidate),
    last_error: value.last_error,
  };
}
async function request<T>(
  action: () => Promise<{ data: T }>,
  context: "workflow" | "model" = "workflow",
): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    if (error instanceof ApiError) {
      if ([401, 403].includes(error.status)) securitySession.clear();
      if (error.code === "AI_WORKFLOW_SCHEMA_REQUIRED")
        throw new AIWritingError(
          "当前数据库需要升级后才能使用 AI 协作。请停止服务，备份后升级，再重新启动；手动写作仍可使用。",
        );
      if (context === "model") {
        const modelErrors: Record<string, string> = {
          MODEL_CREDENTIAL_UNAVAILABLE:
            "Windows 密钥保护失败，未能保存模型密钥。请确认使用启动应用的同一个 Windows 账户后重试。",
          MODEL_CONFIGURATION_UNAVAILABLE:
            "本机模型配置无法读写，请检查应用启动窗口的错误提示后重试。",
          INVALID_MODEL_PROFILE:
            "模型配置无效，请检查服务位置、完整服务地址、模型名称和输出上限。",
        };
        if (modelErrors[error.code])
          throw new AIWritingError(modelErrors[error.code]);
        if ([401, 403].includes(error.status))
          throw new AIWritingError(
            "页面会话已失效，请刷新页面后重新保存模型配置。",
          );
      }
      const messages: Record<number, string> = {
        404: "任务、模型或章节已不存在，请刷新。",
        409: "任务状态或正文已变化，请重新加载；旧候选不会覆盖正文。",
        412: "正文版本已变化，请重新生成候选。",
        422: "请检查模型地址、选区与生成预算。",
        502: "模型未返回合格的候选，请检查服务或调整要求后手动重试。",
        503: "模型尚未配置或暂时不可用，请检查模型设置。",
        504: "模型请求超时，任务已保留，请手动恢复。",
      };
      throw new AIWritingError(
        messages[error.status] ?? "操作未完成，已保存内容不会被覆盖，请重试。",
      );
    }
    throw error instanceof AIWritingError
      ? error
      : new AIWritingError(
          context === "model"
            ? "无法连接本机服务，未能确认模型配置是否保存。请重新运行“启动 AI 网文助手.cmd”，保持启动窗口开启，再刷新页面确认保存结果。"
            : "连接中断，任务仍保存在本地；请刷新确认状态。",
        );
  }
}
async function mutate<T>(
  path: string,
  body: unknown,
  decode: (value: unknown) => T,
  method: "POST" | "PUT" = "POST",
  headers?: Record<string, string>,
  context: "workflow" | "model" = "workflow",
) {
  return request(async () => {
    const proof = await securitySession.getValidSession();
    const call = method === "POST" ? postJson : putJson;
    return call(path, body, decode, {
      headers: { "X-CSRF-Token": proof.csrfToken, ...headers },
    });
  }, context);
}
function runPath(chapterId: string, runId?: string) {
  if (!identifier(chapterId) || (runId !== undefined && !identifier(runId)))
    invalid();
  return `chapters/${chapterId}/ai/runs${runId === undefined ? "" : `/${runId}`}`;
}
export const aiWorkflowClient = {
  models: () =>
    request(
      () =>
        getJson("ai/models", (value) => {
          if (!record(value) || !Array.isArray(value.items)) invalid();
          return value.items.map(parseModelProfile);
        }),
      "model",
    ),
  saveModel: (input: ModelInput, id?: string) => {
    if (id !== undefined && !identifier(id)) invalid();
    return mutate(
      id ? `ai/models/${id}` : "ai/models",
      input,
      parseModelProfile,
      id ? "PUT" : "POST",
      undefined,
      "model",
    );
  },
  list: (chapterId: string) =>
    request(() =>
      getJson(runPath(chapterId), (value) => {
        if (!Array.isArray(value)) invalid();
        return value.map((item: unknown) => parseWorkflowRun(item, chapterId));
      }),
    ),
  create: (chapterId: string, input: RunInput) =>
    mutate(runPath(chapterId), input, (value) =>
      parseWorkflowRun(value, chapterId),
    ),
  action: (
    chapterId: string,
    runId: string,
    action: "generate" | "pause" | "resume",
  ) =>
    mutate(`${runPath(chapterId, runId)}/${action}`, {}, (value) =>
      parseWorkflowRun(value, chapterId),
    ),
  candidate: (
    chapterId: string,
    candidateId: string,
    action: "adopt" | "discard",
    key?: string,
    version?: number,
  ) => {
    if (!identifier(chapterId) || !identifier(candidateId)) invalid();
    return mutate(
      `chapters/${chapterId}/ai/candidates/${candidateId}/${action}`,
      action === "adopt" ? { idempotency_key: key } : {},
      (value) => parseWorkflowRun(value, chapterId),
      "POST",
      version === undefined ? undefined : { "If-Match": `"${version}"` },
    );
  },
};
export type AIWorkflowClient = typeof aiWorkflowClient;
