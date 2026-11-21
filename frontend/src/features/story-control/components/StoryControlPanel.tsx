import { useCallback, useEffect, useState, type ReactNode } from "react";

import {
  ATTRIBUTE_LABELS,
  LINK_LABELS,
  PRIORITY_LABELS,
  THREAD_LABELS,
  storyControlClient,
  storyControlError,
  type AnchorRole,
  type ArcPlan,
  type EventDocument,
  type EvidenceAnchor,
  type Goal,
  type GoalDocument,
  type GoalLink,
  type LinkStatus,
  type StateAttribute,
  type StateDocument,
  type StoryControlClient,
  type StoryEvent,
  type Thread,
  type ThreadDocument,
  type ThreadPriority,
  type ThreadStatus,
  type Timeline,
} from "../api/storyControl";
import type { ForeshadowExtractionClient } from "../api/foreshadowExtraction";
import type { PlanProposalClient } from "../api/planProposal";
import { ForeshadowExtractionPanel } from "./ForeshadowExtractionPanel";
import { PlanProposalPanel } from "./PlanProposalPanel";

type Editing =
  | { readonly kind: "goal"; readonly item: Goal | null }
  | { readonly kind: "thread"; readonly item: Thread | null }
  | { readonly kind: "event"; readonly item: StoryEvent | null }
  | { readonly kind: "state" }
  | null;

const ROLE_LABELS: Record<AnchorRole, string> = {
  setup: "埋设",
  advance: "推进",
  payoff: "兑现",
};

function Field({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}) {
  return (
    <label className="story-control__field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function ChapterSelect({
  plan,
  label,
  value,
  onChange,
}: {
  readonly plan: ArcPlan;
  readonly label: string;
  readonly value: string | null;
  readonly onChange: (value: string | null) => void;
}) {
  return (
    <Field label={label}>
      <select
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value || null)}
      >
        <option value="">未指定</option>
        {plan.chapters.map((chapter) => (
          <option key={chapter.chapter_id} value={chapter.chapter_id}>
            第{chapter.volume_position}卷 第{chapter.position}章 {chapter.title}
          </option>
        ))}
      </select>
    </Field>
  );
}

function chapterName(plan: ArcPlan, chapterId: string | null): string {
  const chapter = plan.chapters.find((item) => item.chapter_id === chapterId);
  return chapter
    ? `第${chapter.volume_position}卷第${chapter.position}章「${chapter.title}」`
    : "未指定";
}

function revisionOf(plan: ArcPlan, chapterId: string): string | null {
  return (
    plan.chapters.find((item) => item.chapter_id === chapterId)?.revision_id ??
    null
  );
}

function toggle(values: readonly string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

const EMPTY_GOAL: GoalDocument = {
  scope: "book",
  volume_id: null,
  parent_goal_ids: [],
  title: "",
  conflict: "",
  desire: "",
  obstacle: "",
  turn: "",
  outcome: "",
  opening_state: "",
  target_characters: null,
  status: "active",
  links: [],
};

function GoalForm({
  plan,
  goal,
  onSave,
  onCancel,
}: {
  readonly plan: ArcPlan;
  readonly goal: Goal | null;
  readonly onSave: (document: GoalDocument) => void;
  readonly onCancel: () => void;
}) {
  const [draft, setDraft] = useState<GoalDocument>(goal ?? EMPTY_GOAL);
  const set = (changes: Partial<GoalDocument>) =>
    setDraft((current) => ({ ...current, ...changes }));
  const setLink = (index: number, changes: Partial<GoalLink>) =>
    set({
      links: draft.links.map((link, at) =>
        at === index ? { ...link, ...changes } : link,
      ),
    });
  type TextKey =
    "conflict" | "desire" | "obstacle" | "turn" | "outcome" | "opening_state";
  const text = (label: string, key: TextKey) => (
    <Field label={label}>
      <textarea
        rows={2}
        maxLength={2000}
        value={draft[key]}
        onChange={(event) => set({ [key]: event.target.value })}
      />
    </Field>
  );
  const others = plan.goals.filter((view) => view.goal.id !== goal?.id);
  return (
    <form
      className="story-control__form"
      aria-label={goal ? `编辑目标「${goal.title}」` : "新建目标"}
      onSubmit={(event) => {
        event.preventDefault();
        const original = new Map(
          (goal?.links ?? []).map((link) => [link.chapter_id, link]),
        );
        onSave({
          ...draft,
          volume_id: draft.scope === "volume" ? draft.volume_id : null,
          links: draft.links.map((link) => {
            const quote = link.quote?.trim() ? link.quote.trim() : null;
            const before = original.get(link.chapter_id);
            const revision =
              quote === null
                ? null
                : before?.quote === quote
                  ? before.chapter_revision_id
                  : revisionOf(plan, link.chapter_id);
            return { ...link, quote, chapter_revision_id: revision };
          }),
        });
      }}
    >
      <Field label="层级">
        <select
          value={draft.scope}
          onChange={(event) =>
            set({ scope: event.target.value === "volume" ? "volume" : "book" })
          }
        >
          <option value="book">全书目标</option>
          <option value="volume">分卷目标</option>
        </select>
      </Field>
      {draft.scope === "volume" ? (
        <Field label="所属分卷">
          <select
            required
            value={draft.volume_id ?? ""}
            onChange={(event) => set({ volume_id: event.target.value || null })}
          >
            <option value="">请选择分卷</option>
            {plan.volumes.map((volume) => (
              <option key={volume.volume_id} value={volume.volume_id}>
                第{volume.position}卷 {volume.title}
              </option>
            ))}
          </select>
        </Field>
      ) : null}
      <Field label="目标名称">
        <input
          required
          maxLength={120}
          value={draft.title}
          onChange={(event) => set({ title: event.target.value })}
        />
      </Field>
      {text("核心矛盾 / 冲突", "conflict")}
      {text("主人公欲望", "desire")}
      {text("主要阻碍", "obstacle")}
      {text("转折", "turn")}
      {text("预期变化 / 结局（可留空）", "outcome")}
      {draft.scope === "volume" ? text("开局状态", "opening_state") : null}
      {others.length ? (
        <fieldset>
          <legend>服务的上级目标</legend>
          {others.map((view) => (
            <label key={view.goal.id}>
              <input
                type="checkbox"
                checked={draft.parent_goal_ids.includes(view.goal.id)}
                onChange={() =>
                  set({
                    parent_goal_ids: toggle(
                      draft.parent_goal_ids,
                      view.goal.id,
                    ),
                  })
                }
              />
              {view.goal.title}
            </label>
          ))}
        </fieldset>
      ) : null}
      <fieldset>
        <legend>落实到章节</legend>
        {draft.links.map((link, index) => (
          <div key={link.chapter_id} className="story-control__row">
            <span>{chapterName(plan, link.chapter_id)}</span>
            <Field label="状态">
              <select
                value={link.status}
                onChange={(event) =>
                  setLink(index, { status: event.target.value as LinkStatus })
                }
              >
                {Object.entries(LINK_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="本章说明">
              <input
                maxLength={2000}
                value={link.note}
                onChange={(event) =>
                  setLink(index, { note: event.target.value })
                }
              />
            </Field>
            <Field label="正文原句（可选，作为已体现的证据）">
              <input
                maxLength={2000}
                value={link.quote ?? ""}
                onChange={(event) =>
                  setLink(index, { quote: event.target.value })
                }
              />
            </Field>
            <button
              type="button"
              onClick={() =>
                set({ links: draft.links.filter((_, at) => at !== index) })
              }
            >
              移除该章
            </button>
          </div>
        ))}
        <ChapterSelect
          plan={plan}
          label="添加章节"
          value={null}
          onChange={(chapterId) => {
            if (
              chapterId &&
              !draft.links.some((link) => link.chapter_id === chapterId)
            )
              set({
                links: [
                  ...draft.links,
                  {
                    chapter_id: chapterId,
                    status: "planned",
                    chapter_revision_id: null,
                    quote: null,
                    note: "",
                  },
                ],
              });
          }}
        />
      </fieldset>
      <button type="submit">保存目标</button>
      {goal ? (
        <button
          type="button"
          onClick={() =>
            onSave({
              ...goal,
              status: goal.status === "active" ? "archived" : "active",
            })
          }
        >
          {goal.status === "active" ? "归档目标" : "恢复目标"}
        </button>
      ) : null}
      <button type="button" onClick={onCancel}>
        取消
      </button>
    </form>
  );
}

const EMPTY_THREAD: ThreadDocument = {
  title: "",
  content: "",
  character_ids: [],
  planned_setup_chapter_id: null,
  planned_payoff_chapter_id: null,
  planned_payoff_volume_id: null,
  priority: "normal",
  status: "planned",
  note: "",
  anchors: [],
};

function ThreadForm({
  plan,
  thread,
  onSave,
  onCancel,
}: {
  readonly plan: ArcPlan;
  readonly thread: Thread | null;
  readonly onSave: (document: ThreadDocument) => void;
  readonly onCancel: () => void;
}) {
  const [draft, setDraft] = useState<ThreadDocument>(thread ?? EMPTY_THREAD);
  const [anchor, setAnchor] = useState<{
    role: AnchorRole;
    chapter: string | null;
    quote: string;
  }>({ role: "setup", chapter: null, quote: "" });
  const set = (changes: Partial<ThreadDocument>) =>
    setDraft((current) => ({ ...current, ...changes }));
  const addAnchor = () => {
    const revision = anchor.chapter ? revisionOf(plan, anchor.chapter) : null;
    if (!anchor.chapter || !revision || !anchor.quote.trim()) return;
    const next: EvidenceAnchor = {
      role: anchor.role,
      chapter_id: anchor.chapter,
      chapter_revision_id: revision,
      quote: anchor.quote.trim(),
    };
    set({ anchors: [...draft.anchors, next] });
    setAnchor({ role: anchor.role, chapter: null, quote: "" });
  };
  return (
    <form
      className="story-control__form"
      aria-label={thread ? `编辑伏笔「${thread.title}」` : "新建伏笔"}
      onSubmit={(event) => {
        event.preventDefault();
        onSave(draft);
      }}
    >
      <Field label="伏笔名称">
        <input
          required
          maxLength={120}
          value={draft.title}
          onChange={(event) => set({ title: event.target.value })}
        />
      </Field>
      <Field label="内容">
        <textarea
          rows={2}
          maxLength={2000}
          value={draft.content}
          onChange={(event) => set({ content: event.target.value })}
        />
      </Field>
      {plan.characters.length ? (
        <fieldset>
          <legend>涉及人物</legend>
          {plan.characters.map((character) => (
            <label key={character.character_id}>
              <input
                type="checkbox"
                checked={draft.character_ids.includes(character.character_id)}
                onChange={() =>
                  set({
                    character_ids: toggle(
                      draft.character_ids,
                      character.character_id,
                    ),
                  })
                }
              />
              {character.name}
            </label>
          ))}
        </fieldset>
      ) : null}
      <ChapterSelect
        plan={plan}
        label="预计埋设章"
        value={draft.planned_setup_chapter_id}
        onChange={(value) => set({ planned_setup_chapter_id: value })}
      />
      <ChapterSelect
        plan={plan}
        label="预计兑现章"
        value={draft.planned_payoff_chapter_id}
        onChange={(value) =>
          set({
            planned_payoff_chapter_id: value,
            planned_payoff_volume_id: value
              ? null
              : draft.planned_payoff_volume_id,
          })
        }
      />
      <Field label="或预计兑现卷">
        <select
          value={draft.planned_payoff_volume_id ?? ""}
          onChange={(event) =>
            set({
              planned_payoff_volume_id: event.target.value || null,
              planned_payoff_chapter_id: event.target.value
                ? null
                : draft.planned_payoff_chapter_id,
            })
          }
        >
          <option value="">未指定</option>
          {plan.volumes.map((volume) => (
            <option key={volume.volume_id} value={volume.volume_id}>
              第{volume.position}卷 {volume.title}
            </option>
          ))}
        </select>
      </Field>
      <Field label="优先级">
        <select
          value={draft.priority}
          onChange={(event) =>
            set({ priority: event.target.value as ThreadPriority })
          }
        >
          {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="状态（已埋设需埋设证据，已兑现需兑现证据，放弃需写理由）">
        <select
          value={draft.status}
          onChange={(event) =>
            set({ status: event.target.value as ThreadStatus })
          }
        >
          {Object.entries(THREAD_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="备注 / 延期或放弃理由">
        <input
          maxLength={2000}
          value={draft.note}
          onChange={(event) => set({ note: event.target.value })}
        />
      </Field>
      <fieldset>
        <legend>正文证据</legend>
        <ul>
          {draft.anchors.map((item, index) => (
            <li key={`${item.chapter_id}-${item.role}-${String(index)}`}>
              {ROLE_LABELS[item.role]} · {chapterName(plan, item.chapter_id)}：
              「{item.quote}」
              <button
                type="button"
                onClick={() =>
                  set({
                    anchors: draft.anchors.filter((_, at) => at !== index),
                  })
                }
              >
                移除证据
              </button>
            </li>
          ))}
        </ul>
        <Field label="证据类型">
          <select
            value={anchor.role}
            onChange={(event) =>
              setAnchor({ ...anchor, role: event.target.value as AnchorRole })
            }
          >
            {Object.entries(ROLE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <ChapterSelect
          plan={plan}
          label="证据所在章"
          value={anchor.chapter}
          onChange={(value) => setAnchor({ ...anchor, chapter: value })}
        />
        <Field label="已保存正文中的原句">
          <input
            maxLength={2000}
            value={anchor.quote}
            onChange={(event) =>
              setAnchor({ ...anchor, quote: event.target.value })
            }
          />
        </Field>
        <button
          type="button"
          disabled={!anchor.chapter || !anchor.quote.trim()}
          onClick={addAnchor}
        >
          添加证据
        </button>
      </fieldset>
      <button type="submit">保存伏笔</button>
      <button type="button" onClick={onCancel}>
        取消
      </button>
    </form>
  );
}

function EventForm({
  plan,
  events,
  event: original,
  onSave,
  onCancel,
}: {
  readonly plan: ArcPlan;
  readonly events: readonly StoryEvent[];
  readonly event: StoryEvent | null;
  readonly onSave: (document: EventDocument) => void;
  readonly onCancel: () => void;
}) {
  const [draft, setDraft] = useState<EventDocument>({
    title: original?.title ?? "",
    description: original?.description ?? "",
    story_time: original?.story_time ?? "",
    chapter_id: original?.chapter_id ?? null,
    character_ids: original?.character_ids ?? [],
    after_event_ids: original?.after_event_ids ?? [],
    before_event_ids: original?.before_event_ids ?? [],
    archived: original?.archived ?? false,
  });
  const others = events.filter((item) => item.id !== original?.id);
  const relation = (
    key: "after_event_ids" | "before_event_ids",
    label: string,
  ) =>
    others.length ? (
      <fieldset>
        <legend>{label}</legend>
        {others.map((item) => (
          <label key={item.id}>
            <input
              type="checkbox"
              checked={draft[key].includes(item.id)}
              onChange={() =>
                setDraft({ ...draft, [key]: toggle(draft[key], item.id) })
              }
            />
            {item.title}
          </label>
        ))}
      </fieldset>
    ) : null;
  return (
    <form
      className="story-control__form"
      aria-label={original ? `编辑事件「${original.title}」` : "新建事件"}
      onSubmit={(submit) => {
        submit.preventDefault();
        onSave(draft);
      }}
    >
      <Field label="事件名称">
        <input
          required
          maxLength={120}
          value={draft.title}
          onChange={(change) =>
            setDraft({ ...draft, title: change.target.value })
          }
        />
      </Field>
      <Field label="故事时间（可留空，如“十年前”）">
        <input
          maxLength={120}
          value={draft.story_time}
          onChange={(change) =>
            setDraft({ ...draft, story_time: change.target.value })
          }
        />
      </Field>
      <ChapterSelect
        plan={plan}
        label="叙述所在章"
        value={draft.chapter_id}
        onChange={(value) => setDraft({ ...draft, chapter_id: value })}
      />
      {relation("after_event_ids", "发生在这些事件之后")}
      {relation("before_event_ids", "发生在这些事件之前")}
      <button type="submit">保存事件</button>
      {original ? (
        <button
          type="button"
          onClick={() => onSave({ ...draft, archived: !draft.archived })}
        >
          {draft.archived ? "恢复事件" : "归档事件"}
        </button>
      ) : null}
      <button type="button" onClick={onCancel}>
        取消
      </button>
    </form>
  );
}

function StateForm({
  plan,
  events,
  onSave,
  onCancel,
}: {
  readonly plan: ArcPlan;
  readonly events: readonly StoryEvent[];
  readonly onSave: (document: StateDocument) => void;
  readonly onCancel: () => void;
}) {
  const [draft, setDraft] = useState<StateDocument>({
    character_id: plan.characters[0]?.character_id ?? "",
    attribute: "injury",
    label: "",
    value: "",
    start_event_id: events[0]?.id ?? "",
    end_event_id: null,
    fact_ids: [],
    archived: false,
  });
  return (
    <form
      className="story-control__form"
      aria-label="新建人物状态"
      onSubmit={(submit) => {
        submit.preventDefault();
        onSave(draft);
      }}
    >
      <Field label="人物">
        <select
          required
          value={draft.character_id}
          onChange={(change) =>
            setDraft({ ...draft, character_id: change.target.value })
          }
        >
          {plan.characters.map((item) => (
            <option key={item.character_id} value={item.character_id}>
              {item.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="状态类别">
        <select
          value={draft.attribute}
          onChange={(change) =>
            setDraft({
              ...draft,
              attribute: change.target.value as StateAttribute,
            })
          }
        >
          {Object.entries(ATTRIBUTE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="项目（如“左臂”）">
        <input
          required
          maxLength={120}
          value={draft.label}
          onChange={(change) =>
            setDraft({ ...draft, label: change.target.value })
          }
        />
      </Field>
      <Field label="状态">
        <input
          required
          maxLength={1000}
          value={draft.value}
          onChange={(change) =>
            setDraft({ ...draft, value: change.target.value })
          }
        />
      </Field>
      <Field label="开始事件">
        <select
          required
          value={draft.start_event_id}
          onChange={(change) =>
            setDraft({ ...draft, start_event_id: change.target.value })
          }
        >
          {events.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      </Field>
      <Field label="结束事件（可留空，表示仍然有效）">
        <select
          value={draft.end_event_id ?? ""}
          onChange={(change) =>
            setDraft({ ...draft, end_event_id: change.target.value || null })
          }
        >
          <option value="">仍然有效</option>
          {events.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      </Field>
      <button type="submit">保存人物状态</button>
      <button type="button" onClick={onCancel}>
        取消
      </button>
    </form>
  );
}

export function StoryControlPanel({
  projectId,
  focusThreadId,
  refreshKey = 0,
  client = storyControlClient,
  proposalClient,
  foreshadowClient,
}: {
  readonly projectId: string;
  readonly focusThreadId?: string;
  readonly refreshKey?: number;
  readonly client?: StoryControlClient;
  readonly proposalClient?: PlanProposalClient;
  readonly foreshadowClient?: ForeshadowExtractionClient;
}) {
  const [plan, setPlan] = useState<ArcPlan | null>(null);
  const [splitting, setSplitting] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<Editing>(null);
  const [status, setStatus] = useState<ThreadStatus | "">("");
  const [character, setCharacter] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!focusThreadId || !timeline) return;
    const target = document.getElementById(`thread-${focusThreadId}`);
    target?.scrollIntoView({ block: "center" });
    target?.focus({ preventScroll: true });
  }, [focusThreadId, timeline]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const [nextPlan, nextTimeline] = await Promise.all([
          client.arcPlan(projectId, signal),
          client.timeline(
            projectId,
            {
              ...(status ? { status } : {}),
              ...(character ? { character_id: character } : {}),
            },
            signal,
          ),
        ]);
        setPlan(nextPlan);
        setTimeline(nextTimeline);
        setError("");
      } catch (reason) {
        if (!signal?.aborted) setError(storyControlError(reason).message);
      }
    },
    [character, client, projectId, status],
  );
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) void load(controller.signal);
    });
    return () => controller.abort();
  }, [load, refreshKey]);

  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setNotice("");
    try {
      await action();
      setEditing(null);
      setNotice(done);
      setError("");
      await load();
    } catch (reason) {
      setError(storyControlError(reason).message);
    } finally {
      setBusy(false);
    }
  };

  if (plan === null || timeline === null)
    return (
      <section className="novel-structure-panel story-control">
        <h3>长篇规划与伏笔</h3>
        {error ? (
          <p role="alert">{error}</p>
        ) : (
          <p role="status">正在读取故事规划…</p>
        )}
      </section>
    );

  const events = timeline.events.map((view) => view.event);
  const characterName = (id: string) =>
    plan.characters.find((item) => item.character_id === id)?.name ?? "人物";
  const due = timeline.threads.filter((view) => view.due);

  return (
    <section
      className="novel-structure-panel story-control"
      aria-labelledby="story-control-heading"
    >
      <h3 id="story-control-heading">长篇规划与伏笔</h3>
      <p className="story-control__note">
        全部由你录入与确认；计划不是已发生的正文事实。查看、筛选不调用模型。
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {due.length ? (
        <div className="story-control__due" role="note">
          <h4>需要处理的伏笔（{due.length}）</h4>
          <ul>
            {due.map((view) => (
              <li key={view.thread.id}>
                {view.thread.title}：{view.due_reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <h4>全书与分卷目标</h4>
      {plan.goals.length ? (
        <ul className="story-control__list">
          {plan.goals.map((view) => (
            <li key={view.goal.id}>
              <strong>
                {view.goal.scope === "book" ? "全书" : "分卷"}：
                {view.goal.title}
              </strong>
              {view.goal.status === "archived" ? "（已归档）" : ""}
              <span>
                {" "}
                · 已体现 {view.reflected} 章 · 待落实 {view.open_links} 章
              </span>
              {view.links.length ? (
                <ul>
                  {view.links.map((link) => (
                    <li key={link.chapter_id}>
                      {link.chapter_title ?? "章节已不存在"}（
                      {LINK_LABELS[link.status]}）
                      {link.problem === "missing" ? " · 关联失效" : ""}
                      {link.problem === "evidence_stale"
                        ? " · 证据所在正文已修改，待复核"
                        : ""}
                    </li>
                  ))}
                </ul>
              ) : null}
              <button
                type="button"
                onClick={() => setEditing({ kind: "goal", item: view.goal })}
              >
                编辑「{view.goal.title}」
              </button>
              <button
                type="button"
                onClick={() =>
                  setSplitting((current) =>
                    current === view.goal.id ? null : view.goal.id,
                  )
                }
              >
                建议拆分「{view.goal.title}」
              </button>
              {splitting === view.goal.id ? (
                <PlanProposalPanel
                  projectId={projectId}
                  goal={view.goal}
                  plan={plan}
                  client={proposalClient}
                  onAdopted={() => {
                    setNotice("已采用所选建议卡，规划已更新。");
                    void load();
                  }}
                  onClose={() => setSplitting(null)}
                />
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p>还没有目标。可以先写全书核心矛盾，结局不确定时留空。</p>
      )}
      <button
        type="button"
        onClick={() => setEditing({ kind: "goal", item: null })}
      >
        新建目标
      </button>
      {editing?.kind === "goal" ? (
        <GoalForm
          key={editing.item?.id ?? "new"}
          plan={plan}
          goal={editing.item}
          onCancel={() => setEditing(null)}
          onSave={(document) =>
            void run(
              () =>
                client.saveGoal(
                  projectId,
                  editing.item?.id ?? null,
                  document,
                  editing.item?.version ?? 0,
                ),
              "目标已保存。",
            )
          }
        />
      ) : null}

      <h4>伏笔</h4>
      <div className="story-control__filters">
        <Field label="按状态筛选">
          <select
            value={status}
            onChange={(event) =>
              setStatus(event.target.value as ThreadStatus | "")
            }
          >
            <option value="">全部</option>
            {Object.entries(THREAD_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="按人物筛选">
          <select
            value={character}
            onChange={(event) => setCharacter(event.target.value)}
          >
            <option value="">全部人物</option>
            {plan.characters.map((item) => (
              <option key={item.character_id} value={item.character_id}>
                {item.name}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {timeline.threads.length ? (
        <ul className="story-control__list">
          {timeline.threads.map((view) => (
            <li
              key={view.thread.id}
              id={`thread-${view.thread.id}`}
              tabIndex={-1}
            >
              <strong>{view.thread.title}</strong>（
              {THREAD_LABELS[view.thread.status]} · 优先级
              {PRIORITY_LABELS[view.thread.priority]}）
              <span>
                {" "}
                埋设：{chapterName(plan, view.thread.planned_setup_chapter_id)}
                ；兑现：
                {view.thread.planned_payoff_volume_id
                  ? `第${
                      plan.volumes.find(
                        (item) =>
                          item.volume_id ===
                          view.thread.planned_payoff_volume_id,
                      )?.position ?? "?"
                    }卷`
                  : chapterName(plan, view.thread.planned_payoff_chapter_id)}
              </span>
              {view.evidence_stale ? <span> · 证据待复核</span> : null}
              <button
                type="button"
                onClick={() =>
                  setEditing({ kind: "thread", item: view.thread })
                }
              >
                编辑伏笔「{view.thread.title}」
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p>没有符合条件的伏笔。</p>
      )}
      <button
        type="button"
        onClick={() => setEditing({ kind: "thread", item: null })}
      >
        新建伏笔
      </button>
      <button
        type="button"
        onClick={() => setExtracting((current) => !current)}
      >
        批量提取伏笔建议
      </button>
      {extracting ? (
        <ForeshadowExtractionPanel
          projectId={projectId}
          plan={plan}
          client={foreshadowClient}
          onAdopted={() => {
            setNotice("已采用所选伏笔建议卡，伏笔已更新。");
            void load();
          }}
          onClose={() => setExtracting(false)}
        />
      ) : null}
      {editing?.kind === "thread" ? (
        <ThreadForm
          key={editing.item?.id ?? "new"}
          plan={plan}
          thread={editing.item}
          onCancel={() => setEditing(null)}
          onSave={(document) =>
            void run(
              () =>
                client.saveThread(
                  projectId,
                  editing.item?.id ?? null,
                  document,
                  editing.item?.version ?? 0,
                ),
              "伏笔已保存。",
            )
          }
        />
      ) : null}

      <h4>故事时间线（按故事发生顺序）</h4>
      {timeline.events.length ? (
        <ol className="story-control__list">
          {timeline.events.map((view) => (
            <li key={view.event.id}>
              {view.event.title}
              {view.event.story_time ? `（${view.event.story_time}）` : ""}
              <span>
                {" "}
                · 叙述位置：
                {view.narrative_position
                  ? `第${view.narrative_position[0]}卷第${view.narrative_position[1]}章`
                  : "未指定"}
              </span>
              <button
                type="button"
                onClick={() => setEditing({ kind: "event", item: view.event })}
              >
                编辑事件「{view.event.title}」
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p>还没有事件。故事时间可以留空，用“之前/之后”描述先后。</p>
      )}
      <button
        type="button"
        onClick={() => setEditing({ kind: "event", item: null })}
      >
        新建事件
      </button>
      {editing?.kind === "event" ? (
        <EventForm
          key={editing.item?.id ?? "new"}
          plan={plan}
          events={events}
          event={editing.item}
          onCancel={() => setEditing(null)}
          onSave={(document) =>
            void run(
              () =>
                client.saveEvent(
                  projectId,
                  editing.item?.id ?? null,
                  document,
                  editing.item?.version ?? 0,
                ),
              "事件已保存。",
            )
          }
        />
      ) : null}

      <h4>人物状态</h4>
      {timeline.warnings.map((warning) => (
        <p key={warning.state_ids.join("-")} role="note">
          {warning.message}
        </p>
      ))}
      {timeline.states.length ? (
        <ul className="story-control__list">
          {timeline.states.map((view) => {
            const start = events.find(
              (item) => item.id === view.state.start_event_id,
            );
            const end = events.find(
              (item) => item.id === view.state.end_event_id,
            );
            return (
              <li key={view.state.id}>
                {characterName(view.state.character_id)} ·{" "}
                {ATTRIBUTE_LABELS[view.state.attribute]}「{view.state.label}」：
                {view.state.value}（{start?.title ?? "事件"} →{" "}
                {view.state.end_event_id ? (end?.title ?? "事件") : "仍然有效"}
                ）{view.invalid_fact_ids.length ? " · 关联事实已失效" : ""}
              </li>
            );
          })}
        </ul>
      ) : (
        <p>还没有人物状态。</p>
      )}
      <button
        type="button"
        disabled={!plan.characters.length || !events.length}
        onClick={() => setEditing({ kind: "state" })}
      >
        新建人物状态
      </button>
      {!plan.characters.length || !events.length ? (
        <p>先添加人物和至少一个事件，才能记录人物状态区间。</p>
      ) : null}
      {editing?.kind === "state" ? (
        <StateForm
          plan={plan}
          events={events}
          onCancel={() => setEditing(null)}
          onSave={(document) =>
            void run(
              () => client.saveState(projectId, null, document, 0),
              "人物状态已保存。",
            )
          }
        />
      ) : null}
      {busy ? <p role="status">正在保存…</p> : null}
    </section>
  );
}

/** Collapsed until the author opens it, so the structure page makes no extra reads. */
export function StoryControlSection({
  projectId,
  focusThreadId,
  refreshKey,
  client,
  proposalClient,
  foreshadowClient,
}: {
  readonly projectId: string;
  readonly focusThreadId?: string;
  readonly refreshKey?: number;
  readonly client?: StoryControlClient;
  readonly proposalClient?: PlanProposalClient;
  readonly foreshadowClient?: ForeshadowExtractionClient;
}) {
  const [opened, setOpened] = useState(false);
  return (
    <details
      open={Boolean(focusThreadId) || undefined}
      className="story-control-section"
      onToggle={(event) => {
        if (event.currentTarget.open) setOpened(true);
      }}
    >
      <summary>
        长篇规划与伏笔（全书/分卷目标、伏笔、故事时间线、人物状态）
      </summary>
      {opened || focusThreadId ? (
        <StoryControlPanel
          focusThreadId={focusThreadId}
          projectId={projectId}
          refreshKey={refreshKey}
          client={client}
          proposalClient={proposalClient}
          foreshadowClient={foreshadowClient}
        />
      ) : null}
    </details>
  );
}
