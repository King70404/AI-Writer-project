import { useEffect, useState } from "react";
import { Link } from "react-router";

import { chapterWritingPath } from "../../novel-structure/routing";
import { formatProjectTimestamp } from "../../projects/formatting";
import { projectStructurePath } from "../../projects/routing";
import {
  ACTION_LABELS,
  EDITORIAL_LABELS,
  workbenchError,
  workspaceClient,
  type ActionItem,
  type ChapterSummary,
  type WorkspaceClient,
  type WorkspaceSummary,
} from "../api/workspace";

const CHAPTER_PAGE = 20;

function formatCount(value: number): string {
  return value.toLocaleString("zh-CN");
}

type SummaryState =
  | { readonly status: "loading" }
  | { readonly status: "error"; readonly message: string }
  | { readonly status: "ready"; readonly summary: WorkspaceSummary };

interface ListState<T> {
  readonly items: readonly T[];
  readonly total: number;
  readonly nextOffset: number | null;
  readonly loading: boolean;
  readonly error: string;
}

function emptyList<T>(): ListState<T> {
  return { items: [], total: 0, nextOffset: 0, loading: false, error: "" };
}

function ActionList({
  projectId,
  items,
}: {
  readonly projectId: string;
  readonly items: readonly ActionItem[];
}) {
  return (
    <ul className="workspace-summary__actions">
      {items.map((item) => (
        <li key={`${item.kind}:${item.chapter_id}`}>
          <span className="workspace-summary__action-label">
            {ACTION_LABELS[item.kind]}
            {item.count > 1 ? ` ×${item.count}` : ""}
          </span>{" "}
          <Link to={chapterWritingPath(projectId, item.chapter_id)}>
            第{item.chapter_position}章 · {item.chapter_title}
          </Link>
        </li>
      ))}
    </ul>
  );
}

/**
 * 小说工作台汇总：总字数、卷/章字数、作者定稿状态与统一待处理事项。
 * 只读取服务端派生的数据；读取失败只影响本区域，“继续写作”保持可用。
 */
export function WorkspaceSummaryPanel({
  projectId,
  compact = false,
  refreshKey = 0,
  client = workspaceClient,
}: {
  readonly projectId: string;
  readonly compact?: boolean;
  /** 卷章结构变化后由页面递增，重新读取派生汇总。 */
  readonly refreshKey?: number;
  readonly client?: WorkspaceClient;
}) {
  const actionPage = compact ? 5 : 10;
  const [attempt, setAttempt] = useState(0);
  const [summary, setSummary] = useState<SummaryState>({ status: "loading" });
  const [actions, setActions] = useState<ListState<ActionItem>>(emptyList);
  const [chapters, setChapters] =
    useState<ListState<ChapterSummary>>(emptyList);
  const [showChapters, setShowChapters] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setSummary({ status: "loading" });
      setActions({ ...emptyList<ActionItem>(), loading: true });
      setChapters(emptyList);
      setShowChapters(false);
      try {
        // 不中止进行中的只读请求：离开或刷新时只丢弃过期结果，避免无意义的请求失败。
        const [loaded, page] = await Promise.all([
          client.summary(projectId),
          client.actions(projectId, 0, actionPage),
        ]);
        if (controller.signal.aborted) return;
        setSummary({ status: "ready", summary: loaded });
        setActions({
          items: page.items,
          total: page.total,
          nextOffset: page.next_offset,
          loading: false,
          error: "",
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        setSummary({ status: "error", message: workbenchError(error).message });
        setActions(emptyList);
      }
    };
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load();
    });
    return () => controller.abort();
  }, [actionPage, attempt, client, projectId, refreshKey]);

  const loadMoreActions = async () => {
    if (actions.loading || actions.nextOffset === null) return;
    const offset = actions.nextOffset;
    setActions((current) => ({ ...current, loading: true, error: "" }));
    try {
      const page = await client.actions(projectId, offset, actionPage);
      setActions((current) => ({
        items: [...current.items, ...page.items],
        total: page.total,
        nextOffset: page.next_offset,
        loading: false,
        error: "",
      }));
    } catch (error) {
      setActions((current) => ({
        ...current,
        loading: false,
        error: workbenchError(error).message,
      }));
    }
  };

  const loadChapters = async () => {
    setShowChapters(true);
    if (chapters.loading || chapters.nextOffset === null) return;
    const offset = chapters.nextOffset;
    setChapters((current) => ({ ...current, loading: true, error: "" }));
    try {
      const page = await client.chapters(projectId, offset, CHAPTER_PAGE);
      setChapters((current) => ({
        items: [...current.items, ...page.items],
        total: page.total,
        nextOffset: page.next_offset,
        loading: false,
        error: "",
      }));
    } catch (error) {
      setChapters((current) => ({
        ...current,
        loading: false,
        error: workbenchError(error).message,
      }));
    }
  };

  const heading = compact ? "本书进度" : "写作进度与待处理";
  if (summary.status === "loading")
    return (
      <section className="workspace-summary" aria-label={heading}>
        <p>正在读取写作进度…</p>
      </section>
    );
  if (summary.status === "error")
    return (
      <section className="workspace-summary" aria-label={heading}>
        <div role="alert">
          <p>{summary.message}</p>
          <button type="button" onClick={() => setAttempt((v) => v + 1)}>
            重新读取汇总
          </button>
        </div>
      </section>
    );

  const data = summary.summary;
  return (
    <section
      className="workspace-summary"
      aria-label={heading}
      data-feature-id="workbench.summary"
    >
      <div className="workspace-summary__header">
        <h3>{heading}</h3>
        <button type="button" onClick={() => setAttempt((v) => v + 1)}>
          刷新汇总
        </button>
      </div>
      <dl className="workspace-summary__totals">
        <div>
          <dt>已保存正文</dt>
          <dd data-testid="workspace-characters">
            {formatCount(data.characters)} 字
          </dd>
        </div>
        <div>
          <dt>章节</dt>
          <dd>
            {formatCount(data.chapter_count)} 章 /{" "}
            {formatCount(data.volume_count)} 卷
          </dd>
        </div>
        <div>
          <dt>章节状态</dt>
          <dd>
            {EDITORIAL_LABELS.final} {data.editorial.final} ·{" "}
            {EDITORIAL_LABELS.review} {data.editorial.review} ·{" "}
            {EDITORIAL_LABELS.draft} {data.editorial.draft}
          </dd>
        </div>
        <div>
          <dt>待处理</dt>
          <dd data-testid="workspace-action-total">{data.action_total} 项</dd>
        </div>
      </dl>
      <p className="workspace-summary__note">
        字数为各章已保存正文的非空白字符数，不含未采用的 AI 候选；统计于{" "}
        <time dateTime={data.generated_at}>
          {formatProjectTimestamp(data.generated_at)}
        </time>
        。
      </p>
      {!compact && data.volumes.length > 0 ? (
        <ul className="workspace-summary__volumes" aria-label="各卷字数">
          {data.volumes.map((volume) => (
            <li key={volume.volume_id}>
              第{volume.position}卷 · {volume.title}：{volume.chapter_count} 章
              · {formatCount(volume.characters)} 字 · 定稿{" "}
              {volume.editorial.final}
            </li>
          ))}
        </ul>
      ) : null}
      <section className="workspace-summary__todo" aria-label="待处理事项">
        <h4>待处理事项</h4>
        {data.action_total === 0 ? (
          <p>目前没有需要处理的事项。</p>
        ) : (
          <>
            <ActionList projectId={projectId} items={actions.items} />
            {actions.error ? <p role="alert">{actions.error}</p> : null}
            {compact ? (
              actions.nextOffset === null ? null : (
                <Link to={projectStructurePath(projectId)}>
                  查看全部 {actions.total} 处
                </Link>
              )
            ) : actions.nextOffset === null ? null : (
              <button
                type="button"
                disabled={actions.loading}
                onClick={() => void loadMoreActions()}
              >
                {actions.loading ? "正在读取…" : "显示更多待处理"}
              </button>
            )}
          </>
        )}
      </section>
      {compact ? null : (
        <section className="workspace-summary__chapters" aria-label="各章字数">
          {!showChapters ? (
            <button type="button" onClick={() => void loadChapters()}>
              查看各章字数与状态
            </button>
          ) : (
            <>
              <h4>各章字数与状态</h4>
              {chapters.items.length > 0 ? (
                <table>
                  <thead>
                    <tr>
                      <th scope="col">章节</th>
                      <th scope="col">字数</th>
                      <th scope="col">状态</th>
                      <th scope="col">待处理</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chapters.items.map((chapter) => (
                      <tr key={chapter.chapter_id}>
                        <td>
                          <Link
                            to={chapterWritingPath(
                              projectId,
                              chapter.chapter_id,
                            )}
                          >
                            第{chapter.position}章 · {chapter.title}
                          </Link>
                        </td>
                        <td>{formatCount(chapter.characters)}</td>
                        <td>
                          {EDITORIAL_LABELS[chapter.editorial_status]}
                          {chapter.content_changed_since_editorial
                            ? "（之后有修改）"
                            : ""}
                        </td>
                        <td>{chapter.open_actions}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : chapters.loading ? null : (
                <p>还没有章节。</p>
              )}
              {chapters.loading ? <p>正在读取章节…</p> : null}
              {chapters.error ? (
                <div role="alert">
                  <p>{chapters.error}</p>
                  <button type="button" onClick={() => void loadChapters()}>
                    重试
                  </button>
                </div>
              ) : null}
              {chapters.nextOffset !== null &&
              chapters.items.length > 0 &&
              !chapters.loading &&
              !chapters.error ? (
                <button type="button" onClick={() => void loadChapters()}>
                  加载更多章节（已显示 {chapters.items.length}/{chapters.total}
                  ）
                </button>
              ) : null}
            </>
          )}
        </section>
      )}
    </section>
  );
}
