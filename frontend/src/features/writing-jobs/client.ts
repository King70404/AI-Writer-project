import { getJson, postJson } from "../../api/client";
import { securitySession } from "../../api/security-session";

export type JobStatus = "planned" | "paused" | "cancelled" | "completed";
export type StepStatus = "pending" | "completed";
export interface WritingStep {
  readonly chapter_id: string;
  readonly status: StepStatus;
}
export type SceneStatus = "pending" | "done" | "skipped";
export interface PlannedSceneProgress {
  readonly scene_id: string;
  readonly title: string;
  readonly status: SceneStatus;
}
/** Author-recorded progress; marks always refer to the plan revision they were made on. */
export interface StepSceneProgress {
  readonly step_index: number;
  readonly chapter_id: string;
  readonly plan_revision_id: string | null;
  readonly plan_version: number | null;
  readonly current_plan_revision_id: string | null;
  readonly current_plan_version: number | null;
  readonly needs_recheck: boolean;
  readonly has_adopted: boolean;
  readonly scenes: readonly PlannedSceneProgress[];
  readonly target_scene_id: string | null;
  readonly next_scene_id: string | null;
  readonly done_count: number;
  readonly skipped_count: number;
  readonly total: number;
}
export function sceneSummary(progress: StepSceneProgress): string {
  return `场景 ${progress.done_count + progress.skipped_count}/${progress.total}`;
}
export type SceneAction = "target" | "done" | "skipped" | "pending" | "recheck";
export interface SceneMark {
  readonly step_index: number;
  readonly plan_revision_id: string;
  readonly action: SceneAction;
  readonly scene_id?: string;
}
/** 本任务各步骤绑定的章节候选稿（只有计数，不含段落正文）。 */
export interface JobDraftSummary {
  readonly draft_id: string;
  readonly chapter_id: string;
  readonly step_index: number;
  readonly status: "ready" | "running" | "failed" | "exhausted";
  readonly segments: number;
  readonly pending: number;
  readonly adopted: number;
  readonly discarded: number;
  readonly edited: number;
  readonly generated_characters: number;
  readonly adopted_characters: number;
}
export interface WritingJob {
  readonly job_id: string;
  readonly project_id: string;
  readonly title: string;
  readonly status: JobStatus;
  readonly version: number;
  readonly current_index: number;
  readonly steps: readonly WritingStep[];
  readonly max_requests: number;
  readonly max_output_characters: number;
  readonly claimed_requests: number;
  readonly used_characters: number;
  readonly active_run_id: string | null;
  /** 当前步骤绑定的是章节候选稿时为其 id（同时也是 active_run_id）。 */
  readonly active_draft_id?: string | null;
  /** 本任务产出的章节候选稿；旧版本服务端未返回时为空。 */
  readonly drafts?: readonly JobDraftSummary[];
  readonly scene_progress: readonly StepSceneProgress[];
}
export type JobAction = "pause" | "resume" | "cancel" | "finish-step";
export interface WritingJobsClient {
  readonly list: (project: string) => Promise<readonly WritingJob[]>;
  readonly get: (job: string) => Promise<WritingJob>;
  readonly bind: (
    job: string,
    runId: string,
    expectedVersion: number,
  ) => Promise<WritingJob>;
  readonly create: (
    project: string,
    title: string,
    chapterIds: readonly string[],
    maxRequests: number,
    maxOutputCharacters: number,
  ) => Promise<WritingJob>;
  readonly act: (
    job: string,
    action: JobAction,
    expectedVersion: number,
  ) => Promise<WritingJob>;
  readonly markScene: (
    job: string,
    mark: SceneMark,
    expectedVersion: number,
  ) => Promise<WritingJob>;
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("写作任务数据无法读取。");
  return value as Record<string, unknown>;
}
function str(value: unknown): string {
  if (typeof value !== "string") throw new Error("写作任务数据无法读取。");
  return value;
}
function count(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw new Error("写作任务数据无法读取。");
  return value;
}
function optionalStr(value: unknown): string | null {
  return value === null ? null : str(value);
}
function optionalCount(value: unknown): number | null {
  return value === null ? null : count(value);
}
function flag(value: unknown): boolean {
  if (typeof value !== "boolean") throw new Error("场景进度无法读取。");
  return value;
}
function parseProgress(value: unknown, index: number): StepSceneProgress {
  const progress = object(value);
  if (!Array.isArray(progress.scenes)) throw new Error("场景进度无法读取。");
  const scenes = progress.scenes.map((item): PlannedSceneProgress => {
    const scene = object(item);
    if (
      scene.status !== "pending" &&
      scene.status !== "done" &&
      scene.status !== "skipped"
    )
      throw new Error("场景进度无法读取。");
    return {
      scene_id: str(scene.scene_id),
      title: str(scene.title),
      status: scene.status,
    };
  });
  const stepIndex = count(progress.step_index);
  if (stepIndex !== index) throw new Error("场景进度无法读取。");
  return {
    step_index: stepIndex,
    chapter_id: str(progress.chapter_id),
    plan_revision_id: optionalStr(progress.plan_revision_id),
    plan_version: optionalCount(progress.plan_version),
    current_plan_revision_id: optionalStr(progress.current_plan_revision_id),
    current_plan_version: optionalCount(progress.current_plan_version),
    needs_recheck: flag(progress.needs_recheck),
    has_adopted: flag(progress.has_adopted),
    scenes,
    target_scene_id: optionalStr(progress.target_scene_id),
    next_scene_id: optionalStr(progress.next_scene_id),
    done_count: count(progress.done_count),
    skipped_count: count(progress.skipped_count),
    total: count(progress.total),
  };
}
function parseDraftSummary(value: unknown): JobDraftSummary {
  const draft = object(value);
  if (
    draft.status !== "ready" &&
    draft.status !== "running" &&
    draft.status !== "failed" &&
    draft.status !== "exhausted"
  )
    throw new Error("任务候选稿无法读取。");
  return {
    draft_id: str(draft.draft_id),
    chapter_id: str(draft.chapter_id),
    step_index: count(draft.step_index),
    status: draft.status,
    segments: count(draft.segments),
    pending: count(draft.pending),
    adopted: count(draft.adopted),
    discarded: count(draft.discarded),
    edited: count(draft.edited),
    generated_characters: count(draft.generated_characters),
    adopted_characters: count(draft.adopted_characters),
  };
}
function parse(value: unknown): WritingJob {
  const job = object(value);
  if (
    job.status !== "planned" &&
    job.status !== "paused" &&
    job.status !== "cancelled" &&
    job.status !== "completed"
  )
    throw new Error("写作任务状态无法读取。");
  if (!Array.isArray(job.steps)) throw new Error("写作任务步骤无法读取。");
  const steps = job.steps.map((value): WritingStep => {
    const step = object(value);
    if (step.status !== "pending" && step.status !== "completed")
      throw new Error("写作任务步骤无法读取。");
    return { chapter_id: str(step.chapter_id), status: step.status };
  });
  const currentIndex = count(job.current_index);
  if (steps.length === 0 || currentIndex > steps.length)
    throw new Error("写作任务步骤无法读取。");
  if (
    !Array.isArray(job.scene_progress) ||
    job.scene_progress.length !== steps.length
  )
    throw new Error("场景进度无法读取。");
  const sceneProgress = job.scene_progress.map(parseProgress);
  return {
    job_id: str(job.job_id),
    project_id: str(job.project_id),
    title: str(job.title),
    status: job.status,
    version: count(job.version),
    current_index: currentIndex,
    steps,
    max_requests: count(job.max_requests),
    max_output_characters: count(job.max_output_characters),
    claimed_requests: count(job.claimed_requests),
    used_characters: count(job.used_characters),
    active_run_id: job.active_run_id === null ? null : str(job.active_run_id),
    active_draft_id:
      job.active_draft_id === null || job.active_draft_id === undefined
        ? null
        : str(job.active_draft_id),
    drafts:
      job.drafts === undefined
        ? []
        : Array.isArray(job.drafts)
          ? job.drafts.map(parseDraftSummary)
          : (() => {
              throw new Error("任务候选稿无法读取。");
            })(),
    scene_progress: sceneProgress,
  };
}
async function write(path: string, body: unknown): Promise<WritingJob> {
  const session = await securitySession.getValidSession();
  return (
    await postJson(path, body, parse, {
      headers: { "X-CSRF-Token": session.csrfToken },
    })
  ).data;
}
export const writingJobsClient: WritingJobsClient = {
  list: async (project) =>
    (
      await getJson(
        `projects/${encodeURIComponent(project)}/writing-jobs`,
        (value) => {
          if (!Array.isArray(value)) throw new Error("写作任务列表无法读取。");
          return value.map(parse);
        },
      )
    ).data,
  get: async (job) =>
    (await getJson(`writing-jobs/${encodeURIComponent(job)}`, parse)).data,
  bind: (job, runId, expectedVersion) =>
    write(`writing-jobs/${encodeURIComponent(job)}/bind-run`, {
      run_id: runId,
      expected_version: expectedVersion,
    }),
  create: (project, title, chapterIds, maxRequests, maxOutputCharacters) =>
    write(`projects/${encodeURIComponent(project)}/writing-jobs`, {
      title,
      chapter_ids: chapterIds,
      max_requests: maxRequests,
      max_output_characters: maxOutputCharacters,
    }),
  markScene: (job, mark, expectedVersion) =>
    write(`writing-jobs/${encodeURIComponent(job)}/scene-progress`, {
      ...mark,
      expected_version: expectedVersion,
    }),
  act: (job, action, expectedVersion) =>
    write(`writing-jobs/${encodeURIComponent(job)}/${action}`, {
      expected_version: expectedVersion,
    }),
};
