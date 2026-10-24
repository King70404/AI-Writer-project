import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

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
import { ChapterNavigator } from "../components/ChapterNavigator";
import {
  forgetRecentChapter,
  recordRecentChapter,
} from "../../workbench/recentWriting";
import type { SelectionSnapshot } from "../hooks/useAIWriting";
import { EditorialStatusControl } from "../../workbench/components/EditorialStatusControl";
import { LocalDraftRecovery } from "../../local-drafts/LocalDraftRecovery";
import { useLocalDraft } from "../../local-drafts/useLocalDraft";
import { ConflictResolution } from "../components/ConflictResolution";

const SAVE_LABELS: Record<SaveStatus, string> = {
  saved: "已保存",
  dirty: "未保存",
  saving: "正在保存…",
  error: "保存失败",
  conflict: "版本冲突",
};

/** ≥1280px 时默认展开三栏；更窄时正文优先，目录和助手按需打开。 */
function wideDesk(): boolean {
  return typeof window.matchMedia === "function"
    ? window.matchMedia("(min-width: 80rem)").matches
    : true;
}

function WritingEditor({
  initial,
  chapter,
  volume,
  projectTitle,
  client,
  loadStorageInstance,
}: {
  readonly initial: VersionedChapterContent;
  readonly chapter: ChapterResponse;
  readonly volume: VolumeResponse;
  readonly projectTitle: string;
  readonly client: NovelStructureApiClient;
  readonly loadStorageInstance?: () => Promise<string>;
}) {
  const writing = useChapterWriting(initial, client);
  const { state, edit, save, reloadServer, flush } = writing;
  const drafts = useLocalDraft(
    {
      projectId: chapter.project_id,
      chapterId: chapter.chapter_id,
      chapterTitle: chapter.title,
      content: state.content,
      savedContent: state.snapshot.resource.content,
      savedRevisionId: state.snapshot.resource.current_revision_id,
      savedVersion: state.snapshot.version,
    },
    loadStorageInstance,
  );
  const navigate = useNavigate();
  const [selection, setSelection] = useState<SelectionSnapshot | null>(null);
  const [taskStatus, setTaskStatus] = useState("没有进行中的 AI 任务");
  const [navigatorOpen, setNavigatorOpen] = useState(wideDesk);
  const [assistantOpen, setAssistantOpen] = useState(wideDesk);
  const [focusMode, setFocusMode] = useState(false);
  const [leaveError, setLeaveError] = useState("");
  const [leaving, setLeaving] = useState(false);
  const focusToggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    recordRecentChapter(chapter.project_id, chapter.chapter_id);
  }, [chapter.chapter_id, chapter.project_id]);
  useEffect(() => {
    if (!focusMode) return;
    const exit = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.isComposing) return;
      setFocusMode(false);
      focusToggle.current?.focus();
    };
    document.addEventListener("keydown", exit);
    return () => document.removeEventListener("keydown", exit);
  }, [focusMode]);
  const guardedNavigate = (
    event: MouseEvent<HTMLAnchorElement>,
    to: string,
  ) => {
    if (state.status === "saved" && !state.reloading) return;
    event.preventDefault();
    if (leaving) return;
    setLeaving(true);
    setLeaveError("");
    void flush()
      .then((saved) => {
        if (saved) void navigate(to);
        else
          setLeaveError(
            "当前章节尚未保存，已留在本章，正文仍保留。请先处理保存状态再切换。",
          );
      })
      .finally(() => setLeaving(false));
  };
  const showNavigator = navigatorOpen && !focusMode;
  const showAssistant = assistantOpen && !focusMode;
  return (
    <section
      className={`chapter-writing-workspace writing-desk${focusMode ? " writing-desk--focus" : ""}${showNavigator ? "" : " writing-desk--no-nav"}${showAssistant ? "" : " writing-desk--no-assistant"}`}
      aria-labelledby="chapter-writing-heading"
      data-feature-id="chapter.writing.autosave"
    >
      <section className="writing-statusbar" aria-label="写作状态">
        <div className="writing-statusbar__title">
          <p className="writing-statusbar__crumbs">
            <span>{projectTitle}</span> · <span>所属卷：{volume.title}</span>
          </p>
          <h2 id="chapter-writing-heading">
            第{chapter.position}章 / {chapter.title}
          </h2>
        </div>
        <div className="chapter-writing-toolbar writing-statusbar__state">
          <p
            role="status"
            aria-label="保存状态"
            data-save-status={state.status}
          >
            {SAVE_LABELS[state.status]}
          </p>
          <p aria-label="字符数">字符数：{state.content.length}</p>
          <p aria-label="AI 任务状态">{taskStatus}</p>
          <EditorialStatusControl
            chapterId={chapter.chapter_id}
            savedRevisionId={state.snapshot.resource.current_revision_id}
            flush={flush}
          />
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
        <div className="writing-statusbar__actions">
          {focusMode ? null : (
            <>
              <button
                type="button"
                aria-pressed={navigatorOpen}
                aria-controls="writing-desk-navigator"
                onClick={() => setNavigatorOpen((value) => !value)}
              >
                {navigatorOpen ? "收起目录" : "显示目录"}
              </button>
              <button
                type="button"
                aria-pressed={assistantOpen}
                aria-controls="writing-desk-assistant"
                onClick={() => setAssistantOpen((value) => !value)}
              >
                {assistantOpen ? "收起助手" : "显示助手"}
              </button>
            </>
          )}
          <button
            ref={focusToggle}
            type="button"
            aria-pressed={focusMode}
            onClick={() => setFocusMode((value) => !value)}
          >
            {focusMode ? "退出专注（Esc）" : "专注写作"}
          </button>
        </div>
      </section>
      {leaveError ? <p role="alert">{leaveError}</p> : null}
      <aside
        id="writing-desk-navigator"
        className="writing-desk__navigator"
        hidden={!showNavigator}
      >
        <ChapterNavigator
          projectId={chapter.project_id}
          chapterId={chapter.chapter_id}
          projectTitle={projectTitle}
          client={client}
          onNavigate={guardedNavigate}
        />
      </aside>
      <div className="writing-desk__editor">
        {state.status === "conflict" ? (
          <ConflictResolution
            chapterTitle={chapter.title}
            localContent={state.content}
            disabled={state.reloading}
            loadServer={async () =>
              (
                await client.getChapterContent(
                  chapter.chapter_id,
                  chapter.project_id,
                )
              ).resource.content
            }
            onKeepLocal={writing.keepLocal}
            onReloadServer={() => void reloadServer()}
          />
        ) : null}
        <LocalDraftRecovery
          instance={drafts.instance}
          storageError={drafts.storageError}
          recoverable={drafts.recoverable}
          foreign={drafts.foreign}
          savedContent={state.snapshot.resource.content}
          savedRevisionId={state.snapshot.resource.current_revision_id}
          canRestore={
            state.status === "saved" && !state.reloading && !state.reloadFailed
          }
          onRestore={edit}
          onDiscard={drafts.discard}
          onDismiss={drafts.dismiss}
        />
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
          className="writing-desk__manuscript"
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
      </div>
      <aside
        id="writing-desk-assistant"
        className="writing-desk__assistant"
        hidden={!showAssistant}
      >
        <AIWorkflowAssistant
          chapterId={chapter.chapter_id}
          projectId={chapter.project_id}
          writing={writing}
          selection={selection}
          onTaskStatus={setTaskStatus}
        />
      </aside>
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
  projectTitle,
  client,
}: {
  readonly projectId: string;
  readonly chapterId: string;
  readonly projectTitle: string;
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
          forgetRecentChapter(projectId, chapterId);
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
        const missing =
          error instanceof NovelStructureApiError &&
          ["not_found", "project_not_found", "contract"].includes(error.kind);
        if (missing) forgetRecentChapter(projectId, chapterId);
        setState({ status: missing ? "not_found" : "error" });
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
    return (
      <div className="chapter-missing">
        <p role="alert">章节不存在或不属于当前项目。</p>
        <Link to={projectStructurePath(projectId)}>打开小说结构</Link>
      </div>
    );
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
      projectTitle={projectTitle}
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
      projectTitle={project.state.resource.project.title}
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
