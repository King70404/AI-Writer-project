import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import { projectStructurePath } from "../../projects/routing";
import {
  LINK_LABELS,
  OMIT_LABELS,
  THREAD_LABELS,
  storyControlClient,
  storyControlError,
  type ChapterGuide,
  type FactHit,
  type RecallPolicyState,
  type RecallPreview,
  type StoryControlClient,
  type ThreadView,
} from "../api/storyControl";

function n(value: number): string {
  return value.toLocaleString("zh-CN");
}

function ThreadList({
  title,
  items,
}: {
  readonly title: string;
  readonly items: readonly ThreadView[];
}) {
  if (!items.length) return null;
  return (
    <>
      <h5>{title}</h5>
      <ul>
        {items.map((view) => (
          <li key={view.thread.id}>
            {view.thread.title}（{THREAD_LABELS[view.thread.status]}）
            {view.due_reason ? <span> · {view.due_reason}</span> : null}
          </li>
        ))}
      </ul>
    </>
  );
}

export function ChapterGuideCard({
  projectId,
  chapterId,
  sourceRevision,
  client = storyControlClient,
}: {
  readonly projectId: string;
  readonly chapterId: string;
  readonly sourceRevision: string;
  readonly client?: StoryControlClient;
}) {
  const [guide, setGuide] = useState<ChapterGuide | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    client.guide(chapterId, controller.signal).then(
      (value) => {
        setGuide(value);
        setError("");
      },
      (reason: unknown) => {
        if (!controller.signal.aborted)
          setError(storyControlError(reason).message);
      },
    );
    return () => controller.abort();
  }, [chapterId, client, sourceRevision]);
  const empty =
    guide !== null &&
    !guide.goals.length &&
    !guide.setup_threads.length &&
    !guide.payoff_threads.length &&
    !guide.due_threads.length;
  return (
    <section className="story-guide" aria-labelledby="story-guide-title">
      <h4 id="story-guide-title">本章任务（作者计划）</h4>
      {error ? <p role="alert">{error}</p> : null}
      {guide === null && !error ? <p role="status">正在读取本章计划…</p> : null}
      {empty ? (
        <p>
          本章还没有关联全书/分卷目标或伏笔。可在
          <Link to={projectStructurePath(projectId)}>小说结构</Link>
          中规划；不规划也能继续写作。
        </p>
      ) : null}
      {guide?.goals.length ? (
        <>
          <h5>服务的目标</h5>
          <ul>
            {guide.goals.map((view) => {
              const link = view.links.find(
                (item) => item.chapter_id === chapterId,
              );
              return (
                <li key={view.goal.id}>
                  {view.goal.scope === "book" ? "全书" : "分卷"}：
                  {view.goal.title}
                  {link ? `（${LINK_LABELS[link.status]}）` : ""}
                  {link?.note ? ` · ${link.note}` : ""}
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
      {guide ? (
        <>
          <ThreadList title="计划在本章埋设" items={guide.setup_threads} />
          <ThreadList
            title="计划在本章或本卷兑现"
            items={guide.payoff_threads}
          />
          <ThreadList title="需要处理的伏笔" items={guide.due_threads} />
        </>
      ) : null}
      <p className="story-guide__note">
        计划会作为“计划，非已发生事实”随准备的任务一起冻结；不会自动改变伏笔状态。
      </p>
    </section>
  );
}

function toggle(values: readonly string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

export function RecallControl({
  projectId,
  chapterId,
  sourceRevision,
  lastRecall,
  client = storyControlClient,
}: {
  readonly projectId: string;
  readonly chapterId: string;
  readonly sourceRevision: string;
  /** Fact ids frozen in the most recently prepared task, for the difference view. */
  readonly lastRecall?: readonly string[];
  readonly client?: StoryControlClient;
}) {
  const [policy, setPolicy] = useState<RecallPolicyState | null>(null);
  const [pinned, setPinned] = useState<readonly string[]>([]);
  const [excluded, setExcluded] = useState<readonly string[]>([]);
  const [preview, setPreview] = useState<RecallPreview | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<readonly FactHit[] | null>(null);
  const [total, setTotal] = useState(0);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const current = await client.recallPolicy(chapterId, signal);
        setPolicy(current);
        setPinned(current.pinned_fact_ids);
        setExcluded(current.excluded_fact_ids);
        setError("");
      } catch (reason) {
        if (!signal?.aborted) setError(storyControlError(reason).message);
      }
    },
    [chapterId, client],
  );
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load(controller.signal);
    });
    return () => controller.abort();
  }, [load, sourceRevision]);
  useEffect(() => {
    if (policy === null) return;
    let active = true;
    client.recallPreview(chapterId, pinned, excluded).then(
      (value) => {
        if (active) setPreview(value);
      },
      (reason: unknown) => {
        if (active) setError(storyControlError(reason).message);
      },
    );
    return () => {
      active = false;
    };
  }, [chapterId, client, excluded, pinned, policy]);

  const search = async () => {
    try {
      const page = await client.searchFacts(projectId, {
        q: query.trim(),
        status: "confirmed",
        forChapter: chapterId,
      });
      setHits(page.items);
      setTotal(page.total);
      setError("");
    } catch (reason) {
      setError(storyControlError(reason).message);
    }
  };
  const save = async () => {
    if (policy === null) return;
    setSaving(true);
    setMessage("");
    try {
      const saved = await client.saveRecallPolicy(
        chapterId,
        pinned,
        excluded,
        policy.version,
      );
      setPolicy(saved);
      setMessage(
        `已保存为本章召回设置第 ${saved.version} 版；下次“准备”任务时生效，已准备的任务不变。`,
      );
      setError("");
    } catch (reason) {
      const failure = storyControlError(reason);
      setError(failure.message);
      if (failure.code === "STORY_CONTROL_CONFLICT") {
        const current = await client.recallPolicy(chapterId).catch(() => null);
        if (current) setPolicy(current);
      }
    } finally {
      setSaving(false);
    }
  };
  const dirty =
    policy !== null &&
    (policy.pinned_fact_ids.join() !== pinned.join() ||
      policy.excluded_fact_ids.join() !== excluded.join());
  const difference = useMemo(() => {
    if (!preview || lastRecall === undefined) return null;
    const now = preview.selected.map((item) => item.id);
    return {
      added: preview.selected.filter((item) => !lastRecall.includes(item.id)),
      removed: lastRecall.filter((item) => !now.includes(item)).length,
    };
  }, [lastRecall, preview]);
  const titles = new Map(
    [...(preview?.selected ?? []), ...(preview?.omitted ?? [])].map((item) => [
      item.id,
      item.title,
    ]),
  );

  return (
    <section className="recall-control" aria-labelledby="recall-control-title">
      <h4 id="recall-control-title">本次依据（前文事实召回）</h4>
      {error ? <p role="alert">{error}</p> : null}
      {preview ? (
        <>
          <p>
            已选 {n(preview.selected.length)} / {preview.item_limit}{" "}
            项（作者固定{" "}
            {n(
              preview.selected.filter((item) => item.reason === "pinned")
                .length,
            )}{" "}
            项），占用 {n(preview.used_characters)} /{" "}
            {n(preview.character_limit)} 字符；因预算省略{" "}
            {n(preview.omitted_total)} 项，作者排除 {n(preview.excluded_total)}{" "}
            项。
          </p>
          <meter
            aria-label="事实召回字符预算"
            min={0}
            max={preview.character_limit}
            value={preview.used_characters}
          />
          {preview.blocked ? (
            <div role="alert">
              <p>固定的事实有问题，准备任务会被拒绝（不会悄悄丢掉固定项）：</p>
              <ul>
                {preview.omitted
                  .filter((item) => item.reason.startsWith("pin_"))
                  .map((item) => (
                    <li key={item.id}>
                      {item.title ?? "已删除的事实"}：{OMIT_LABELS[item.reason]}
                    </li>
                  ))}
              </ul>
            </div>
          ) : null}
          <ol className="recall-control__selected">
            {preview.selected.map((item) => (
              <li key={item.id}>
                {item.title}（
                {item.reason === "pinned" ? "作者固定" : "文字关联"} ·{" "}
                {n(item.characters)} 字符）
              </li>
            ))}
          </ol>
          {difference ? (
            <p>
              与上次准备的任务相比：新增 {n(difference.added.length)} 项
              {difference.added.length
                ? `（${difference.added.map((item) => item.title).join("、")}）`
                : ""}
              ，移除 {n(difference.removed)} 项。重新准备后才会使用新的依据。
            </p>
          ) : null}
        </>
      ) : (
        <p role="status">正在计算本次依据…</p>
      )}
      <details>
        <summary>调整依据</summary>
        <p>
          检索作者已确认的事实，固定关键事实或排除无关事实。只在本机检索，不调用模型。
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void search();
          }}
        >
          <label>
            关键词
            <input
              value={query}
              maxLength={100}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <button type="submit">检索事实</button>
        </form>
        {hits !== null ? (
          <>
            <p role="status">找到 {n(total)} 条已确认事实。</p>
            <ul className="recall-control__hits">
              {hits.map((hit) => {
                const isPinned = pinned.includes(hit.id);
                const isExcluded = excluded.includes(hit.id);
                return (
                  <li key={hit.id}>
                    <strong>{hit.title}</strong>
                    {hit.chapter_title ? `（${hit.chapter_title}）` : ""}：
                    {hit.text}
                    {hit.stale ? "（来源已修改，需重新确认）" : ""}
                    {hit.recallable_here === false
                      ? "（不在本章之前或已失效，不能召回）"
                      : ""}
                    <button
                      type="button"
                      aria-pressed={isPinned}
                      disabled={!isPinned && hit.recallable_here === false}
                      onClick={() => {
                        setPinned(toggle(pinned, hit.id));
                        setExcluded(excluded.filter((item) => item !== hit.id));
                      }}
                    >
                      {isPinned
                        ? `取消固定「${hit.title}」`
                        : `固定「${hit.title}」`}
                    </button>
                    <button
                      type="button"
                      aria-pressed={isExcluded}
                      onClick={() => {
                        setExcluded(toggle(excluded, hit.id));
                        setPinned(pinned.filter((item) => item !== hit.id));
                      }}
                    >
                      {isExcluded
                        ? `取消排除「${hit.title}」`
                        : `排除「${hit.title}」`}
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        ) : null}
        {pinned.length || excluded.length ? (
          <p>
            固定：
            {pinned.map((item) => titles.get(item) ?? "已选事实").join("、") ||
              "无"}
            ；排除：
            {excluded
              .map((item) => titles.get(item) ?? "已选事实")
              .join("、") || "无"}
          </p>
        ) : null}
        <button
          type="button"
          disabled={!dirty || saving}
          onClick={() => void save()}
        >
          {saving ? "正在保存…" : "保存为本章召回设置"}
        </button>
        {dirty ? (
          <p>有未保存的调整；上方依据是预览，尚未用于准备任务。</p>
        ) : null}
        {message ? <p role="status">{message}</p> : null}
      </details>
    </section>
  );
}
