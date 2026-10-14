import { getJson, postJson, putJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";
import { AIWritingError } from "./ai-writing";
import {
  parseModelProfile,
  workflowFailureMessage,
  type ModelProfile,
} from "./ai-workflow";

export interface WritingRule {
  readonly name: string;
  readonly instruction: string;
  readonly applies_to: string;
}
export interface RuleRevision {
  readonly id: string;
  readonly rule_id: string;
  readonly project_id: string;
  readonly version: number;
  readonly title: string;
  readonly reference_id: string | null;
  readonly rules: readonly WritingRule[];
  readonly created_at: string;
}
export interface ReferenceUnit {
  readonly id: string;
  readonly start: number;
  readonly end: number;
  readonly text: string;
}
export interface UnitAnalysis {
  readonly unit_id: string;
  readonly quote: string;
  readonly function: string;
  readonly effect: string;
  readonly rationale: string;
  readonly transfer: string;
}
export interface WritingReference {
  readonly id: string;
  readonly project_id: string;
  readonly title: string;
  readonly text: string;
  readonly granularity: "sentence" | "paragraph";
  readonly units: readonly ReferenceUnit[];
  readonly model_snapshot: ModelProfile;
  readonly messages: readonly {
    readonly role: string;
    readonly content: string;
  }[];
  readonly status: "ready" | "analyzing" | "analyzed" | "failed";
  readonly version: number;
  readonly attempts: number;
  readonly last_error: string | null;
  readonly analysis: null | {
    readonly units: readonly UnitAnalysis[];
    readonly long_form_notes: string;
    readonly rules: readonly WritingRule[];
  };
  readonly created_at: string;
}
export interface PlanBeat {
  readonly id: string;
  readonly action: string;
  readonly change: string;
}
export interface PlanScene {
  readonly id: string;
  readonly title: string;
  readonly setting: string;
  readonly character_ids: readonly string[];
  readonly beats: readonly PlanBeat[];
}
export interface ChapterPlanInput {
  readonly memory_focuses: readonly string[];
  readonly target_characters: number;
  readonly chapter_goal: string;
  readonly conflict: string;
  readonly continuity_notes: string;
  readonly scenes: readonly PlanScene[];
  readonly include_story_bible: boolean;
  readonly writing_rule_revision_ids: readonly string[];
}
export interface ChapterPlan extends ChapterPlanInput {
  readonly chapter_id: string;
  readonly project_id: string;
  readonly version: number;
  readonly revision_id: string;
  readonly updated_at: string;
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function text(value: unknown): value is string {
  return typeof value === "string";
}
function id(value: unknown): value is string {
  return text(value) && /^[A-Za-z0-9_-]{1,80}$/u.test(value);
}
function integer(value: unknown, minimum = 0): value is number {
  return (
    typeof value === "number" && Number.isSafeInteger(value) && value >= minimum
  );
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text);
}
function invalid(): never {
  throw new AIWritingError(
    "范文或规划数据无法安全读取，请重新加载。",
    "INVALID_RESPONSE",
  );
}
function array<T>(value: unknown, decode: (item: unknown) => T): T[] {
  if (!Array.isArray(value)) invalid();
  return value.map(decode);
}
function rule(value: unknown): WritingRule {
  if (
    !object(value) ||
    !text(value.name) ||
    !text(value.instruction) ||
    !text(value.applies_to)
  )
    invalid();
  return {
    name: value.name,
    instruction: value.instruction,
    applies_to: value.applies_to,
  };
}
export function parseRuleRevision(
  value: unknown,
  projectId: string,
): RuleRevision {
  if (
    !object(value) ||
    !id(value.id) ||
    !id(value.rule_id) ||
    value.project_id !== projectId ||
    !integer(value.version, 1) ||
    !text(value.title) ||
    !(value.reference_id === null || id(value.reference_id)) ||
    !text(value.created_at)
  )
    invalid();
  return {
    id: value.id,
    rule_id: value.rule_id,
    project_id: projectId,
    version: value.version,
    title: value.title,
    reference_id: value.reference_id,
    rules: array(value.rules, rule),
    created_at: value.created_at,
  };
}
export function parseWritingReference(
  value: unknown,
  projectId: string,
): WritingReference {
  if (
    !object(value) ||
    !id(value.id) ||
    value.project_id !== projectId ||
    !text(value.title) ||
    !text(value.text) ||
    (value.granularity !== "sentence" && value.granularity !== "paragraph") ||
    !object(value.model_snapshot) ||
    !text(value.status) ||
    !["ready", "analyzing", "analyzed", "failed"].includes(value.status) ||
    !integer(value.version, 1) ||
    !integer(value.attempts) ||
    value.attempts > 3 ||
    !(value.last_error === null || text(value.last_error)) ||
    !text(value.created_at)
  )
    invalid();
  const source = Array.from(value.text);
  const units = array(value.units, (unit): ReferenceUnit => {
    if (
      !object(unit) ||
      !id(unit.id) ||
      !integer(unit.start) ||
      !integer(unit.end, 1) ||
      unit.start >= unit.end ||
      unit.end > source.length ||
      !text(unit.text) ||
      source.slice(unit.start, unit.end).join("") !== unit.text
    )
      invalid();
    return { id: unit.id, start: unit.start, end: unit.end, text: unit.text };
  });
  if (
    !units.length ||
    units.length > 40 ||
    new Set(units.map((unit) => unit.id)).size !== units.length ||
    units.some((unit, index) => index > 0 && unit.start < units[index - 1].end)
  )
    invalid();
  const messages = array(
    value.messages,
    (message): { role: string; content: string } => {
      if (
        !object(message) ||
        (message.role !== "system" && message.role !== "user") ||
        !text(message.content)
      )
        invalid();
      return { role: message.role, content: message.content };
    },
  );
  let analysis: WritingReference["analysis"] = null;
  if (value.analysis !== null) {
    if (!object(value.analysis) || !text(value.analysis.long_form_notes))
      invalid();
    analysis = {
      units: array(value.analysis.units, (unit): UnitAnalysis => {
        if (
          !object(unit) ||
          !id(unit.unit_id) ||
          !text(unit.quote) ||
          !unit.quote.trim() ||
          !text(unit.function) ||
          !text(unit.effect) ||
          !text(unit.rationale) ||
          !text(unit.transfer) ||
          !units
            .find((item) => item.id === unit.unit_id)
            ?.text.includes(unit.quote)
        )
          invalid();
        return {
          unit_id: unit.unit_id,
          quote: unit.quote,
          function: unit.function,
          effect: unit.effect,
          rationale: unit.rationale,
          transfer: unit.transfer,
        };
      }),
      long_form_notes: value.analysis.long_form_notes,
      rules: array(value.analysis.rules, rule),
    };
    if (
      analysis.units.length !== units.length ||
      new Set(analysis.units.map((unit) => unit.unit_id)).size !== units.length
    )
      invalid();
  }
  if ((value.status === "analyzed") !== (analysis !== null)) invalid();
  return {
    id: value.id,
    project_id: projectId,
    title: value.title,
    text: value.text,
    granularity: value.granularity,
    units,
    model_snapshot: parseModelProfile({
      ...value.model_snapshot,
      has_key: false,
    }),
    messages,
    status: value.status as WritingReference["status"],
    version: value.version,
    attempts: value.attempts,
    last_error: value.last_error,
    analysis,
    created_at: value.created_at,
  };
}
export function parseChapterPlan(
  value: unknown,
  projectId: string,
  chapterId: string,
): ChapterPlan | null {
  if (value === null) return null;
  if (
    !object(value) ||
    value.project_id !== projectId ||
    value.chapter_id !== chapterId ||
    !integer(value.version, 1) ||
    !id(value.revision_id) ||
    !text(value.updated_at) ||
    !strings(value.memory_focuses) ||
    !integer(value.target_characters, 200) ||
    value.target_characters > 20000 ||
    !text(value.chapter_goal) ||
    !text(value.conflict) ||
    !text(value.continuity_notes) ||
    typeof value.include_story_bible !== "boolean" ||
    !strings(value.writing_rule_revision_ids)
  )
    invalid();
  return {
    chapter_id: chapterId,
    project_id: projectId,
    version: value.version,
    revision_id: value.revision_id,
    updated_at: value.updated_at,
    memory_focuses: value.memory_focuses,
    target_characters: value.target_characters,
    chapter_goal: value.chapter_goal,
    conflict: value.conflict,
    continuity_notes: value.continuity_notes,
    include_story_bible: value.include_story_bible,
    writing_rule_revision_ids: value.writing_rule_revision_ids,
    scenes: array(value.scenes, (scene): PlanScene => {
      if (
        !object(scene) ||
        !id(scene.id) ||
        !text(scene.title) ||
        !text(scene.setting) ||
        !strings(scene.character_ids)
      )
        invalid();
      return {
        id: scene.id,
        title: scene.title,
        setting: scene.setting,
        character_ids: scene.character_ids,
        beats: array(scene.beats, (beat): PlanBeat => {
          if (
            !object(beat) ||
            !id(beat.id) ||
            !text(beat.action) ||
            !text(beat.change)
          )
            invalid();
          return { id: beat.id, action: beat.action, change: beat.change };
        }),
      };
    }),
  };
}

export function analysisFailureMessage(code: string): string {
  const messages: Record<string, string> = {
    WritingOutputInvalid:
      "模型回复未包含完整的句段分析，或引文与原文不符。请缩短范文或调整模型输出上限后重新准备分析。",
    WRITING_OUTPUT_INVALID:
      "模型回复未包含完整的句段分析，或引文与原文不符。请缩短范文或调整模型输出上限后重新准备分析。",
    WritingInterrupted:
      "上次分析因服务停止而中断。请核对服务商的请求状态，再决定是否手动重试。",
  };
  return (
    messages[code] ??
    workflowFailureMessage(code)
      .replaceAll("手动恢复任务", "手动重试分析")
      .replace("上次生成", "上次分析")
  );
}

export function preparationError(error: unknown): AIWritingError {
  if (error instanceof AIWritingError) return error;
  if (error instanceof ApiError) {
    if ([401, 403].includes(error.status)) securitySession.clear();
    const codes: Record<string, string> = {
      INVALID_RESPONSE: "范文或规划数据无法安全读取，请重新加载。",
      PLANNING_CONFLICT:
        "章节规划已在其他页面更新。当前草稿已保留，请重新加载后再修改。",
      PLANNING_REFERENCE_INVALID:
        "规划引用的人物或写作规则不可用，请刷新并重新选择。",
      PLANNING_UNAVAILABLE: "章节规划暂不可用，请先备份并启用新版 AI 协作。",
      WRITING_STUDIO_UNAVAILABLE:
        "范文分析暂不可用，请先备份并启用新版 AI 协作。",
      WRITING_CONFLICT:
        "范文状态或规则版本已改变。当前草稿已保留，请重新加载并选择最新版本后再操作。",
      WRITING_CONSENT_REQUIRED:
        "请先勾选向该云端模型发送此范文的同意，再确认分析。",
      WRITING_OUTPUT_INVALID: analysisFailureMessage("WRITING_OUTPUT_INVALID"),
      AI_WORKFLOW_SCHEMA_REQUIRED:
        "请先点击“备份并启用 AI 协作”，再打开范文与规划。",
    };
    const statuses: Record<number, string> = {
      401: "页面会话已失效，请刷新后重试。",
      403: "页面无法发送请求，请刷新后重试。",
      404: "范文、规则或章节不存在，请重新加载。",
      409: "数据或模型设置已改变，请重新加载确认。",
      422: "请检查范文长度、句段数量及规划字段；单份范文最多 8000 字、40 个句段。",
      502: "模型没有返回完整合格的分析，请检查模型输出上限后手动重试。",
      503: "功能暂不可用，请先启用 AI 协作并检查模型设置。",
    };
    return new AIWritingError(
      codes[error.code] ??
        (error.code.startsWith("AI_PROVIDER_") ||
        error.code.startsWith("MODEL_")
          ? workflowFailureMessage(error.code)
          : (statuses[error.status] ??
            "操作未完成，请重新加载确认已保存内容。")),
      error.code,
    );
  }
  return new AIWritingError(
    "连接中断，请重新加载确认是否已保存；不会自动重发模型请求。",
    "NETWORK_ERROR",
  );
}
async function request<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw preparationError(error);
  }
}
async function mutate<T>(
  path: string,
  input: unknown,
  decode: (value: unknown) => T,
  put = false,
): Promise<T> {
  return request(async () => {
    const proof = await securitySession.getValidSession();
    return (put ? putJson : postJson)(path, input, decode, {
      headers: { "X-CSRF-Token": proof.csrfToken },
    });
  });
}
function projectPath(projectId: string): string {
  if (!id(projectId)) invalid();
  return `projects/${projectId}/writing`;
}
function resourceId(value: string): string {
  if (!id(value)) invalid();
  return value;
}
export const writingPreparationClient = {
  references: (projectId: string) =>
    request(() =>
      getJson(`${projectPath(projectId)}/references`, (value) =>
        array(value, (item) => parseWritingReference(item, projectId)),
      ),
    ),
  reference: (projectId: string, referenceId: string) =>
    request(() =>
      getJson(
        `${projectPath(projectId)}/references/${resourceId(referenceId)}`,
        (value) => parseWritingReference(value, projectId),
      ),
    ),
  prepareReference: (
    projectId: string,
    input: {
      title: string;
      text: string;
      granularity: "sentence" | "paragraph";
      profile_id: string;
    },
  ) =>
    mutate(`${projectPath(projectId)}/references`, input, (value) =>
      parseWritingReference(value, projectId),
    ),
  analyze: (
    projectId: string,
    reference: WritingReference,
    cloudConsent: boolean,
  ) =>
    mutate(
      `${projectPath(projectId)}/references/${resourceId(reference.id)}/analyze`,
      { expected_version: reference.version, cloud_consent: cloudConsent },
      (value) => parseWritingReference(value, projectId),
    ),
  rules: (projectId: string) =>
    request(() =>
      getJson(`${projectPath(projectId)}/rules`, (value) =>
        array(value, (item) => parseRuleRevision(item, projectId)),
      ),
    ),
  confirmRules: (
    projectId: string,
    input: {
      title: string;
      reference_id: string | null;
      rules: readonly WritingRule[];
    },
    previous?: RuleRevision,
  ) =>
    mutate(
      `${projectPath(projectId)}/rules${previous ? `/${resourceId(previous.rule_id)}/versions` : ""}`,
      {
        ...input,
        confirmed: true,
        ...(previous ? { expected_version: previous.version } : {}),
      },
      (value) => parseRuleRevision(value, projectId),
    ),
  plan: (projectId: string, chapterId: string) =>
    request(() =>
      getJson(`chapters/${resourceId(chapterId)}/planning`, (value) =>
        parseChapterPlan(value, projectId, chapterId),
      ),
    ),
  savePlan: (
    projectId: string,
    chapterId: string,
    input: ChapterPlanInput,
    expectedVersion: number,
  ) =>
    mutate(
      `chapters/${resourceId(chapterId)}/planning`,
      { ...input, expected_version: expectedVersion },
      (value) => {
        const plan = parseChapterPlan(value, projectId, chapterId);
        if (!plan) invalid();
        return plan;
      },
      true,
    ),
};
export type WritingPreparationClient = typeof writingPreparationClient;
