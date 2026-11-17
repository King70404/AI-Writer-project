import { API_BASE_URL, getJson, postJson } from "../../../api/client";
import { securitySession } from "../../../api/security-session";
import { parseEstimate, type SendEstimate } from "../../usage/api/budget";
import { parseRuleRevision, type RuleRevision } from "./writing-preparation";

type SlotStatus = "ready" | "running" | "completed" | "failed";
export interface Trial {
  readonly id: string;
  readonly version: number;
  readonly chapter_id: string;
  readonly manuscript_revision_id: string;
  readonly plan_revision_id: string;
  readonly rule_version_id: string;
  readonly rule_index: number;
  readonly scene: string;
  readonly plan: string;
  readonly manuscript: string;
  readonly method: string;
  readonly model_name: string;
  readonly model_kind: "local" | "cloud";
  readonly a: {
    readonly status: SlotStatus;
    readonly text: string | null;
    readonly error: string | null;
  };
  readonly b: {
    readonly status: SlotStatus;
    readonly text: string | null;
    readonly error: string | null;
  };
  readonly complete: boolean;
  readonly a_uses_rule?: boolean;
  readonly a_score?: Score;
  readonly b_score?: Score;
}
export interface Template {
  readonly id: string;
  readonly source_project_id: string;
  readonly source_rule_version_id: string;
  readonly name: string;
  readonly instruction: string;
  readonly applies_to: string;
  readonly excludes: string;
  readonly scene_tags: readonly string[];
  readonly priority: number;
}
export interface Annotation {
  readonly id: string;
  readonly chapter_id: string;
  readonly manuscript_revision_id: string;
  readonly rule_version_id: string;
  readonly rule_index: number;
  readonly start: number;
  readonly end: number;
  readonly judgment: "embodied" | "not_embodied" | "not_applicable";
  readonly reason: string;
}
export interface Score {
  readonly focus: number;
  readonly continuity: number;
  readonly subtext: number;
  readonly persistence: number;
  readonly originality: number;
  readonly reason: string;
}
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("方法验证数据无法读取。");
  return value as Record<string, unknown>;
}
function identifier(value: string): string {
  if (!/^[A-Za-z0-9_-]{1,100}$/u.test(value))
    throw new Error("方法验证标识无效。");
  return value;
}
function text(value: unknown): string {
  if (typeof value !== "string") throw new Error("方法验证数据无法读取。");
  return value;
}
function number(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw new Error("方法验证数据无法读取。");
  return value;
}
function nullable(value: unknown): string | null {
  return value === null ? null : text(value);
}
function candidate(value: unknown): Trial["a"] {
  const item = record(value);
  if (
    !["ready", "running", "completed", "failed"].includes(String(item.status))
  )
    throw new Error("方法验证状态无效。");
  return {
    status: item.status as SlotStatus,
    text: nullable(item.text),
    error: nullable(item.error),
  };
}
function trial(value: unknown): Trial {
  const item = record(value);
  if (
    typeof item.complete !== "boolean" ||
    (item.a_uses_rule !== undefined && typeof item.a_uses_rule !== "boolean") ||
    !["local", "cloud"].includes(String(item.model_kind))
  )
    throw new Error("方法验证状态无效。");
  return {
    id: identifier(text(item.id)),
    version: number(item.version),
    chapter_id: identifier(text(item.chapter_id)),
    manuscript_revision_id: identifier(text(item.manuscript_revision_id)),
    plan_revision_id: identifier(text(item.plan_revision_id)),
    rule_version_id: identifier(text(item.rule_version_id)),
    rule_index: number(item.rule_index),
    scene: text(item.scene),
    plan: text(item.plan),
    manuscript: text(item.manuscript),
    method: text(item.method),
    model_name: text(item.model_name),
    model_kind: item.model_kind as "local" | "cloud",
    a: candidate(item.a),
    b: candidate(item.b),
    complete: item.complete,
    ...(item.a_uses_rule === undefined
      ? {}
      : {
          a_uses_rule: item.a_uses_rule,
          a_score: score(item.a_score),
          b_score: score(item.b_score),
        }),
  };
}
function score(value: unknown): Score {
  const item = record(value);
  const result = {
    focus: number(item.focus),
    continuity: number(item.continuity),
    subtext: number(item.subtext),
    persistence: number(item.persistence),
    originality: number(item.originality),
    reason: text(item.reason),
  };
  if (
    [
      result.focus,
      result.continuity,
      result.subtext,
      result.persistence,
      result.originality,
    ].some((rating) => rating < 1 || rating > 5)
  )
    throw new Error("方法评分数据无效。");
  return result;
}
function template(value: unknown): Template {
  const item = record(value);
  if (
    !Array.isArray(item.scene_tags) ||
    !item.scene_tags.every((tag: unknown) => typeof tag === "string")
  )
    throw new Error("方法模板数据无法读取。");
  return {
    id: identifier(text(item.id)),
    source_project_id: identifier(text(item.source_project_id)),
    source_rule_version_id: identifier(text(item.source_rule_version_id)),
    name: text(item.name),
    instruction: text(item.instruction),
    applies_to: text(item.applies_to),
    excludes: text(item.excludes),
    scene_tags: item.scene_tags,
    priority: number(item.priority),
  };
}
function annotation(value: unknown): Annotation {
  const item = record(value);
  if (
    !["embodied", "not_embodied", "not_applicable"].includes(
      String(item.judgment),
    )
  )
    throw new Error("方法标注状态无效。");
  return {
    id: identifier(text(item.id)),
    chapter_id: identifier(text(item.chapter_id)),
    manuscript_revision_id: identifier(text(item.manuscript_revision_id)),
    rule_version_id: identifier(text(item.rule_version_id)),
    rule_index: number(item.rule_index),
    start: number(item.start),
    end: number(item.end),
    judgment: item.judgment as Annotation["judgment"],
    reason: text(item.reason),
  };
}
function list<T>(value: unknown, decode: (item: unknown) => T): T[] {
  if (!Array.isArray(value)) throw new Error("方法验证数据无法读取。");
  return value.map(decode);
}
function root(project: string): string {
  return `projects/${identifier(project)}/writing`;
}
async function read<T>(
  path: string,
  decode: (value: unknown) => T,
): Promise<T> {
  return (await getJson(path, decode)).data;
}
async function send<T>(
  path: string,
  input: unknown,
  decode: (value: unknown) => T,
): Promise<T> {
  const proof = await securitySession.getValidSession();
  return (
    await postJson(path, input, decode, {
      headers: { "X-CSRF-Token": proof.csrfToken },
    })
  ).data;
}
export const methodClient = {
  listTrials: (project: string, chapter: string) =>
    read(
      `${root(project)}/method-trials?chapter_id=${identifier(chapter)}`,
      (value) => list(value, trial),
    ),
  prepare: (project: string, input: object) =>
    send(`${root(project)}/method-trials`, input, trial),
  get: (project: string, id: string) =>
    read(`${root(project)}/method-trials/${identifier(id)}`, trial),
  estimate: (
    project: string,
    id: string,
    slot: "A" | "B",
  ): Promise<SendEstimate> =>
    read(
      `${root(project)}/method-trials/${identifier(id)}/estimate/${slot}`,
      parseEstimate,
    ),
  send: (
    project: string,
    id: string,
    slot: "A" | "B",
    version: number,
    cloudConsent: boolean,
  ) =>
    send(
      `${root(project)}/method-trials/${identifier(id)}/send`,
      { slot, expected_version: version, cloud_consent: cloudConsent },
      trial,
    ),
  rate: (project: string, id: string, version: number, a: Score, b: Score) =>
    send(
      `${root(project)}/method-trials/${identifier(id)}/rate`,
      { expected_version: version, a, b },
      trial,
    ),
  annotations: (project: string, chapter: string) =>
    read(
      `${root(project)}/method-annotations/${identifier(chapter)}`,
      (value) => list(value, annotation),
    ),
  annotate: (project: string, input: object) =>
    send(`${root(project)}/method-annotations`, input, (value) =>
      identifier(text(record(value).id)),
    ),
  templates: (project: string) =>
    read(`${root(project)}/method-templates`, (value) => list(value, template)),
  createTemplate: (project: string, input: object) =>
    send(`${root(project)}/method-templates`, input, template),
  copyTemplate: (project: string, id: string): Promise<RuleRevision> =>
    send(
      `${root(project)}/method-templates/${identifier(id)}/copy`,
      { confirmed: true },
      (value) => parseRuleRevision(value, project),
    ),
  async deleteTemplate(project: string, id: string): Promise<void> {
    const proof = await securitySession.getValidSession();
    const response = await fetch(
      `${API_BASE_URL}/${root(project)}/method-templates/${identifier(id)}`,
      {
        method: "DELETE",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": proof.csrfToken,
        },
        body: "{}",
      },
    );
    if (!response.ok) throw new Error("删除模板失败，请重试。");
  },
};
export type MethodClient = typeof methodClient;
