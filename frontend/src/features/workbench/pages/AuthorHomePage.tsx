import { useEffect, useState } from "react";
import { Link } from "react-router";

import { SystemStatus } from "../../../components/SystemStatus";
import {
  novelStructureApiClient,
  NovelStructureApiError,
  type NovelStructureApiClient,
} from "../../novel-structure/api/client";
import { chapterWritingPath } from "../../novel-structure/routing";
import {
  projectApiClient,
  type ProjectDetailApiClient,
} from "../../projects/api/client";
import { ProjectApiError } from "../../projects/api/errors";
import { formatProjectTimestamp } from "../../projects/formatting";
import { projectStructurePath } from "../../projects/routing";
import {
  forgetRecentChapter,
  lastRecentChapter,
  type RecentChapter,
} from "../recentWriting";

type ContinueState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | { readonly status: "project_missing" }
  | { readonly status: "chapter_missing" }
  | {
      readonly status: "ready";
      readonly projectTitle: string;
      readonly chapterTitle: string;
      readonly chapterPosition: number;
    };

function ContinueWritingCard({
  recent,
  projectClient,
  structureClient,
  onForget,
}: {
  readonly recent: RecentChapter;
  readonly projectClient: ProjectDetailApiClient;
  readonly structureClient: NovelStructureApiClient;
  readonly onForget: () => void;
}) {
  const [state, setState] = useState<ContinueState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setState({ status: "loading" });
      let projectTitle: string;
      try {
        const project = await projectClient.getProject(recent.projectId, {
          signal: controller.signal,
        });
        projectTitle = project.project.title;
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ProjectApiError && error.kind === "not_found") {
          forgetRecentChapter(recent.projectId, recent.chapterId);
          setState({ status: "project_missing" });
        } else setState({ status: "error" });
        return;
      }
      try {
        const chapter = await structureClient.getChapter(
          recent.chapterId,
          recent.projectId,
          undefined,
          controller.signal,
        );
        if (controller.signal.aborted) return;
        if (chapter.resource.project_id !== recent.projectId) {
          forgetRecentChapter(recent.projectId, recent.chapterId);
          setState({ status: "chapter_missing" });
          return;
        }
        setState({
          status: "ready",
          projectTitle,
          chapterTitle: chapter.resource.title,
          chapterPosition: chapter.resource.position,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        if (
          error instanceof NovelStructureApiError &&
          ["not_found", "project_not_found", "contract"].includes(error.kind)
        ) {
          forgetRecentChapter(recent.projectId, recent.chapterId);
          setState({ status: "chapter_missing" });
        } else setState({ status: "error" });
      }
    };
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load();
    });
    return () => controller.abort();
  }, [attempt, projectClient, recent, structureClient]);

  const writePath = chapterWritingPath(recent.projectId, recent.chapterId);
  if (state.status === "loading")
    return <p role="status">正在读取上次写作的章节…</p>;
  if (state.status === "project_missing")
    return (
      <div role="alert">
        <p>上次写作的小说已不存在。可以从书架选择其他小说。</p>
        <Link to="/projects" onClick={onForget}>
          打开书架
        </Link>
      </div>
    );
  if (state.status === "chapter_missing")
    return (
      <div role="alert">
        <p>上次写作的章节已不存在，已回到该小说的卷章结构。</p>
        <Link to={projectStructurePath(recent.projectId)}>打开小说结构</Link>
      </div>
    );
  if (state.status === "error")
    return (
      <div role="alert">
        <p>暂时无法读取上次章节的信息；正文没有受到影响。</p>
        <button type="button" onClick={() => setAttempt((value) => value + 1)}>
          重新读取
        </button>
        <Link to={writePath}>直接打开上次章节</Link>
      </div>
    );
  return (
    <div className="continue-card">
      <p className="continue-card__book">{state.projectTitle}</p>
      <p className="continue-card__chapter">
        第{state.chapterPosition}章 · {state.chapterTitle}
      </p>
      <p className="continue-card__meta">
        上次在本机打开：
        <time dateTime={recent.openedAt}>
          {formatProjectTimestamp(recent.openedAt)}
        </time>
      </p>
      <Link className="button-link button-link--primary" to={writePath}>
        继续写作
      </Link>
    </div>
  );
}

export function AuthorHomePage({
  projectClient = projectApiClient,
  structureClient = novelStructureApiClient,
}: {
  readonly projectClient?: ProjectDetailApiClient;
  readonly structureClient?: NovelStructureApiClient;
}) {
  const [recent, setRecent] = useState<RecentChapter | null>(() =>
    lastRecentChapter(),
  );
  return (
    <section
      className="author-home"
      data-feature-id="FND-001"
      aria-labelledby="author-home-title"
    >
      <p className="section-kicker">本地长篇创作</p>
      <h2 id="author-home-title">写作首页</h2>
      <section
        className="author-home__continue"
        aria-labelledby="continue-title"
      >
        <h3 id="continue-title">继续上次创作</h3>
        {recent ? (
          <ContinueWritingCard
            key={`${recent.projectId}:${recent.chapterId}`}
            recent={recent}
            projectClient={projectClient}
            structureClient={structureClient}
            onForget={() => setRecent(null)}
          />
        ) : (
          <p>
            本机还没有最近写作的章节。打开书架选择小说，或新建一本开始写作。
          </p>
        )}
        <div className="author-home__actions">
          <Link
            className={
              recent ? "button-link" : "button-link button-link--primary"
            }
            to="/projects"
          >
            打开书架
          </Link>
          <Link className="button-link" to="/projects">
            新建小说
          </Link>
        </div>
        <p className="author-home__note">
          设定、人物和模型配置都不会阻止进入空白章节；没有模型时手动写作、自动保存与导出仍可使用。
        </p>
      </section>
      <section className="author-home__system" aria-label="运行状态">
        <SystemStatus />
      </section>
    </section>
  );
}
