import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { isCanonicalPrefixedUlid } from "../../../api/identifiers";
import { useProjectDetails } from "../../projects/hooks/useProjectDetails";
import type { ProjectDetailApiClient } from "../../projects/api/client";
import { projectStructurePath } from "../../projects/routing";
import {
  novelStructureApiClient,
  NovelStructureApiError,
  type NovelStructureApiClient,
} from "../api/client";
import type {
  ChapterResponse,
  VersionedChapterContent,
  VolumeResponse,
} from "../api/contracts";
import { useChapterWriting, type SaveStatus } from "../hooks/useChapterWriting";
import { AIWorkflowAssistant } from "../components/AIWorkflowAssistant";
import type { SelectionSnapshot } from "../hooks/useAIWriting";

const SAVE_LABELS: Record<SaveStatus, string> = {
  saved: "已保存",
  dirty: "未保存",
  saving: "正在保存…",
  error: "保存失败",
  conflict: "版本冲突",
};

function WritingEditor({
  initial,
  chapter,
  volume,
  client,
}: {
  readonly initial: VersionedChapterContent;
  readonly chapter: ChapterResponse;
  readonly volume: VolumeResponse;
  readonly client: NovelStructureApiClient;
}) {
  const writing = useChapterWriting(initial, client);
  const { state, edit, save, reloadServer } = writing;
  const [selection, setSelection] = useState<SelectionSnapshot | null>(null);
  return (
    <section
      className="chapter-writing-workspace"
      aria-labelledby="chapter-writing-heading"
      data-feature-id="chapter.writing.autosave"
    >
      <Link to={projectStructurePath(chapter.project_id)}>返回小说结构</Link>
      <h2 id="chapter-writing-heading">
        第{chapter.position}章 / {chapter.title}
      </h2>
      <p>所属卷：{volume.title}</p>
      <div className="chapter-writing-toolbar">
        <p role="status" aria-label="保存状态">
          {SAVE_LABELS[state.status]}
        </p>
        <button
          type="button"
          disabled={
            state.status === "saved" ||
            state.status === "saving" ||
            state.status === "conflict" ||
            state.reloading
          }
          onClick={() => void save()}
        >
          立即保存
        </button>
      </div>
      {state.status === "conflict" ? (
        <div role="alert">
          <p>服务器上的章节已发生变化。当前内容尚未覆盖服务器版本。</p>
          <p>重新加载会丢弃当前未保存的本地正文。</p>
          <button
            type="button"
            disabled={state.reloading}
            onClick={() => void reloadServer()}
          >
            丢弃本地正文并重新加载服务器版本
          </button>
        </div>
      ) : null}
      {state.status === "error" ? (
        <p role="alert">
          保存失败，当前正文已保留。请点击“立即保存”重试，或继续编辑后再次保存。
        </p>
      ) : null}
      {state.reloadFailed ? (
        <div role="alert">
          <p>
            服务器正文尚未确认，本地正文仍保留。重新读取前暂停编辑，避免覆盖已采纳内容。
          </p>
          <button
            type="button"
            disabled={state.reloading}
            onClick={() => void reloadServer()}
          >
            重新读取已保存正文
          </button>
        </div>
      ) : null}
      {state.reloading ? <p role="status">正在重新读取服务器正文…</p> : null}
      <label htmlFor="chapter-manuscript">章节正文</label>
      <textarea
        id="chapter-manuscript"
        value={state.content}
        readOnly={state.reloading || state.reloadFailed}
        spellCheck={false}
        onChange={(event) => edit(event.target.value)}
        onSelect={(event) => {
          const {
            selectionStart: start,
            selectionEnd: end,
            value,
          } = event.currentTarget;
          setSelection({ start, end, text: value.slice(start, end) });
        }}
        onKeyDown={(event) => {
          if (event.ctrlKey && event.key.toLowerCase() === "s") {
            event.preventDefault();
            void save();
          }
          if (
            event.key === "Tab" &&
            !event.shiftKey &&
            !event.ctrlKey &&
            !event.altKey &&
            !state.reloading
          ) {
            event.preventDefault();
            event.currentTarget.setRangeText(
              "\t",
              event.currentTarget.selectionStart,
              event.currentTarget.selectionEnd,
              "end",
            );
            edit(event.currentTarget.value);
          }
        }}
      />
      <p aria-label="字符数">字符数：{state.content.length}</p>
      <AIWorkflowAssistant
        chapterId={chapter.chapter_id}
        writing={writing}
        selection={selection}
      />
    </section>
  );
}

type LoadState =
  | { readonly status: "loading" }
  | { readonly status: "not_found" }
  | { readonly status: "error" }
  | {
      readonly status: "ready";
      readonly chapter: ChapterResponse;
      readonly volume: VolumeResponse;
      readonly content: VersionedChapterContent;
    };

function ChapterLoader({
  projectId,
  chapterId,
  client,
}: {
  readonly projectId: string;
  readonly chapterId: string;
  readonly client: NovelStructureApiClient;
}) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setState({ status: "loading" });
      try {
        const chapter = await client.getChapter(
          chapterId,
          projectId,
          undefined,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (
          chapter.resource.project_id !== projectId ||
          chapter.resource.chapter_id !== chapterId
        ) {
          setState({ status: "not_found" });
          return;
        }
        const volume = await client.getVolume(
          chapter.resource.volume_id,
          projectId,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        const content = await client.getChapterContent(
          chapterId,
          projectId,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (
          content.resource.project_id !== projectId ||
          content.resource.chapter_id !== chapterId ||
          content.resource.volume_id !== chapter.resource.volume_id
        ) {
          setState({ status: "not_found" });
          return;
        }
        setState({
          status: "ready",
          chapter: chapter.resource,
          volume: volume.resource,
          content,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setState({
          status:
            error instanceof NovelStructureApiError &&
            ["not_found", "project_not_found", "contract"].includes(error.kind)
              ? "not_found"
              : "error",
        });
      }
    };
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load();
    });
    return () => controller.abort();
  }, [attempt, chapterId, client, projectId]);
  if (state.status === "loading")
    return <p role="status">正在加载章节结构与正文…</p>;
  if (state.status === "not_found")
    return <p role="alert">章节不存在或不属于当前项目。</p>;
  if (state.status === "error")
    return (
      <div role="alert">
        <p>章节加载失败，未显示编辑器。</p>
        <button type="button" onClick={() => setAttempt((value) => value + 1)}>
          重新加载章节
        </button>
      </div>
    );
  return (
    <WritingEditor
      initial={state.content}
      chapter={state.chapter}
      volume={state.volume}
      client={client}
    />
  );
}

function ProjectWritingPage({
  projectId,
  chapterId,
  client,
  projectClient,
}: {
  readonly projectId: string;
  readonly chapterId: string;
  readonly client: NovelStructureApiClient;
  readonly projectClient?: ProjectDetailApiClient;
}) {
  const project = useProjectDetails(projectId, projectClient);
  if (project.state.status === "loading")
    return <p role="status">正在加载项目…</p>;
  if (
    project.state.status === "invalid" ||
    project.state.status === "not_found"
  )
    return <p role="alert">项目不存在或编号无效。</p>;
  if (project.state.status === "error")
    return (
      <div role="alert">
        <p>项目加载失败。</p>
        <button type="button" onClick={() => void project.reload()}>
          重新加载项目
        </button>
      </div>
    );
  return (
    <ChapterLoader
      projectId={projectId}
      chapterId={chapterId}
      client={client}
    />
  );
}

export function ChapterWritingPage({
  client = novelStructureApiClient,
  projectClient,
}: {
  readonly client?: NovelStructureApiClient;
  readonly projectClient?: ProjectDetailApiClient;
}) {
  const { projectId, chapterId } = useParams();
  if (
    !isCanonicalPrefixedUlid(projectId, "prj") ||
    !isCanonicalPrefixedUlid(chapterId, "chp")
  )
    return <p role="alert">项目或章节编号无效。</p>;
  return (
    <ProjectWritingPage
      key={`${projectId}:${chapterId}`}
      projectId={projectId}
      chapterId={chapterId}
      client={client}
      projectClient={projectClient}
    />
  );
}
