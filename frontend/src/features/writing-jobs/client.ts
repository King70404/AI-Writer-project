import { getJson, postJson } from "../../api/client";
import { securitySession } from "../../api/security-session";

export type JobStatus = "planned" | "paused" | "cancelled" | "completed";
export type StepStatus = "pending" | "completed";
export interface WritingStep {
  readonly chapter_id: string;
  readonly status: StepStatus;
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
  act: (job, action, expectedVersion) =>
    write(`writing-jobs/${encodeURIComponent(job)}/${action}`, {
      expected_version: expectedVersion,
    }),
};
