import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { ApiError } from "../../api/errors";
import { chapterWritingPath } from "../novel-structure/routing";
import {
  workspaceClient,
  type ChapterSummary,
  type WorkspaceClient,
} from "../workbench/api/workspace";
import {
  writingJobsClient,
  type JobAction,
  type WritingJob,
  type WritingJobsClient,
} from "./client";
import "./writing-jobs.css";

const STATUS: Record<WritingJob["status"], string> = {
  planned: "进行中",
  paused: "已暂停",
  cancelled: "已终止",
  completed: "已完成",
};
function message(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409 || error.status === 412)
      return "任务状态已变化，请刷新后再操作。";
    if (error.status === 503)
      return "当前数据库需要升级后才能使用写作任务，请先停止服务并备份。";
    if (error.status === 404) return "任务或章节已不存在，请刷新后重试。";
    if (error.status === 422) return "请检查任务名称和选择的章节。";
  }
  return "写作任务未能完成，请检查连接后重试。";
}

export function WritingJobsPanel({
  projectId,
  client = writingJobsClient,
  chaptersClient = workspaceClient,
}: {
  readonly projectId: string;
  readonly client?: WritingJobsClient;
  readonly chaptersClient?: WorkspaceClient;
}) {
  const [open, setOpen] = useState(false);
  const [jobs, setJobs] = useState<readonly WritingJob[]>([]);
  const [chapters, setChapters] = useState<readonly ChapterSummary[]>([]);
  const [next, setNext] = useState<number | null>(0);
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const [loadedJobs, firstPage] = await Promise.all([
        client.list(projectId),
        chaptersClient.chapters(projectId, 0, 50),
      ]);
      setJobs(loadedJobs);
      setChapters(firstPage.items);
      setNext(firstPage.next_offset);
    } catch (failure) {
      setError(message(failure));
    } finally {
      setBusy(false);
    }
  }
  function toggleOpen() {
    if (!open) void refresh();
    setOpen(!open);
  }
  async function loadMore() {
    if (next === null || busy) return;
    setBusy(true);
    setError("");
    try {
      const page = await chaptersClient.chapters(projectId, next, 50);
      setChapters((old) => [...old, ...page.items]);
      setNext(page.next_offset);
    } catch (failure) {
      setError(message(failure));
    } finally {
      setBusy(false);
    }
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    if (busy || !title.trim() || selected.length === 0) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const job = await client.create(projectId, title.trim(), selected);
      setJobs((old) => [job, ...old]);
      setSelected([]);
      setTitle("");
      setNotice("任务已创建；请选择当前章节进入写作台。");
    } catch (failure) {
      setError(message(failure));
    } finally {
      setBusy(false);
    }
  }
  async function act(job: WritingJob, action: JobAction) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await client.act(job.job_id, action, job.version);
      setJobs((old) =>
        old.map((item) => (item.job_id === updated.job_id ? updated : item)),
      );
      setNotice(
        action === "finish-step"
          ? "已结束本章任务；章节定稿状态没有改变。"
          : "任务状态已更新。",
      );
    } catch (failure) {
      setError(message(failure));
    } finally {
      setBusy(false);
    }
  }
  const chapterName = (id: string, position: number) => {
    const chapter = chapters.find((item) => item.chapter_id === id);
    return chapter
      ? `第 ${chapter.position} 章 · ${chapter.title}`
      : `任务中的第 ${position + 1} 章`;
  };
  return (
    <section className="writing-jobs" aria-label="跨章写作任务">
      <button type="button" onClick={toggleOpen} aria-expanded={open}>
        {open ? "收起写作任务" : "安排写作任务"}
      </button>
      {open ? (
        <div className="writing-jobs__body">
          <h3>跨章写作任务</h3>
          <p>
            按选择顺序安排章节；创建任务不会发送模型请求。进入写作台后，每次发送和采用仍由你确认。
          </p>
          <p>
            本清单尚未设置跨章总额度；每次生成仍使用现有模型预算和发送前确认。
          </p>
          {error ? (
            <div role="alert">
              <p>{error}</p>
              <button
                type="button"
                onClick={() => void refresh()}
                disabled={busy}
              >
                刷新任务
              </button>
            </div>
          ) : null}
          {notice ? <p role="status">{notice}</p> : null}
          <form onSubmit={(event) => void create(event)}>
            <label>
              任务名称
              <input
                value={title}
                maxLength={120}
                onChange={(event) => setTitle(event.target.value)}
                disabled={busy}
              />
            </label>
            <fieldset disabled={busy}>
              <legend>按顺序选择章节（最多 10 章）</legend>
              {chapters.map((chapter) => (
                <label
                  key={chapter.chapter_id}
                  className="writing-jobs__choice"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(chapter.chapter_id)}
                    disabled={
                      !selected.includes(chapter.chapter_id) &&
                      selected.length >= 10
                    }
                    onChange={(event) =>
                      setSelected((old) =>
                        event.target.checked
                          ? [...old, chapter.chapter_id]
                          : old.filter((id) => id !== chapter.chapter_id),
                      )
                    }
                  />
                  第 {chapter.position} 章 · {chapter.title}
                  {selected.includes(chapter.chapter_id)
                    ? `（第 ${selected.indexOf(chapter.chapter_id) + 1} 项）`
                    : ""}
                </label>
              ))}
              {!busy && chapters.length === 0 ? <p>请先创建章节。</p> : null}
            </fieldset>
            {next !== null ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void loadMore()}
              >
                加载更多章节
              </button>
            ) : null}
            <button
              type="submit"
              disabled={busy || !title.trim() || selected.length === 0}
            >
              创建任务清单
            </button>
          </form>
          <h4>已保存的任务</h4>
          {!busy && jobs.length === 0 ? <p>还没有写作任务。</p> : null}
          <ul>
            {jobs.map((job) => (
              <li key={job.job_id}>
                <h5>{job.title}</h5>
                <p>
                  {STATUS[job.status]} · 已完成{" "}
                  {
                    job.steps.filter((step) => step.status === "completed")
                      .length
                  }
                  /{job.steps.length} 章
                </p>
                <ol>
                  {job.steps.map((step, index) => (
                    <li key={step.chapter_id}>
                      {chapterName(step.chapter_id, index)} ·{" "}
                      {step.status === "completed"
                        ? "已结束"
                        : index === job.current_index &&
                            job.status === "planned"
                          ? "当前章节"
                          : "待处理"}
                    </li>
                  ))}
                </ol>
                {job.status === "planned" && job.steps[job.current_index] ? (
                  <>
                    <Link
                      to={chapterWritingPath(
                        projectId,
                        job.steps[job.current_index].chapter_id,
                      )}
                    >
                      进入当前章节写作
                    </Link>{" "}
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void act(job, "finish-step")}
                    >
                      结束本章任务
                    </button>{" "}
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void act(job, "pause")}
                    >
                      暂停任务
                    </button>{" "}
                  </>
                ) : null}
                {job.status === "paused" ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void act(job, "resume")}
                  >
                    恢复任务
                  </button>
                ) : null}{" "}
                {job.status === "planned" || job.status === "paused" ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void act(job, "cancel")}
                  >
                    终止任务
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
