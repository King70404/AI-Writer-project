import { useEffect, useRef, useState } from "react";
import type { ModelProfile } from "../api/ai-workflow";
import {
  analysisFailureMessage,
  preparationError,
  writingPreparationClient,
  type ChapterPlan,
  type RuleRevision,
  type WritingPreparationClient,
  type WritingReference,
  type WritingRule,
} from "../api/writing-preparation";
import {
  ChapterPlanningEditor,
  type ChapterPlanningHandle,
} from "./ChapterPlanningEditor";

const STATUS = {
  ready: "待确认分析",
  analyzing: "正在分析",
  analyzed: "分析已保存",
  failed: "上次分析未完成",
};

export function ReferenceWritingWorkbench({
  projectId,
  chapterId,
  profile,
  content,
  onDirty,
  onOpenGenerate,
  client = writingPreparationClient,
}: {
  readonly projectId: string;
  readonly chapterId: string;
  readonly profile: ModelProfile | undefined;
  readonly content: string;
  readonly onDirty: (dirty: boolean) => void;
  /** 规划保存后返回“生成”分区准备续写（不发送模型）。 */
  readonly onOpenGenerate?: () => void;
  readonly client?: WritingPreparationClient;
}) {
  const [references, setReferences] = useState<readonly WritingReference[]>([]);
  const [rules, setRules] = useState<readonly RuleRevision[]>([]);
  const [plan, setPlan] = useState<ChapterPlan | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [planningBusy, setPlanningBusy] = useState(false);
  const [actionTarget, setActionTarget] = useState<
    "prepare" | "analysis" | "rules" | null
  >(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [granularity, setGranularity] = useState<"sentence" | "paragraph">(
    "sentence",
  );
  const [selectedId, setSelectedId] = useState("");
  const [consentId, setConsentId] = useState("");
  const [ruleTitle, setRuleTitle] = useState("");
  const [draftRules, setDraftRules] = useState<readonly WritingRule[]>([]);
  const [ruleReference, setRuleReference] = useState<string | null>(null);
  const [previous, setPrevious] = useState<RuleRevision>();
  const lock = useRef(false);
  const planning = useRef<ChapterPlanningHandle>(null);
  const [planSavedNotice, setPlanSavedNotice] = useState(false);
  const [shortcutMessage, setShortcutMessage] = useState("");
  const applyRuleToChapter = (revision: RuleRevision) => {
    const result = planning.current?.addRule(revision.id) ?? "busy";
    setShortcutMessage(
      result === "added"
        ? `已把“${revision.title}”版本 ${revision.version} 加入本章规划，尚未保存。请在下方核对后点击“保存章节规划”。`
        : result === "already_selected"
          ? `本章规划已选用“${revision.title}”版本 ${revision.version}。`
          : result === "limit"
            ? "本章规划最多选用 8 份规则版本，请先取消一份再加入。"
            : "规划正在保存或处理中，请稍后再加入。",
    );
    if (result === "added" || result === "already_selected") {
      setPlanSavedNotice(false);
      queueMicrotask(() =>
        document
          .querySelector<HTMLInputElement>(
            `input[data-rule-revision-id="${revision.id}"]`,
          )
          ?.focus(),
      );
    }
  };
  const selected = references.find((item) => item.id === selectedId);
  const unavailable = busy || planningBusy;

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setBusy(true);
      setError("");
      void Promise.all([
        client.references(projectId),
        client.rules(projectId),
        client.plan(projectId, chapterId),
      ])
        .then(([nextReferences, nextRules, nextPlan]) => {
          if (!active) return;
          setReferences(nextReferences);
          setRules(nextRules);
          setPlan(nextPlan);
          setLoaded(true);
        })
        .catch((failure: unknown) => {
          if (active) setError(preparationError(failure).message);
        })
        .finally(() => {
          if (active) setBusy(false);
        });
    });
    return () => {
      active = false;
    };
  }, [chapterId, client, projectId, reloadKey]);
  const storeReference = (reference: WritingReference) => {
    setReferences((current) => [
      reference,
      ...current.filter((item) => item.id !== reference.id),
    ]);
    setSelectedId(reference.id);
  };
  const action = async (
    target: "prepare" | "analysis" | "rules",
    work: () => Promise<void>,
  ) => {
    if (lock.current || planningBusy) return;
    lock.current = true;
    setActionTarget(target);
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await work();
    } catch (failure) {
      setError(preparationError(failure).message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const prepare = () =>
    action("prepare", async () => {
      if (!profile || !title.trim() || !text.trim()) {
        setError("请填写范文名称、粘贴范文并选择模型。");
        return;
      }
      const reference = await client.prepareReference(projectId, {
        title: title.trim(),
        text,
        granularity,
        profile_id: profile.id,
      });
      storeReference(reference);
      setConsentId("");
      setMessage("范文已保存。请核对发送内容，再确认分析。");
    });
  const analyze = () =>
    action("analysis", async () => {
      if (!selected) return;
      try {
        const result = await client.analyze(
          projectId,
          selected,
          consentId === selected.id,
        );
        storeReference(result);
        setMessage("分析已保存。查看对照说明后，可编辑并确认写作规则。");
      } catch (failure) {
        try {
          storeReference(await client.reference(projectId, selected.id));
        } catch {
          /* Keep the frozen reference when reconciliation is unavailable. */
        }
        throw failure;
      }
    });
  const editRules = (source: WritingReference) => {
    setActionTarget("rules");
    setError("");
    setRuleTitle(`${source.title} 写作方法`);
    setRuleReference(source.id);
    setDraftRules(source.analysis?.rules ?? []);
    setPrevious(undefined);
    setMessage("已载入建议规则，请检查并修改适用范围，再确认保存。");
  };
  const saveRules = () =>
    action("rules", async () => {
      if (
        !ruleTitle.trim() ||
        draftRules.some(
          (item) =>
            !item.name.trim() ||
            !item.instruction.trim() ||
            !item.applies_to.trim(),
        )
      ) {
        setError("请填写规则名称、操作方法和适用范围。");
        return;
      }
      const saved = await client.confirmRules(
        projectId,
        {
          title: ruleTitle.trim(),
          reference_id: ruleReference,
          rules: draftRules,
        },
        previous,
      );
      setRules((current) => [
        saved,
        ...current.filter((item) => item.id !== saved.id),
      ]);
      setPrevious(saved);
      setShortcutMessage("");
      setMessage(
        `规则已确认保存为版本 ${saved.version}。可点击“将此规则加入本章规划”，或在章节规划中勾选该版本并保存。`,
      );
    });
  return (
    <section
      aria-label="范文分析与章节规划"
      className="reference-writing-workbench"
    >
      <h4>范文分析与章节规划</h4>
      <p>
        粘贴范文 → 对照句段分析 → 确认写作方法 → 规划本章 →
        准备续写或改写。分析中的“写作原因”是根据文字推测的效果与用意。
      </p>
      {error && actionTarget !== "analysis" && actionTarget !== "rules" ? (
        <p role="alert">{error}</p>
      ) : null}
      {message && actionTarget !== "analysis" && actionTarget !== "rules" ? (
        <p role="status">{message}</p>
      ) : null}
      {busy && actionTarget !== "analysis" && actionTarget !== "rules" ? (
        <p role="status">正在处理范文与规划，请稍候…</p>
      ) : null}
      <button
        type="button"
        disabled={unavailable}
        onClick={() => {
          setActionTarget(null);
          setMessage("");
          onDirty(false);
          setLoaded(false);
          setReloadKey((value) => value + 1);
        }}
      >
        丢弃未保存规划并重新加载
      </button>
      {loaded ? (
        <>
          <fieldset disabled={unavailable}>
            <legend>粘贴范文</legend>
            <label>
              范文名称
              <input
                maxLength={120}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label>
              范文原文
              <textarea
                rows={6}
                maxLength={8000}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            </label>
            <label>
              分析粒度
              <select
                value={granularity}
                onChange={(event) =>
                  setGranularity(event.target.value as "sentence" | "paragraph")
                }
              >
                <option value="sentence">逐句分析</option>
                <option value="paragraph">逐段分析</option>
              </select>
            </label>
            <p>
              单份最多 8000 字、40 个句段。建议先选 3–8 句；详细分析需要较多输出
              Token，可在模型配置中提高上限或缩短范文。长范文可分批保存。当前模型：
              {profile?.name ?? "请在上方添加并选择模型"}。
            </p>
            <button
              type="button"
              disabled={!profile}
              onClick={() => void prepare()}
            >
              保存范文并准备分析
            </button>
            <label>
              已保存范文
              <select
                value={selectedId}
                onChange={(event) => {
                  setSelectedId(event.target.value);
                  setConsentId("");
                  setError("");
                  setMessage("");
                  setActionTarget(null);
                }}
              >
                <option value="">选择范文查看</option>
                {references.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} · {STATUS[item.status]}
                  </option>
                ))}
              </select>
            </label>
          </fieldset>
          {selected ? (
            <section aria-label="当前范文分析">
              <h5>{selected.title}</h5>
              <p role="status">
                {STATUS[selected.status]} · 已发送 {selected.attempts}/3 次
              </p>
              <p>
                分析模型：{selected.model_snapshot.name}；服务地址：
                {selected.model_snapshot.base_url}；输出上限{" "}
                {selected.model_snapshot.max_output_tokens} Token。
              </p>
              <details>
                <summary>查看范文分析实际发送内容</summary>
                {selected.messages.map((item, index) => (
                  <label key={index}>
                    分析请求 {index + 1} · {item.role}
                    <textarea readOnly rows={6} value={item.content} />
                  </label>
                ))}
              </details>
              {selected.status === "failed" ? (
                <p
                  role={
                    actionTarget === "analysis" && error ? undefined : "alert"
                  }
                >
                  {analysisFailureMessage(selected.last_error ?? "")}
                  已保存的范文保留；系统不会自动重发。
                </p>
              ) : null}
              {selected.status === "ready" || selected.status === "failed" ? (
                <>
                  {selected.model_snapshot.kind === "cloud" ? (
                    <label>
                      <input
                        type="checkbox"
                        disabled={unavailable}
                        checked={consentId === selected.id}
                        onChange={(event) =>
                          setConsentId(event.target.checked ? selected.id : "")
                        }
                      />
                      我同意向该云端模型发送此范文与分析要求
                    </label>
                  ) : null}
                  <button
                    type="button"
                    disabled={
                      unavailable ||
                      selected.attempts >= 3 ||
                      (selected.model_snapshot.kind === "cloud" &&
                        consentId !== selected.id)
                    }
                    onClick={() => void analyze()}
                  >
                    {busy && actionTarget === "analysis"
                      ? "正在发送并分析范文…"
                      : "确认发送并分析范文"}
                  </button>
                </>
              ) : null}
              {actionTarget === "analysis" && error ? (
                <p role="alert">{error}</p>
              ) : null}
              {actionTarget === "analysis" && message ? (
                <p role="status">{message}</p>
              ) : null}
              {busy && actionTarget === "analysis" ? (
                <p role="status">
                  分析请求正在处理，请等待模型回复；不会重复发送。
                </p>
              ) : null}
              {selected.analysis ? (
                <>
                  <p className="reference-long-form-notes">
                    长篇应用建议：{selected.analysis.long_form_notes}
                  </p>
                  <div className="reference-analysis-list">
                    {selected.analysis.units.map((unit) => (
                      <article key={unit.unit_id}>
                        <h6>
                          句段{" "}
                          {selected.units.findIndex(
                            (item) => item.id === unit.unit_id,
                          ) + 1}
                        </h6>
                        <blockquote>
                          {
                            selected.units.find(
                              (item) => item.id === unit.unit_id,
                            )?.text
                          }
                        </blockquote>
                        <dl>
                          <dt>对应文字</dt>
                          <dd>{unit.quote}</dd>
                          <dt>句段作用</dt>
                          <dd>{unit.function}</dd>
                          <dt>阅读效果</dt>
                          <dd>{unit.effect}</dd>
                          <dt>写作原因（推测）</dt>
                          <dd>{unit.rationale}</dd>
                          <dt>原创写作如何应用</dt>
                          <dd>{unit.transfer}</dd>
                        </dl>
                      </article>
                    ))}
                  </div>
                  <button
                    type="button"
                    disabled={unavailable}
                    onClick={() => editRules(selected)}
                  >
                    编辑并提炼这份范文的写作规则
                  </button>
                </>
              ) : null}
            </section>
          ) : null}
          <section aria-label="确认写作规则">
            <h4>可复用的写作规则</h4>
            {actionTarget === "rules" && error ? (
              <p role="alert">{error}</p>
            ) : null}
            {actionTarget === "rules" && message ? (
              <p role="status">{message}</p>
            ) : null}
            {busy && actionTarget === "rules" ? (
              <p role="status">正在保存规则版本…</p>
            ) : null}
            <p>
              只提炼可复用的方法。确认后的规则仍须在本章规划中选择，才会进入下一次生成上下文；范文原句不会自动作为正文。
            </p>
            <label>
              编辑已有规则版本
              <select
                disabled={unavailable}
                value={previous?.id ?? ""}
                onChange={(event) => {
                  const revision = rules.find(
                    (item) => item.id === event.target.value,
                  );
                  setPrevious(revision);
                  setRuleTitle(revision?.title ?? "");
                  setRuleReference(revision?.reference_id ?? null);
                  setDraftRules(revision?.rules ?? []);
                }}
              >
                <option value="">新建规则</option>
                {rules.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} · 版本 {item.version}
                  </option>
                ))}
              </select>
            </label>
            <fieldset disabled={unavailable}>
              <legend>
                {previous
                  ? `编辑版本 ${previous.version}，保存时创建新版本`
                  : "待确认的规则"}
              </legend>
              <label>
                规则集名称
                <input
                  maxLength={120}
                  value={ruleTitle}
                  onChange={(event) => setRuleTitle(event.target.value)}
                />
              </label>
              {draftRules.map((item, index) => (
                <fieldset key={index}>
                  <legend>规则 {index + 1}</legend>
                  <label>
                    规则 {index + 1} 名称
                    <input
                      maxLength={80}
                      value={item.name}
                      onChange={(event) =>
                        setDraftRules(
                          draftRules.map((rule, position) =>
                            position === index
                              ? { ...rule, name: event.target.value }
                              : rule,
                          ),
                        )
                      }
                    />
                  </label>
                  <label>
                    规则 {index + 1} 操作方法
                    <textarea
                      rows={3}
                      maxLength={1000}
                      value={item.instruction}
                      onChange={(event) =>
                        setDraftRules(
                          draftRules.map((rule, position) =>
                            position === index
                              ? { ...rule, instruction: event.target.value }
                              : rule,
                          ),
                        )
                      }
                    />
                  </label>
                  <label>
                    规则 {index + 1} 适用范围
                    <input
                      maxLength={200}
                      value={item.applies_to}
                      onChange={(event) =>
                        setDraftRules(
                          draftRules.map((rule, position) =>
                            position === index
                              ? { ...rule, applies_to: event.target.value }
                              : rule,
                          ),
                        )
                      }
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() =>
                      setDraftRules(
                        draftRules.filter((_, position) => position !== index),
                      )
                    }
                  >
                    删除规则 {index + 1}
                  </button>
                </fieldset>
              ))}
              <button
                type="button"
                disabled={draftRules.length >= 8}
                onClick={() =>
                  setDraftRules([
                    ...draftRules,
                    { name: "", instruction: "", applies_to: "" },
                  ])
                }
              >
                增加写作规则
              </button>
              <button
                type="button"
                disabled={!draftRules.length}
                onClick={() => void saveRules()}
              >
                确认保存写作规则{previous ? "新版本" : ""}
              </button>
            </fieldset>
            {previous ? (
              <div className="reference-shortcut">
                <button
                  type="button"
                  disabled={unavailable}
                  onClick={() => applyRuleToChapter(previous)}
                >
                  将此规则加入本章规划
                </button>
                <p>
                  只修改本章规划中“写作规则版本”的选择，保留其他未保存修改；保存规划前不会影响生成。
                </p>
              </div>
            ) : null}
            {shortcutMessage ? <p role="status">{shortcutMessage}</p> : null}
          </section>
          <ChapterPlanningEditor
            ref={planning}
            key={`${reloadKey}:${plan?.revision_id ?? "new"}`}
            projectId={projectId}
            chapterId={chapterId}
            plan={plan}
            rules={rules}
            content={content}
            client={client}
            onSaved={(saved) => {
              setPlan(saved);
              setShortcutMessage("");
              setPlanSavedNotice(true);
            }}
            onDirty={onDirty}
            disabled={busy}
            onBusy={setPlanningBusy}
          />
          {planSavedNotice && onOpenGenerate ? (
            <div
              className="reference-shortcut"
              role="group"
              aria-label="规划已保存"
            >
              <p>章节规划已保存，下一次准备的 AI 任务会使用它。</p>
              <button type="button" onClick={onOpenGenerate}>
                去“生成”准备续写
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
