import { getJson, postJson } from "../../../api/client";
import { ApiError } from "../../../api/errors";
import { securitySession } from "../../../api/security-session";
import { parseEstimate, type SendEstimate } from "../../usage/api/budget";

/**
 * 规划“建议拆分”（F02 / C-1）。准备只冻结所选目标、既有规划和章节标题，不调用模型；
 * 作者确认预估后才发送一次。模型回复是建议卡，作者勾选采用的卡才写入真实规划，
 * 不会创建或改写章节正文。
 */
export type ProposalStatus = "ready" | "running" | "completed" | "failed";

export interface ChildGoalCard {
  readonly kind: "child_goal";
  readonly title: string;
  readonly volume_id: string | null;
  readonly conflict: string;
  readonly obstacle: string;
  readonly turn: string;
  readonly outcome: string;
  readonly chapter_ids: readonly string[];
  readonly reason: string;
}
export interface ChapterLinkCard {
  readonly kind: "chapter_link";
  readonly chapter_id: string;
  readonly note: string;
  readonly reason: string;
}
export type ProposalCard = ChildGoalCard | ChapterLinkCard;

export interface ProposalAdoption {
  readonly index: number;
  readonly action: "created" | "linked" | "already_linked";
  readonly goal_id: string;
}
export interface FrozenGoal {
  readonly id: string;
  readonly version: number;
  readonly scope: "book" | "volume";
  readonly title: string;
  readonly linked_chapter_ids: readonly string[];
}
export interface PlanProposal {
  readonly id: string;
  readonly version: number;
  readonly goal_id: string;
  readonly status: ProposalStatus;
  readonly model_name: string;
  readonly model_kind: "local" | "cloud";
  readonly author_request: string;
  readonly source: FrozenGoal;
  readonly children: readonly FrozenGoal[];
  readonly volumes: readonly {
    readonly volume_id: string;
    readonly title: string;
  }[];
  readonly chapters: readonly {
    readonly chapter_id: string;
    readonly title: string;
    readonly volume_position: number;
    readonly position: number;
  }[];
  readonly chapters_omitted: number;
  readonly summary: string | null;
  readonly cards: readonly ProposalCard[];
  readonly error: string | null;
  readonly evidence: string | null;
  readonly evidence_truncated: boolean;
  readonly adoptions: readonly ProposalAdoption[];
  readonly request_preview: string;
}
export interface ProposalModel {
  readonly id: string;
  readonly name: string;
  readonly kind: "local" | "cloud";
}

export class PlanProposalError extends Error {
  public readonly code: string;
  public constructor(message: string, code = "NETWORK") {
    super(message);
    this.name = "PlanProposalError";
    this.code = code;
  }
}

function invalid(): never {
  throw new PlanProposalError(
    "拆分建议数据无法安全读取，请刷新。",
    "INVALID_RESPONSE",
  );
}
function obj(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
  return value as Record<string, unknown>;
}
function str(value: unknown): string {
  if (typeof value !== "string") invalid();
  return value;
}
function id(value: unknown): string {
  const result = str(value);
  if (!/^[A-Za-z0-9_-]{1,100}$/u.test(result)) invalid();
  return result;
}
function int(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    invalid();
  return value;
}
function bool(value: unknown): boolean {
  if (typeof value !== "boolean") invalid();
  return value;
}
function list<T>(value: unknown, decode: (v: unknown) => T): T[] {
  if (!Array.isArray(value)) invalid();
  return value.map(decode);
}
function nullable<T>(value: unknown, decode: (v: unknown) => T): T | null {
  return value === null || value === undefined ? null : decode(value);
}
function oneOf<T extends string>(options: readonly T[]) {
  return (value: unknown): T => {
    const result = str(value);
    if (!options.includes(result as T)) invalid();
    return result as T;
  };
}
const status = oneOf<ProposalStatus>([
  "ready",
  "running",
  "completed",
  "failed",
]);
const kind = oneOf<"local" | "cloud">(["local", "cloud"]);
const action = oneOf<ProposalAdoption["action"]>([
  "created",
  "linked",
  "already_linked",
]);
const scope = oneOf<"book" | "volume">(["book", "volume"]);

function frozenGoal(value: unknown): FrozenGoal {
  const item = obj(value);
  return {
    id: id(item.id),
    version: int(item.version),
    scope: scope(item.scope),
    title: str(item.title),
    linked_chapter_ids: list(item.linked_chapter_ids, id),
  };
}
function card(value: unknown): ProposalCard {
  const item = obj(value);
  if (item.kind === "child_goal")
    return {
      kind: "child_goal",
      title: str(item.title),
      volume_id: nullable(item.volume_id, id),
      conflict: str(item.conflict),
      obstacle: str(item.obstacle),
      turn: str(item.turn),
      outcome: str(item.outcome),
      chapter_ids: list(item.chapter_ids, id),
      reason: str(item.reason),
    };
  if (item.kind === "chapter_link")
    return {
      kind: "chapter_link",
      chapter_id: id(item.chapter_id),
      note: str(item.note),
      reason: str(item.reason),
    };
  return invalid();
}

export function parseProposal(value: unknown, projectId: string): PlanProposal {
  const item = obj(value);
  if (item.project_id !== projectId) invalid();
  const model = obj(item.model);
  return {
    id: id(item.id),
    version: int(item.version),
    goal_id: id(item.goal_id),
    status: status(item.status),
    model_name: str(model.name),
    model_kind: kind(model.kind),
    author_request: str(item.author_request),
    source: frozenGoal(item.source),
    children: list(item.children, frozenGoal),
    volumes: list(item.volumes, (raw) => {
      const volume = obj(raw);
      return { volume_id: id(volume.volume_id), title: str(volume.title) };
    }),
    chapters: list(item.chapters, (raw) => {
      const chapter = obj(raw);
      return {
        chapter_id: id(chapter.chapter_id),
        title: str(chapter.title),
        volume_position: int(chapter.volume_position),
        position: int(chapter.position),
      };
    }),
    chapters_omitted: int(item.chapters_omitted),
    summary: nullable(item.summary, str),
    cards: list(item.cards, card),
    error: nullable(item.error, str),
    evidence: nullable(item.evidence, str),
    evidence_truncated: bool(item.evidence_truncated),
    adoptions: list(item.adoptions, (raw) => {
      const adoption = obj(raw);
      return {
        index: int(adoption.index),
        action: action(adoption.action),
        goal_id: id(adoption.goal_id),
      };
    }),
    request_preview: str(item.request_preview),
  };
}

const MESSAGES: Record<string, string> = {
  AI_WORKFLOW_SCHEMA_REQUIRED:
    "需要先“备份并启用 AI 协作”（数据库升级）后才能使用拆分建议；写作不受影响。",
  STORY_CONTROL_UNAVAILABLE: "拆分建议暂不可用；写作不受影响。",
  PLAN_PROPOSAL_STALE:
    "准备建议后规划已被修改，为避免覆盖你的改动，本次没有采用。请重新准备建议。",
  PLAN_PROPOSAL_CONFLICT:
    "建议状态已变化（可能已在其他窗口发送或失败），请刷新后再操作。",
  PLAN_PROPOSAL_INVALID: "所选建议卡无效，或本书的建议记录已达上限。",
  PLAN_PROPOSAL_NOT_FOUND: "该目标或建议已不存在，请刷新。",
  PLAN_PROPOSAL_CONSENT_REQUIRED:
    "这是云端模型：请先勾选同意发送冻结的规划摘要。",
  STORY_CONTROL_INVALID:
    "采用失败：建议引用的章节或分卷已不存在，或目标已达上限。规划未改变。",
  STORY_CONTROL_CYCLE: "采用会让目标关系形成循环，未采用。",
  AI_BUDGET_REFUSED:
    "按你设定的严格预算，本次没有发送，也没有记录用量。可调整预算后重新预估。",
  MODEL_PROFILE_NOT_FOUND: "该模型配置已不存在，请重新选择模型。",
  PROJECT_NOT_FOUND: "这本小说已不存在或已删除。",
};

export function planProposalError(error: unknown): PlanProposalError {
  if (error instanceof PlanProposalError) return error;
  if (error instanceof ApiError) {
    if (error.status === 401) securitySession.clear();
    return new PlanProposalError(
      MESSAGES[error.code] ??
        (error.status >= 500
          ? "模型服务暂不可用，本次建议已记为失败；规划未改变。"
          : "拆分建议请求失败，请稍后重试；规划未改变。"),
      error.code,
    );
  }
  return new PlanProposalError(
    "连接中断，拆分建议未完成；规划未改变，可刷新查看结果。",
  );
}

async function request<T>(action: () => Promise<{ data: T }>): Promise<T> {
  try {
    return (await action()).data;
  } catch (error) {
    throw planProposalError(error);
  }
}
async function csrf(): Promise<{ headers: Record<string, string> }> {
  const session = await securitySession.getValidSession();
  return { headers: { "X-CSRF-Token": session.csrfToken } };
}
function base(projectId: string): string {
  return `projects/${id(projectId)}/plan-proposals`;
}

export const planProposalClient = {
  models: () =>
    request(() =>
      getJson("ai/models", (value) => {
        const item = obj(value);
        return list(item.items, (raw) => {
          const profile = obj(raw);
          return {
            id: id(profile.id),
            name: str(profile.name),
            kind: kind(profile.kind),
          };
        });
      }),
    ),
  list: (projectId: string) =>
    request(() =>
      getJson(base(projectId), (value) =>
        list(obj(value).items, (raw) => parseProposal(raw, projectId)),
      ),
    ),
  prepare: (
    projectId: string,
    goalId: string,
    profileId: string,
    authorRequest: string,
  ) =>
    request(async () =>
      postJson(
        base(projectId),
        {
          goal_id: id(goalId),
          profile_id: profileId,
          author_request: authorRequest,
        },
        (value) => parseProposal(value, projectId),
        await csrf(),
      ),
    ),
  estimate: (projectId: string, proposalId: string): Promise<SendEstimate> =>
    request(() =>
      getJson(`${base(projectId)}/${id(proposalId)}/estimate`, parseEstimate),
    ),
  send: (projectId: string, proposal: PlanProposal, cloudConsent: boolean) =>
    request(async () =>
      postJson(
        `${base(projectId)}/${id(proposal.id)}/send`,
        { expected_version: proposal.version, cloud_consent: cloudConsent },
        (value) => parseProposal(value, projectId),
        await csrf(),
      ),
    ),
  adopt: (projectId: string, proposalId: string, indexes: readonly number[]) =>
    request(async () =>
      postJson(
        `${base(projectId)}/${id(proposalId)}/adopt`,
        { card_indexes: indexes },
        (value) => parseProposal(value, projectId),
        await csrf(),
      ),
    ),
};
export type PlanProposalClient = typeof planProposalClient;
