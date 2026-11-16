import { useEffect, useState } from "react";
import { REASON_LABELS, type SendEstimate } from "../../usage/api/budget";
import type { ModelProfile } from "../api/ai-workflow";
import {
  methodClient,
  type Annotation,
  type MethodClient,
  type Score,
  type Template,
  type Trial,
} from "../api/method-validation";
import type { ChapterPlan, RuleRevision } from "../api/writing-preparation";

const dimensions = [
  ["focus", "焦点清晰度"],
  ["continuity", "行动连续性"],
  ["subtext", "对话潜台词"],
  ["persistence", "场景停留"],
  ["originality", "原创表达"],
] as const;
type Ratings = Record<(typeof dimensions)[number][0], string>;
const emptyRatings = (): Ratings => ({
  focus: "",
  continuity: "",
  subtext: "",
  persistence: "",
  originality: "",
});
const judgments: Record<Annotation["judgment"], string> = {
  embodied: "体现方法",
  not_embodied: "没体现",
  not_applicable: "不适用",
};

export function MethodValidation({
  projectId,
  chapterId,
  manuscriptRevision,
  savedContent,
  plan,
  rules,
  profile,
  onRulesChanged,
  client = methodClient,
}: {
  readonly projectId: string;
  readonly chapterId: string;
  readonly manuscriptRevision: string;
  readonly savedContent: string;
  readonly plan: ChapterPlan | null;
  readonly rules: readonly RuleRevision[];
  readonly profile: ModelProfile | undefined;
  readonly onRulesChanged: (rule: RuleRevision) => void;
  readonly client?: MethodClient;
}) {
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [ruleId, setRuleId] = useState("");
  const [ruleIndex, setRuleIndex] = useState(0);
  const [sceneId, setSceneId] = useState("");
  const [suggested, setSuggested] = useState<readonly string[]>([]);
  const [trials, setTrials] = useState<readonly Trial[]>([]);
  const [trial, setTrial] = useState<Trial | null>(null);
  const [estimate, setEstimate] = useState<SendEstimate | null>(null);
  const [estimateError, setEstimateError] = useState(false);
  const [estimateKey, setEstimateKey] = useState(0);
  const [ack, setAck] = useState(false);
  const [cloudConsent, setCloudConsent] = useState(false);
  const [aRatings, setARatings] = useState<Ratings>(emptyRatings);
  const [bRatings, setBRatings] = useState<Ratings>(emptyRatings);
  const [aReason, setAReason] = useState("");
  const [bReason, setBReason] = useState("");
  const [selection, setSelection] = useState({ start: 0, end: 0 });
  const [judgment, setJudgment] = useState<Annotation["judgment"]>("embodied");
  const [reason, setReason] = useState("");
  const [annotations, setAnnotations] = useState<readonly Annotation[]>([]);
  const [templates, setTemplates] = useState<readonly Template[]>([]);
  const [templateName, setTemplateName] = useState("");
  const [templateMethod, setTemplateMethod] = useState("");
  const [templateApplies, setTemplateApplies] = useState("");
  const [templateExcludes, setTemplateExcludes] = useState("");
  const [templateConfirmed, setTemplateConfirmed] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const selectedRule = rules.find((rule) => rule.id === ruleId);
  const selectedMethod = selectedRule?.rules[ruleIndex];
  const trialTextTooLong =
    savedContent.length > 50_000 && Array.from(savedContent).length > 50_000;
  const chooseScene = (id: string) => {
    setSceneId(id);
    const scene = plan?.scenes.find((item) => item.id === id);
    if (!scene) {
      setSuggested([]);
      return;
    }
    const text = `${scene.title} ${scene.setting} ${scene.beats.map((beat) => `${beat.action} ${beat.change}`).join(" ")}`;
    const matches = rules
      .flatMap((revision) =>
        revision.rules.map((method, index) => ({ revision, method, index })),
      )
      .filter(({ method }) =>
        (method.scene_tags ?? []).some(
          (tag) => tag.trim() !== "" && text.includes(tag),
        ),
      )
      .sort((a, b) => (b.method.priority ?? 3) - (a.method.priority ?? 3))
      .slice(0, 3);
    setSuggested(
      matches.map(
        ({ revision, method }) => `${revision.title} · ${method.name}`,
      ),
    );
    if (!ruleId && matches[0]) {
      setRuleId(matches[0].revision.id);
      setRuleIndex(matches[0].index);
    }
  };

  useEffect(() => {
    if (!opened) return;
    let alive = true;
    Promise.all([
      client.listTrials(projectId, chapterId),
      client.annotations(projectId, chapterId),
      client.templates(projectId),
    ])
      .then(([loadedTrials, loadedAnnotations, loadedTemplates]) => {
        if (!alive) return;
        setTrials(loadedTrials);
        setAnnotations(loadedAnnotations);
        setTemplates(loadedTemplates);
      })
      .catch(() => {
        if (alive) setError("方法验证数据读取失败，请刷新。");
      });
    return () => {
      alive = false;
    };
  }, [opened, chapterId, client, projectId, refresh]);

  useEffect(() => {
    if (
      !trial ||
      !opened ||
      (trial.a.status !== "ready" && trial.b.status !== "ready")
    )
      return;
    let alive = true;
    queueMicrotask(() => {
      if (alive) {
        setEstimate(null);
        setEstimateError(false);
        setAck(false);
      }
    });
    client
      .estimate(projectId, trial.id, "A")
      .then((value) => {
        if (alive) setEstimate(value);
      })
      .catch(() => {
        if (alive) setEstimateError(true);
      });
    return () => {
      alive = false;
    };
  }, [client, projectId, trial, opened, estimateKey]);

  const action = async (work: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
    } catch {
      setError(
        "操作未完成，请检查已保存内容、预算和所选方法是否已有标注或评分后重试。",
      );
    } finally {
      setBusy(false);
    }
  };
  const reloadTrial = async () => {
    if (trial) setTrial(await client.get(projectId, trial.id));
  };
  const createTrial = () =>
    void action(async () => {
      if (!plan || !profile || !selectedMethod || !sceneId)
        throw new Error("missing selection");
      const result = await client.prepare(projectId, {
        chapter_id: chapterId,
        manuscript_revision_id: manuscriptRevision,
        plan_revision_id: plan.revision_id,
        rule_version_id: ruleId,
        rule_index: ruleIndex,
        scene_id: sceneId,
        profile_id: profile.id,
      });
      setTrial(result);
      setEstimate(null);
      setAck(false);
      setCloudConsent(false);
      setARatings(emptyRatings());
      setBRatings(emptyRatings());
      setAReason("");
      setBReason("");
      setRefresh((value) => value + 1);
      setNotice("对照已准备，尚未发送。请核对冻结内容并分别确认两个候选。");
    });
  const sendSlot = (slot: "A" | "B") =>
    void action(async () => {
      if (
        !trial ||
        !estimate ||
        estimate.decision === "refused" ||
        (estimate.decision === "warning" && !ack) ||
        (trial.model_kind === "cloud" && !cloudConsent)
      )
        throw new Error("confirmation required");
      try {
        const sent = await client.send(
          projectId,
          trial.id,
          slot,
          trial.version,
          cloudConsent,
        );
        setEstimate(null);
        setAck(false);
        setTrial(sent);
      } catch (failure) {
        await reloadTrial();
        throw failure;
      }
      setCloudConsent(false);
      setRefresh((value) => value + 1);
    });
  const validRatings = (ratings: Ratings) =>
    dimensions.every(([key]) => ratings[key] !== "");
  const makeScore = (ratings: Ratings, explanation: string): Score => ({
    focus: Number(ratings.focus),
    continuity: Number(ratings.continuity),
    subtext: Number(ratings.subtext),
    persistence: Number(ratings.persistence),
    originality: Number(ratings.originality),
    reason: explanation,
  });
  const saveRatings = () =>
    void action(async () => {
      if (!trial || !validRatings(aRatings) || !validRatings(bRatings))
        throw new Error("ratings missing");
      setTrial(
        await client.rate(
          projectId,
          trial.id,
          trial.version,
          makeScore(aRatings, aReason),
          makeScore(bRatings, bReason),
        ),
      );
      setRefresh((value) => value + 1);
      setNotice("评分已保存，这是你的本次偏好，不会采用候选。");
    });
  const saveAnnotation = () =>
    void action(async () => {
      if (!selectedMethod || selection.end <= selection.start || !reason.trim())
        throw new Error("annotation incomplete");
      await client.annotate(projectId, {
        chapter_id: chapterId,
        manuscript_revision_id: manuscriptRevision,
        rule_version_id: ruleId,
        rule_index: ruleIndex,
        ...selection,
        judgment,
        reason,
      });
      setReason("");
      setRefresh((value) => value + 1);
      setNotice("标注已保存到当前正文与规则版本。");
    });
  const saveTemplate = () =>
    void action(async () => {
      if (!selectedMethod || !templateConfirmed)
        throw new Error("confirmation required");
      await client.createTemplate(projectId, {
        source_rule_version_id: ruleId,
        source_rule_index: ruleIndex,
        name: templateName,
        instruction: templateMethod,
        applies_to: templateApplies,
        excludes: templateExcludes,
        scene_tags: selectedMethod.scene_tags ?? [],
        priority: selectedMethod.priority ?? 3,
        confirmed: true,
      });
      setTemplateName("");
      setTemplateMethod("");
      setTemplateApplies("");
      setTemplateExcludes("");
      setTemplateConfirmed(false);
      setRefresh((value) => value + 1);
      setNotice("个人模板已保存。");
    });
  const renderScores = (
    slot: "A" | "B",
    ratings: Ratings,
    setRatings: (next: Ratings) => void,
    explanation: string,
    setExplanation: (next: string) => void,
  ) => (
    <fieldset>
      <legend>候选 {slot} 的作者评分</legend>
      {dimensions.map(([key, label]) => (
        <label key={key}>
          {label}
          <select
            aria-label={`${slot} ${label}`}
            value={ratings[key]}
            onChange={(event) =>
              setRatings({ ...ratings, [key]: event.target.value })
            }
          >
            <option value="">请选择</option>
            {[1, 2, 3, 4, 5].map((value) => (
              <option value={value} key={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      ))}
      <label>
        判断说明（可选）
        <input
          maxLength={500}
          value={explanation}
          onChange={(event) => setExplanation(event.target.value)}
        />
      </label>
    </fieldset>
  );
  const canSend =
    !busy &&
    estimate !== null &&
    estimate.decision !== "refused" &&
    (estimate.decision !== "warning" || ack) &&
    (trial?.model_kind !== "cloud" || cloudConsent);

  return (
    <details onToggle={(event) => setOpened(event.currentTarget.open)}>
      <summary>写作方法验证与复用</summary>
      {opened ? (
        <section aria-label="写作方法验证">
          <p>
            选择已确认方法。手工标注不调用模型；对照试写最多两次分别确认的发送，评分只表达个人偏好，不会采用候选。
          </p>
          {error ? <p role="alert">{error}</p> : null}
          {notice ? <p role="status">{notice}</p> : null}
          <label>
            规则版本
            <select
              value={ruleId}
              onChange={(event) => {
                setRuleId(event.target.value);
                setRuleIndex(0);
              }}
            >
              <option value="">请选择</option>
              {rules.map((rule) => (
                <option key={rule.id} value={rule.id}>
                  {rule.title} · 第 {rule.version} 版
                </option>
              ))}
            </select>
          </label>
          {selectedRule ? (
            <label>
              要验证的方法
              <select
                value={ruleIndex}
                onChange={(event) => setRuleIndex(Number(event.target.value))}
              >
                {selectedRule.rules.map((rule, index) => (
                  <option key={`${rule.name}-${index}`} value={index}>
                    {rule.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {selectedMethod ? (
            <p>
              方法：{selectedMethod.instruction}；适用：
              {selectedMethod.applies_to}；不适用：
              {selectedMethod.excludes || "未填写"}；优先级：
              {selectedMethod.priority ?? 3}。
            </p>
          ) : null}
          <h4>手工标注已保存正文</h4>
          <p>在下方选中一段，再填写判断依据。修改正文后旧标注仍绑定原修订。</p>
          <textarea
            aria-label="选择已保存正文中的片段"
            readOnly
            value={savedContent}
            onSelect={(event) => {
              const field = event.currentTarget;
              setSelection({
                start: Array.from(savedContent.slice(0, field.selectionStart))
                  .length,
                end: Array.from(savedContent.slice(0, field.selectionEnd))
                  .length,
              });
            }}
          />
          <label>
            判断
            <select
              value={judgment}
              onChange={(event) =>
                setJudgment(event.target.value as Annotation["judgment"])
              }
            >
              {Object.entries(judgments).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            判断依据
            <input
              maxLength={500}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={
              busy ||
              !selectedMethod ||
              selection.start >= selection.end ||
              !reason.trim()
            }
            onClick={saveAnnotation}
          >
            保存标注
          </button>
          {annotations.length ? (
            <ul aria-label="历史方法标注">
              {annotations.map((item) => (
                <li key={item.id}>
                  {judgments[item.judgment]}：{item.reason}（正文修订{" "}
                  {item.manuscript_revision_id}，规则版本 {item.rule_version_id}
                  ）
                </li>
              ))}
            </ul>
          ) : (
            <p>暂无标注。</p>
          )}
          <h4>对照试写</h4>
          {trialTextTooLong ? (
            <p>
              已保存正文超过 5
              万字，暂不能作为一次对照试写的发送上下文；手工标注仍可用。
            </p>
          ) : null}
          {plan && plan.writing_rule_revision_ids.length > 1 ? (
            <p role="note">
              本章规划关联了多份规则。请先检查是否相互冲突，并选择本次要单独比较的方法；系统不会自动合并冲突规则。
            </p>
          ) : null}
          <label>
            已保存场景
            <select
              value={sceneId}
              onChange={(event) => chooseScene(event.target.value)}
            >
              <option value="">请选择</option>
              {plan?.scenes.map((scene) => (
                <option key={scene.id} value={scene.id}>
                  {scene.title || scene.id}
                </option>
              ))}
            </select>
          </label>
          {suggested.length ? (
            <p>
              按场景标签建议的方法：{suggested.join("、")}
              。如有冲突，请由你选择。
            </p>
          ) : null}
          <button
            type="button"
            disabled={
              busy ||
              !plan ||
              !profile ||
              !selectedMethod ||
              !sceneId ||
              trialTextTooLong
            }
            onClick={createTrial}
          >
            准备对照（不发送）
          </button>
          {trials.length ? (
            <label>
              历史对照
              <select
                value={trial?.id ?? ""}
                onChange={(event) => {
                  setTrial(
                    trials.find((item) => item.id === event.target.value) ??
                      null,
                  );
                  setEstimate(null);
                  setAck(false);
                  setCloudConsent(false);
                  setARatings(emptyRatings());
                  setBRatings(emptyRatings());
                  setAReason("");
                  setBReason("");
                }}
              >
                <option value="">请选择</option>
                {trials.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id.slice(0, 8)} ·{" "}
                    {item.complete ? "可评分" : "未完成"}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {trial ? (
            <div>
              {trial.manuscript_revision_id !== manuscriptRevision ||
              (plan !== null && trial.plan_revision_id !== plan.revision_id) ? (
                <p role="status">
                  正文或规划已变化；本次比较仍使用创建时冻结的版本。
                </p>
              ) : null}
              <details>
                <summary>核对冻结的场景、规划和正文</summary>
                <p>方法：{trial.method}</p>
                <pre
                  style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {trial.scene}
                </pre>
                <pre
                  style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {trial.plan}
                </pre>
                <pre
                  style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                >
                  {trial.manuscript}
                </pre>
              </details>
              {estimateError ? (
                <p role="alert">
                  无法读取发送前预估。
                  <button
                    type="button"
                    onClick={() => setEstimateKey((value) => value + 1)}
                  >
                    重试预估
                  </button>
                </p>
              ) : null}
              {estimate &&
              (trial.a.status === "ready" || trial.b.status === "ready") ? (
                <div>
                  <p>
                    每次发送的保守上限：输入 {estimate.input_tokens_upper}{" "}
                    token、输出 {estimate.output_tokens_upper} token；
                    {estimate.estimated_cost_upper === null
                      ? "未计价"
                      : `${estimate.estimated_cost_upper} ${estimate.currency}`}
                    。两组使用相同较高上限以保留盲评。
                  </p>
                  {estimate.decision === "refused" ? (
                    <p role="alert">
                      严格预算阻止发送：
                      {estimate.reasons
                        .map((item) => REASON_LABELS[item])
                        .join("；")}
                    </p>
                  ) : null}
                  {estimate.decision === "warning" ? (
                    <label>
                      <input
                        type="checkbox"
                        checked={ack}
                        onChange={(event) => setAck(event.target.checked)}
                      />
                      我已知晓预算提醒，仍发送一次
                    </label>
                  ) : null}
                  {trial.model_kind === "cloud" ? (
                    <label>
                      <input
                        type="checkbox"
                        checked={cloudConsent}
                        onChange={(event) =>
                          setCloudConsent(event.target.checked)
                        }
                      />
                      同意本次把冻结场景、规划和正文发送至云端模型
                    </label>
                  ) : null}
                </div>
              ) : null}
              {(["A", "B"] as const).map((slot) => {
                const candidate = slot === "A" ? trial.a : trial.b;
                return (
                  <section key={slot} aria-label={`候选 ${slot}`}>
                    <h5>候选 {slot}</h5>
                    {candidate.status === "ready" ? (
                      <button
                        type="button"
                        disabled={!canSend}
                        onClick={() => sendSlot(slot)}
                      >
                        确认发送候选 {slot}
                      </button>
                    ) : null}
                    {candidate.status === "running" ? <p>发送中…</p> : null}
                    {candidate.status === "failed" ? (
                      <p>这份候选未完成，不会自动重试。</p>
                    ) : null}
                    {candidate.text ? (
                      <pre
                        style={{
                          whiteSpace: "pre-wrap",
                          overflowWrap: "anywhere",
                        }}
                      >
                        {candidate.text}
                      </pre>
                    ) : null}
                  </section>
                );
              })}
              {trial.complete && trial.a_uses_rule === undefined ? (
                <>
                  {renderScores(
                    "A",
                    aRatings,
                    setARatings,
                    aReason,
                    setAReason,
                  )}
                  {renderScores(
                    "B",
                    bRatings,
                    setBRatings,
                    bReason,
                    setBReason,
                  )}
                  <button
                    type="button"
                    disabled={
                      busy || !validRatings(aRatings) || !validRatings(bRatings)
                    }
                    onClick={saveRatings}
                  >
                    保存评分并揭示方法
                  </button>
                </>
              ) : null}
              {trial.a_uses_rule !== undefined ? (
                <div>
                  <p>
                    本次方法用于候选 {trial.a_uses_rule ? "A" : "B"}
                    ；评分是作者偏好，不代表文学质量保证。
                  </p>
                  {(
                    [
                      ["A", trial.a_score],
                      ["B", trial.b_score],
                    ] as const
                  ).map(([slot, ratings]) =>
                    ratings ? (
                      <p key={slot}>
                        候选 {slot}：
                        {dimensions
                          .map(([key, label]) => `${label} ${ratings[key]}`)
                          .join(" · ")}{" "}
                        {ratings.reason ? `；${ratings.reason}` : ""}
                      </p>
                    ) : null,
                  )}
                </div>
              ) : null}
            </div>
          ) : null}
          <h4>个人方法模板</h4>
          <p>
            请先对所选方法完成手工标注或对照评分，再自行填写可跨书复用的方法和条件；不自动复制范文、人物或情节。
          </p>
          <label>
            模板名称
            <input
              value={templateName}
              maxLength={80}
              onChange={(event) => setTemplateName(event.target.value)}
            />
          </label>
          <label>
            可复用方法
            <textarea
              value={templateMethod}
              maxLength={1000}
              onChange={(event) => setTemplateMethod(event.target.value)}
            />
          </label>
          <label>
            模板适用条件
            <input
              value={templateApplies}
              maxLength={200}
              onChange={(event) => setTemplateApplies(event.target.value)}
            />
          </label>
          <label>
            模板不适用条件
            <input
              value={templateExcludes}
              maxLength={200}
              onChange={(event) => setTemplateExcludes(event.target.value)}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={templateConfirmed}
              onChange={(event) => setTemplateConfirmed(event.target.checked)}
            />
            我已检查模板不含来源正文、人物名及其他小说情节
          </label>
          <button
            type="button"
            disabled={
              busy ||
              !selectedMethod ||
              !templateConfirmed ||
              !templateName.trim() ||
              !templateMethod.trim() ||
              !templateApplies.trim()
            }
            onClick={saveTemplate}
          >
            保存个人模板
          </button>
          {templates.length ? (
            <ul aria-label="个人方法模板">
              {templates.map((item) => (
                <li key={item.id}>
                  {item.name}：{item.instruction}{" "}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void action(async () => {
                        const created = await client.copyTemplate(
                          projectId,
                          item.id,
                        );
                        onRulesChanged(created);
                        setNotice("已复制为本书新规则版本，不与来源自动同步。");
                      })
                    }
                  >
                    确认复制为本书新规则
                  </button>{" "}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void action(async () => {
                        await client.deleteTemplate(projectId, item.id);
                        setRefresh((value) => value + 1);
                        setNotice("模板已删除，已复制的规则仍保留。");
                      })
                    }
                  >
                    删除模板
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p>暂无个人模板。</p>
          )}
        </section>
      ) : null}
    </details>
  );
}
