import { ExternalHandoff } from "../../external-handoff/ExternalHandoff";
import { writingJobsClient, type WritingJob } from "../../writing-jobs/client";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import {
  aiWorkflowClient,
  workflowFailureMessage,
  type AIWorkflowClient,
  type WorkflowRun,
} from "../api/ai-workflow";
import { useAIWorkflow } from "../hooks/useAIWorkflow";
import type { SelectionSnapshot } from "../hooks/useAIWriting";
import type { useChapterWriting } from "../hooks/useChapterWriting";
import {
  usageClient as defaultUsageClient,
  type UsageClient,
} from "../../usage/api/usage";
import {
  budgetClient as defaultBudgetClient,
  type BudgetClient,
} from "../../usage/api/budget";
import { BudgetSettingsPanel } from "../../usage/components/BudgetSettingsPanel";
import { ModelUsagePanel } from "../../usage/components/ModelUsagePanel";
import { SendEstimatePanel } from "../../usage/components/SendEstimatePanel";
import { AIModelSettings } from "./AIModelSettings";
import { CandidateComparison } from "./CandidateComparison";
import { editIsCurrent } from "../candidate-edit";
import { CandidateEditor } from "./CandidateEditor";
import { ReferenceWritingWorkbench } from "./ReferenceWritingWorkbench";
import { StoryMemoryWorkbench } from "./StoryMemoryWorkbench";
import {
  ChapterGuideCard,
  RecallControl,
} from "../../story-control/components/ChapterStoryControl";
import type { StoryControlClient } from "../../story-control/api/storyControl";

const STATUS: Record<WorkflowRun["status"], string> = {
  ready: "可以生成下一段",
  generating: "正在生成",
  paused: "已暂停",
  interrupted: "上次生成中断，请确认后恢复",
  completed: "本轮已完成",
};
type AssistantTab = "prepare" | "generate" | "review";
const TABS: readonly { readonly id: AssistantTab; readonly label: string }[] = [
  { id: "prepare", label: "准备" },
  { id: "generate", label: "生成" },
  { id: "review", label: "评审" },
];
const SOURCE_LABELS: Record<string, string> = {
  current_chapter: "当前章节",
  outline: "小说大纲",
  story_bible: "小说设定",
  volume: "当前卷",
  previous_chapter: "前一章",
  characters: "人物",
  project: "小说简介",
  chapter_plan: "章节规划",
  planning_assets: "规划关联人物与设定",
  writing_rules: "已确认的写作规则",
  story_memory: "已确认的前文事实",
  story_guide: "全书/卷目标与伏笔计划（计划，非已发生事实）",
};

export function AIWorkflowAssistant({
  chapterId,
  jobId,
  writing,
  selection,
  onTaskStatus,
  client = aiWorkflowClient,
  projectId,
  usageClient = defaultUsageClient,
  budgetClient = defaultBudgetClient,
  storyControlClient,
}: {
  readonly chapterId: string;
  readonly jobId?: string;
  /** 用于读取本章模型用量；缺省时不显示用量面板。 */
  readonly projectId?: string;
  readonly usageClient?: UsageClient;
  readonly budgetClient?: BudgetClient;
  readonly storyControlClient?: StoryControlClient;
  readonly writing: ReturnType<typeof useChapterWriting>;
  readonly selection: SelectionSnapshot | null;
  /** 把当前任务的真实状态同步到写作页固定状态区。 */
  readonly onTaskStatus?: (label: string) => void;
  readonly client?: AIWorkflowClient;
}) {
  const ai = useAIWorkflow(chapterId, writing, client);
  const [profileId, setProfileId] = useState("");
  const [instruction, setInstruction] = useState("");
  const [steps, setSteps] = useState("5");
  const [confirmedRunId, setConfirmedRunId] = useState<string | null>(null);
  const [formError, setFormError] = useState("");
  const [preparationMounted, setPreparationMounted] = useState(false);
  const [planningDirty, setPlanningDirty] = useState(false);
  const [memoryMounted, setMemoryMounted] = useState(false);
  const [storyControlOpen, setStoryControlOpen] = useState(false);
  const [tab, setTab] = useState<AssistantTab>("generate");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsFocus, setSettingsFocus] = useState(0);
  const [editorDirty, setEditorDirty] = useState(false);
  const [budgetGate, setBudgetGate] = useState({ allowed: true, reason: "" });
  const [jobState, setJobState] = useState<{
    readonly id: string;
    readonly job: WritingJob | null;
    readonly error: string;
  } | null>(null);
  const [jobBusy, setJobBusy] = useState(false);
  const [jobRefresh, setJobRefresh] = useState(0);
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    void writingJobsClient
      .get(jobId)
      .then((job) => {
        if (!cancelled) setJobState({ id: jobId, job, error: "" });
      })
      .catch(() => {
        if (!cancelled)
          setJobState({
            id: jobId,
            job: null,
            error: "跨章任务读取失败，请刷新后再发送。",
          });
      });
    return () => {
      cancelled = true;
    };
  }, [
    jobId,
    jobRefresh,
    ai.active?.run_id,
    ai.active?.generated_steps,
    ai.active?.candidates.length,
    ai.generating,
  ]);
  const job = jobState?.id === jobId ? (jobState?.job ?? null) : null;
  const jobMatches =
    !!job &&
    job.project_id === projectId &&
    job.status === "planned" &&
    job.steps[job.current_index]?.chapter_id === chapterId;
  const jobBound =
    !!jobMatches && !!ai.active && job?.active_run_id === ai.active.run_id;
  const jobQuotaAvailable =
    !!job &&
    job.claimed_requests < job.max_requests &&
    job.used_characters < job.max_output_characters;
  const jobCanSend = !jobId || (jobBound && jobQuotaAvailable);
  const bindRun = async () => {
    if (!job || !jobId || !ai.active || jobBusy) return;
    setJobBusy(true);
    try {
      const result = await writingJobsClient.bind(
        jobId,
        ai.active.run_id,
        job.version,
      );
      setJobState({ id: jobId, job: result, error: "" });
    } catch {
      setJobState({
        id: jobId,
        job: null,
        error: "关联任务失败，状态可能已变化；请刷新后重试。",
      });
    } finally {
      setJobBusy(false);
    }
  };
  const onBudgetGate = useCallback((allowed: boolean, reason: string) => {
    setBudgetGate((current) =>
      current.allowed === allowed && current.reason === reason
        ? current
        : { allowed, reason },
    );
  }, []);
  const tabRefs = useRef<Record<AssistantTab, HTMLButtonElement | null>>({
    prepare: null,
    generate: null,
    review: null,
  });
  const continueButton = useRef<HTMLButtonElement>(null);
  const [focusContinue, setFocusContinue] = useState(false);
  useEffect(() => {
    if (!focusContinue || tab !== "generate") return;
    continueButton.current?.focus();
    queueMicrotask(() => setFocusContinue(false));
  }, [focusContinue, tab]);
  const selectTab = (next: AssistantTab, focus = false) => {
    if (next === "prepare") setPreparationMounted(true);
    if (next === "review") setMemoryMounted(true);
    setTab(next);
    if (focus) tabRefs.current[next]?.focus();
  };
  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    const index = TABS.findIndex((item) => item.id === tab);
    const target =
      event.key === "ArrowRight"
        ? TABS[(index + 1) % TABS.length]
        : event.key === "ArrowLeft"
          ? TABS[(index + TABS.length - 1) % TABS.length]
          : event.key === "Home"
            ? TABS[0]
            : event.key === "End"
              ? TABS[TABS.length - 1]
              : undefined;
    if (!target) return;
    event.preventDefault();
    selectTab(target.id, true);
  };
  const profile = ai.models.find(
    (item) => item.id === (profileId || ai.models[0]?.id),
  );
  const runProfile =
    ai.active?.model_snapshot ??
    ai.models.find(
      (item) => item.id === (ai.active?.profile_id ?? "default-local"),
    );
  const run = ai.active;
  const pending = run?.candidates.find((item) => item.status === "pending");
  const taskLabel = !run
    ? ai.loading
      ? "正在读取 AI 任务…"
      : "没有进行中的 AI 任务"
    : ai.generating
      ? "AI 正在生成：已发送请求，等待模型回复"
      : pending
        ? `AI 候选待你确认 · 第 ${pending.sequence} 段`
        : `AI 任务：${STATUS[run.status]}`;
  useEffect(() => {
    onTaskStatus?.(taskLabel);
  }, [onTaskStatus, taskLabel]);
  // A finished or failed send changes the ledger; an open usage panel re-reads it.
  const usageRefresh = `${run?.run_id ?? ""}:${run?.generated_steps ?? 0}:${
    run?.last_error ?? ""
  }:${ai.generating ? 1 : 0}`;
  const unavailable =
    ai.busy ||
    ai.loading ||
    ai.upgradeRequired ||
    writing.state.reloading ||
    writing.state.reloadFailed;
  const prepare = (operation: "continue" | "rewrite") => {
    if (planningDirty) {
      setFormError("章节规划尚未保存，请保存规划后再准备 AI 任务。");
      return;
    }
    const limit = Number(steps);
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 10) {
      setFormError("本轮段数须为 1–10。");
      return;
    }
    setFormError("");
    setConfirmedRunId(null);
    void ai.prepare(
      operation,
      profile?.id ?? "",
      instruction,
      limit,
      selection,
    );
  };
  const consented =
    runProfile?.kind !== "cloud" || confirmedRunId === run?.run_id;
  const canSend = consented && budgetGate.allowed && jobCanSend;
  const taskError = ai.errorRunId === run?.run_id ? ai.error : "";
  const sendBlockedReason =
    jobId && !jobCanSend
      ? "请先为本章准备并关联任务，且确认跨章额度尚有余量。"
      : writing.state.reloadFailed
        ? "正文读取失败，请先重新加载服务器正文，再继续生成。"
        : writing.state.reloading
          ? "正在读取最新正文，请稍候。"
          : !runProfile
            ? "原模型配置不可用，请选择可用模型并重新准备任务。"
            : !consented
              ? "请先勾选上面的发送同意，再确认生成。"
              : !budgetGate.allowed
                ? budgetGate.reason
                : "";
  const kindLabel = (item: {
    readonly kind: string;
    readonly has_key: boolean;
  }) =>
    item.kind === "cloud"
      ? item.has_key
        ? "云端 · 已保存密钥"
        : "云端 · 未保存密钥，发送前需补充 API Key"
      : "本机模型";
  const openSettings = () => {
    setSettingsOpen(true);
    setSettingsFocus((value) => value + 1);
  };
  return (
    <section
      aria-label="AI写作助手"
      className="ai-writing-assistant"
      data-feature-id="ai.workflow"
    >
      <h3>AI协作写作</h3>
      <ExternalHandoff chapterId={chapterId} writing={writing} />
      {ai.upgradeRequired ? (
        <section aria-label="启用 AI 协作">
          <p>
            当前数据库需要升级。将先在本机保存数据库备份，再添加 AI
            协作表，保留正文和历史版本。手动写作仍可使用。
          </p>
          <button
            type="button"
            disabled={
              ai.busy ||
              ai.loading ||
              writing.state.reloading ||
              writing.state.reloadFailed
            }
            onClick={() => void ai.upgrade()}
          >
            {ai.upgrading ? "正在备份并启用…" : "备份并启用 AI 协作"}
          </button>
        </section>
      ) : null}
      {ai.upgradeMessage ? <p role="status">{ai.upgradeMessage}</p> : null}
      <p>
        每次生成 200–300
        字，先保留为候选，由你确认后写入正文。任务和候选会保存在本机，可关闭后继续。
      </p>
      {(ai.error && !taskError) || formError ? (
        <p role="alert">{formError || ai.error}</p>
      ) : null}
      {planningDirty ? (
        <p role="status">章节规划有未保存修改；保存后再准备新任务。</p>
      ) : null}
      <div
        className="ai-assistant-tabs"
        role="tablist"
        aria-label="AI 助手分区"
      >
        {TABS.map((item) => (
          <button
            key={item.id}
            ref={(node) => {
              tabRefs.current[item.id] = node;
            }}
            type="button"
            role="tab"
            id={`ai-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`ai-panel-${item.id}`}
            tabIndex={tab === item.id ? 0 : -1}
            onClick={() => selectTab(item.id)}
            onKeyDown={onTabKey}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="ai-panel-prepare"
        aria-labelledby="ai-tab-prepare"
        hidden={tab !== "prepare"}
      >
        {ai.upgradeRequired ? (
          <p>启用 AI 协作后可使用范文分析与章节规划；手动写作不受影响。</p>
        ) : preparationMounted ? (
          <>
            <details
              className="story-control-desk"
              onToggle={(event) => {
                if (event.currentTarget.open) setStoryControlOpen(true);
              }}
            >
              <summary>
                本章任务与本次依据（全书/卷目标、伏笔、可固定或排除的前文事实）
              </summary>
              {storyControlOpen ? (
                <>
                  <ChapterGuideCard
                    projectId={writing.state.snapshot.resource.project_id}
                    chapterId={chapterId}
                    sourceRevision={
                      writing.state.snapshot.resource.current_revision_id
                    }
                    client={storyControlClient}
                  />
                  <RecallControl
                    projectId={writing.state.snapshot.resource.project_id}
                    chapterId={chapterId}
                    sourceRevision={
                      writing.state.snapshot.resource.current_revision_id
                    }
                    lastRecall={
                      run
                        ? run.context.manifest.sources
                            .filter(
                              (source) => source.source === "story_memory",
                            )
                            .flatMap((source) =>
                              source.references.map(
                                (reference) => reference[0],
                              ),
                            )
                        : undefined
                    }
                    client={storyControlClient}
                  />
                </>
              ) : null}
            </details>
            <ReferenceWritingWorkbench
              projectId={writing.state.snapshot.resource.project_id}
              chapterId={chapterId}
              profile={profile}
              content={writing.state.content}
              onDirty={setPlanningDirty}
              onOpenGenerate={() => {
                setTab("generate");
                setFocusContinue(true);
              }}
            />
          </>
        ) : null}
      </div>
      <div
        role="tabpanel"
        id="ai-panel-review"
        aria-labelledby="ai-tab-review"
        hidden={tab !== "review"}
      >
        {ai.upgradeRequired ? (
          <p>启用 AI 协作后可使用长篇记忆与评审；手动写作不受影响。</p>
        ) : memoryMounted ? (
          <StoryMemoryWorkbench
            projectId={writing.state.snapshot.resource.project_id}
            chapterId={chapterId}
            sourceRevision={writing.state.snapshot.resource.current_revision_id}
            profile={profile}
            disabled={
              unavailable || planningDirty || writing.state.status !== "saved"
            }
            onRewrite={(quote, requirement, revision) => {
              const content = writing.getContent(),
                start = content.indexOf(quote);
              if (
                writing.state.status !== "saved" ||
                revision !==
                  writing.state.snapshot.resource.current_revision_id ||
                start < 0 ||
                content.indexOf(quote, start + 1) >= 0
              ) {
                setFormError(
                  "评审引文已改变或出现多次，请重新评审，或手动选择要改写的正文。",
                );
                return;
              }
              setFormError("");
              setInstruction(requirement);
              setConfirmedRunId(null);
              setTab("generate");
              void ai.prepare("rewrite", profile?.id ?? "", requirement, 1, {
                start,
                end: start + quote.length,
                text: quote,
              });
            }}
          />
        ) : null}
      </div>
      <div
        role="tabpanel"
        id="ai-panel-generate"
        aria-labelledby="ai-tab-generate"
        hidden={tab !== "generate"}
      >
        <section className="ai-model-summary" aria-label="当前模型">
          {ai.models.length === 0 ? (
            <>
              <p>
                {ai.loading
                  ? "正在读取模型配置…"
                  : "当前没有模型。手动写作可继续；添加模型后即可准备 AI 任务。"}
              </p>
              <button
                type="button"
                disabled={ai.busy || ai.loading || ai.upgradeRequired}
                onClick={openSettings}
              >
                添加模型
              </button>
            </>
          ) : (
            <>
              <p>
                当前模型：{profile?.name} · {profile ? kindLabel(profile) : ""}
                。 配置已保存；本应用尚未检查服务连接。
              </p>
              <button
                type="button"
                disabled={ai.busy || ai.upgradeRequired}
                onClick={() => setSettingsOpen((value) => !value)}
              >
                {settingsOpen ? "收起模型管理" : "管理模型"}
              </button>
            </>
          )}
        </section>
        <AIModelSettings
          projectId={writing.state.snapshot.resource.project_id}
          models={ai.models}
          disabled={ai.busy || ai.upgradeRequired}
          onUpgradeRequired={ai.modelError}
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
          focusRequest={settingsFocus}
          onSaved={(saved) => {
            ai.modelSaved(saved);
            setProfileId(saved.id);
          }}
          client={client}
        />
        <label htmlFor="ai-profile">使用模型</label>
        <select
          id="ai-profile"
          value={profile?.id ?? ""}
          disabled={unavailable}
          onChange={(event) => setProfileId(event.target.value)}
        >
          {ai.models.length === 0 ? (
            <option value="">请先添加模型</option>
          ) : null}
          {ai.models.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · {item.kind === "cloud" ? "云端" : "本地"}
            </option>
          ))}
        </select>
        {run &&
        profile &&
        (run.profile_id ?? "default-local") !== profile.id ? (
          <p>
            当前任务使用准备时冻结的模型“{runProfile?.name ?? "原模型配置"}
            ”；切换模型只影响下一次新准备的任务。
          </p>
        ) : null}
        <label htmlFor="ai-instruction">额外要求（可选）</label>
        <textarea
          id="ai-instruction"
          rows={2}
          maxLength={4000}
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
        />
        <label htmlFor="ai-step-limit">本轮最多生成段数</label>
        <input
          id="ai-step-limit"
          inputMode="numeric"
          value={steps}
          onChange={(event) => setSteps(event.target.value)}
        />
        <button
          ref={continueButton}
          type="button"
          disabled={unavailable || !profile || planningDirty}
          onClick={() => prepare("continue")}
        >
          准备续写
        </button>
        <button
          type="button"
          disabled={
            unavailable || !profile || planningDirty || !selection?.text.trim()
          }
          onClick={() => prepare("rewrite")}
        >
          准备改写选中文本
        </button>
        {!profile && !ai.loading ? (
          <p>添加并选择模型后才能准备 AI 任务。</p>
        ) : null}
        <p>
          准备只保存正文并冻结上下文，不调用模型；确认发送后才会生成。每次采纳后可选择继续下一段，达到本轮上限即停止。
        </p>
        {ai.loading ? <p role="status">正在读取模型与已保存任务…</p> : null}
        <button
          type="button"
          disabled={ai.busy}
          onClick={() => void ai.refresh()}
        >
          刷新协作任务
        </button>
        {ai.runs.length ? (
          <>
            <label htmlFor="ai-saved-runs">已保存的任务</label>
            <select
              id="ai-saved-runs"
              value={run?.run_id ?? ""}
              disabled={unavailable}
              onChange={(event) => {
                setConfirmedRunId(null);
                ai.select(event.target.value);
              }}
            >
              {ai.runs.map((item, index) => (
                <option key={item.run_id} value={item.run_id}>
                  {index + 1}. {item.operation === "continue" ? "续写" : "改写"}{" "}
                  · {STATUS[item.status]} · {item.generated_steps}/
                  {item.max_steps} 段
                </option>
              ))}
            </select>
          </>
        ) : null}
        {run ? (
          <section aria-label="当前AI任务">
            <p role="status">
              {STATUS[run.status]} · 已生成 {run.generated_steps}/
              {run.max_steps} 段，{run.generated_characters}/
              {run.max_output_characters} 字
            </p>
            <p>
              模型：{runProfile?.name ?? "原模型配置不可用"}；每次输出最多{" "}
              {runProfile?.max_output_tokens ?? "—"} Token。字数按非空白 Unicode
              字符计算。
            </p>
            <details>
              <summary>查看本次上下文依据与发送内容</summary>
              <p>
                采用：
                {run.context.manifest.included_sources
                  .map((source) => SOURCE_LABELS[source] ?? source)
                  .join("、")}
                。
              </p>
              <p>
                未纳入：
                {run.context.manifest.omitted_sources
                  .map((source) => SOURCE_LABELS[source] ?? source)
                  .join("、") || "无"}
                。
                {run.context.manifest.truncated
                  ? "超出预算的内容已截取，以下为实际发送片段。"
                  : "上下文未截断。"}
              </p>
              <textarea
                aria-label="本次发送的小说上下文"
                readOnly
                rows={8}
                value={run.context.text}
              />
              <p>额外要求：{run.instruction || "无"}</p>
              {run.operation === "rewrite" ? (
                <>
                  <p>本次待改写选区（任务准备时保存的原文）：</p>
                  <textarea
                    aria-label="本次发送的改写选区"
                    readOnly
                    rows={4}
                    value={run.selected_text}
                  />
                </>
              ) : null}
              {run.candidates.some(
                (candidate) => candidate.status !== "discarded",
              ) ? (
                <>
                  <p>
                    继续生成时还会发送本轮已采纳的段落；选择“采纳并生成下一段”时，也会发送当前待采纳的候选。丢弃的候选不会发送。
                  </p>
                  <textarea
                    aria-label="下一段随上下文发送的本轮候选"
                    readOnly
                    rows={5}
                    value={run.candidates
                      .filter((candidate) => candidate.status !== "discarded")
                      .map((candidate) => candidate.text)
                      .join("\n\n")}
                  />
                </>
              ) : null}
              <details>
                <summary>查看各项来源与取舍原因</summary>
                <ol>
                  {run.context.manifest.sources.map((source, index) => (
                    <li key={`${source.source}-${index}`}>
                      <p>
                        {SOURCE_LABELS[source.source] ?? source.source}：
                        {source.omitted_reason
                          ? `未纳入，${source.omitted_reason}`
                          : source.reason}
                        {source.truncated ? "（已截取）" : ""}
                      </p>
                      {source.references.length ? (
                        <p>
                          已固定 {source.references.length}{" "}
                          项来源快照，后续编辑不会改变本次发送内容。
                        </p>
                      ) : null}
                      {source.omitted_reason === null ? (
                        <pre>{source.text}</pre>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </details>
            </details>
            {runProfile?.kind === "cloud" ? (
              <div>
                <p>
                  将把上面的小说片段、选区、额外要求及本轮已采纳段落发送至{" "}
                  {runProfile.base_url}
                  。服务商可能计费；本应用限制段数和输出量，只按你填写的价格估算金额上限。
                </p>
                <label>
                  <input
                    type="checkbox"
                    checked={confirmedRunId === run.run_id}
                    onChange={(event) =>
                      setConfirmedRunId(
                        event.target.checked ? run.run_id : null,
                      )
                    }
                  />
                  我同意本轮任务向该模型发送上述内容
                </label>
              </div>
            ) : null}
            {taskError || run.last_error ? (
              <p role="alert">
                {taskError || workflowFailureMessage(run.last_error!)}
              </p>
            ) : null}
            {run.status === "ready" && !pending ? (
              <SendEstimatePanel
                key={`${run.run_id}:${run.generated_steps}:${run.candidates.length}:${run.last_error ?? ""}`}
                chapterId={chapterId}
                runId={run.run_id}
                refreshKey={`${run.generated_steps}:${run.candidates.length}:${run.last_error ?? ""}`}
                onGate={onBudgetGate}
                client={budgetClient}
              />
            ) : null}
            {jobId ? (
              <div className="writing-job-binding" aria-label="跨章任务额度">
                {job ? (
                  <>
                    <p>
                      跨章任务：{job.title} · 已发送 {job.claimed_requests}/
                      {job.max_requests} 次 · 已用或保留 {job.used_characters}/
                      {job.max_output_characters} 字
                    </p>
                    <p>
                      {jobBound
                        ? "本次任务已关联；每次发送仍需确认。"
                        : "先准备本章任务并关联到跨章任务，再确认发送。"}
                    </p>
                    {!jobMatches ? (
                      <p>
                        任务已暂停、结束或当前章节已变化，请返回小说结构查看。
                      </p>
                    ) : null}
                    {jobMatches &&
                    !jobBound &&
                    !job.active_run_id &&
                    run.status === "ready" &&
                    run.generated_steps === 0 &&
                    run.candidates.length === 0 ? (
                      <button
                        type="button"
                        disabled={jobBusy || unavailable}
                        onClick={() => void bindRun()}
                      >
                        关联本次任务
                      </button>
                    ) : null}
                  </>
                ) : (
                  <p>{jobState?.error || "正在读取跨章任务…"}</p>
                )}
                {jobState?.error ? (
                  <button
                    type="button"
                    onClick={() => setJobRefresh((value) => value + 1)}
                  >
                    刷新跨章任务
                  </button>
                ) : null}
              </div>
            ) : null}
            {sendBlockedReason ? <p>{sendBlockedReason}</p> : null}
            {ai.busy ? (
              <p role="status">
                {ai.generating
                  ? "正在发送请求并等待模型回复，请勿重复点击。可以暂停后续生成。"
                  : "正在处理，请稍候。可以暂停后续生成。"}
              </p>
            ) : null}
            {run.status === "ready" && !pending ? (
              <button
                type="button"
                disabled={unavailable || !canSend || !runProfile}
                onClick={() => void ai.generate()}
              >
                确认发送并生成
              </button>
            ) : null}
            {run.status !== "completed" && run.status !== "paused" ? (
              <button type="button" onClick={() => void ai.pause()}>
                暂停任务
              </button>
            ) : null}
            {run.status === "paused" || run.status === "interrupted" ? (
              <button
                type="button"
                disabled={unavailable}
                onClick={() => void ai.resume()}
              >
                恢复任务
              </button>
            ) : null}
            {pending ? (
              <section aria-label="AI候选">
                <h4>待确认候选 · 第 {pending.sequence} 段</h4>
                <textarea
                  aria-label="AI候选文本"
                  readOnly
                  rows={8}
                  value={pending.text}
                />
                <p>
                  模型：{pending.model} · {pending.character_count} 字
                </p>
                <CandidateComparison
                  operation={run.operation}
                  original={run.selected_text}
                  candidate={pending.latest_edit?.text ?? pending.text}
                  currentContent={writing.state.content}
                />
                <CandidateEditor
                  key={pending.candidate_id}
                  candidate={pending}
                  savedRevisionId={
                    writing.state.snapshot.resource.current_revision_id
                  }
                  disabled={unavailable}
                  onSave={(text) => ai.saveEdit(pending, text)}
                  onDirtyChange={setEditorDirty}
                />
                {pending.latest_edit ? (
                  <>
                    <button
                      type="button"
                      disabled={
                        unavailable ||
                        editorDirty ||
                        writing.state.status !== "saved" ||
                        !editIsCurrent(
                          pending,
                          writing.state.snapshot.resource.current_revision_id,
                        )
                      }
                      onClick={() =>
                        void ai.adopt(
                          pending,
                          false,
                          pending.latest_edit?.edit_id ?? null,
                        )
                      }
                    >
                      {run.operation === "continue"
                        ? "追加修改后的文本"
                        : "用修改后的文本替换选区"}
                    </button>
                    <button
                      type="button"
                      disabled={
                        unavailable ||
                        editorDirty ||
                        writing.state.status !== "saved"
                      }
                      onClick={() => void ai.adopt(pending, false)}
                    >
                      改为采用原始候选
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    disabled={
                      unavailable ||
                      editorDirty ||
                      writing.state.status !== "saved"
                    }
                    onClick={() => void ai.adopt(pending, false)}
                  >
                    {run.operation === "continue"
                      ? "追加到正文"
                      : "替换选中文本"}
                  </button>
                )}
                {!jobId &&
                run.operation === "continue" &&
                run.generated_steps < run.max_steps &&
                run.status !== "paused" ? (
                  <button
                    type="button"
                    disabled={
                      unavailable ||
                      editorDirty ||
                      writing.state.status !== "saved" ||
                      !consented ||
                      (pending.latest_edit !== null &&
                        !editIsCurrent(
                          pending,
                          writing.state.snapshot.resource.current_revision_id,
                        ))
                    }
                    onClick={() =>
                      void ai.adopt(
                        pending,
                        true,
                        pending.latest_edit?.edit_id ?? null,
                      )
                    }
                  >
                    采纳并生成下一段
                  </button>
                ) : null}
                <button
                  type="button"
                  disabled={unavailable}
                  onClick={() => void ai.discard(pending)}
                >
                  丢弃
                </button>
              </section>
            ) : null}
            {run.candidates.some((item) => item.status !== "pending") ? (
              <details>
                <summary>查看已处理候选</summary>
                <ol>
                  {run.candidates
                    .filter((item) => item.status !== "pending")
                    .map((item) => (
                      <li key={item.candidate_id}>
                        第 {item.sequence} 段 ·{" "}
                        {item.status === "adopted"
                          ? item.adopted_edit_id
                            ? "已采纳（采用作者修改版本）"
                            : "已采纳"
                          : "已丢弃"}
                        <pre>{item.text}</pre>
                      </li>
                    ))}
                </ol>
              </details>
            ) : null}
          </section>
        ) : null}
        {projectId ? (
          <ModelUsagePanel
            projectId={projectId}
            chapterId={chapterId}
            title="本章模型用量"
            refreshKey={usageRefresh}
            client={usageClient}
          />
        ) : null}
        {projectId ? (
          <BudgetSettingsPanel
            projectId={projectId}
            profileId={profile?.id ?? null}
            profileName={profile?.name ?? ""}
            client={budgetClient}
          />
        ) : null}
      </div>
    </section>
  );
}
