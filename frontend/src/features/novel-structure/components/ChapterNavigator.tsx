import { useEffect, useState, type MouseEvent } from "react";
import { Link } from "react-router";

import {
  projectCharactersPath,
  projectStoryBiblePath,
  projectStructurePath,
} from "../../projects/routing";
import type { NovelStructureApiClient } from "../api/client";
import type { ChapterResponse, VolumeResponse } from "../api/contracts";
import { chapterWritingPath } from "../routing";

interface VolumeEntry {
  readonly volume: VolumeResponse;
  readonly chapters: readonly ChapterResponse[];
}

type TreeState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | { readonly status: "ready"; readonly volumes: readonly VolumeEntry[] };

/** 写作页左栏：只读卷章目录，复用已有卷/章列表接口，不读取正文。 */
export function ChapterNavigator({
  projectId,
  chapterId,
  projectTitle,
  client,
  onNavigate,
}: {
  readonly projectId: string;
  readonly chapterId: string;
  readonly projectTitle: string;
  readonly client: NovelStructureApiClient;
  /** 离开本章前的保存保护：未保存时阻止默认导航，保存成功后再跳转。 */
  readonly onNavigate: (
    event: MouseEvent<HTMLAnchorElement>,
    to: string,
  ) => void;
}) {
  const [state, setState] = useState<TreeState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setState({ status: "loading" });
      try {
        const volumes = [
          ...(await client.listVolumes(projectId, controller.signal)),
        ].sort((left, right) => left.position - right.position);
        const entries = await Promise.all(
          volumes.map(async (volume) => ({
            volume,
            chapters: [
              ...(await client.listChapters(
                projectId,
                volume.volume_id,
                controller.signal,
              )),
            ].sort((left, right) => left.position - right.position),
          })),
        );
        if (!controller.signal.aborted)
          setState({ status: "ready", volumes: entries });
      } catch {
        if (!controller.signal.aborted) setState({ status: "error" });
      }
    };
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load();
    });
    return () => controller.abort();
  }, [attempt, client, projectId]);

  const link = (to: string, label: string, current = false) => (
    <Link
      to={to}
      aria-current={current ? "page" : undefined}
      onClick={(event) => onNavigate(event, to)}
    >
      {label}
    </Link>
  );
  const keyword = query.trim();
  return (
    <nav className="chapter-navigator" aria-label="卷章导航">
      <p className="chapter-navigator__book">{projectTitle}</p>
      <ul className="chapter-navigator__links">
        <li>{link("/projects", "返回书架")}</li>
        <li>{link(projectStructurePath(projectId), "返回小说结构")}</li>
        <li>{link(projectStoryBiblePath(projectId), "小说设定")}</li>
        <li>{link(projectCharactersPath(projectId), "人物")}</li>
      </ul>
      <label htmlFor="chapter-navigator-search">搜索章节</label>
      <input
        id="chapter-navigator-search"
        type="search"
        value={query}
        maxLength={100}
        onChange={(event) => setQuery(event.target.value)}
      />
      {state.status === "loading" ? (
        <p role="status">正在读取卷章目录…</p>
      ) : null}
      {state.status === "error" ? (
        <div role="alert">
          <p>卷章目录读取失败；当前章节仍可继续写作。</p>
          <button
            type="button"
            onClick={() => setAttempt((value) => value + 1)}
          >
            重新读取目录
          </button>
        </div>
      ) : null}
      {state.status === "ready" ? (
        <ol className="chapter-navigator__volumes">
          {state.volumes.map(({ volume, chapters }) => {
            const visible = keyword
              ? chapters.filter((chapter) => chapter.title.includes(keyword))
              : chapters;
            if (keyword && !visible.length) return null;
            return (
              <li key={volume.volume_id}>
                <p className="chapter-navigator__volume">
                  第{volume.position}卷 · {volume.title}
                </p>
                {visible.length ? (
                  <ol className="chapter-navigator__chapters">
                    {visible.map((chapter) => (
                      <li key={chapter.chapter_id}>
                        {link(
                          chapterWritingPath(projectId, chapter.chapter_id),
                          `第${chapter.position}章 ${chapter.title}`,
                          chapter.chapter_id === chapterId,
                        )}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="chapter-navigator__empty">本卷还没有章节。</p>
                )}
              </li>
            );
          })}
          {keyword &&
          !state.volumes.some(({ chapters }) =>
            chapters.some((chapter) => chapter.title.includes(keyword)),
          ) ? (
            <li className="chapter-navigator__empty">没有匹配的章节。</li>
          ) : null}
          {!state.volumes.length ? (
            <li className="chapter-navigator__empty">还没有卷。</li>
          ) : null}
        </ol>
      ) : null}
    </nav>
  );
}
