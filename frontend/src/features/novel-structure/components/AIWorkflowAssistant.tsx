import { useState } from "react";
import {
  aiWorkflowClient,
  type AIWorkflowClient,
  type WorkflowRun,
} from "../api/ai-workflow";
import { useAIWorkflow } from "../hooks/useAIWorkflow";
import type { SelectionSnapshot } from "../hooks/useAIWriting";
import type { useChapterWriting } from "../hooks/useChapterWriting";
import { AIModelSettings } from "./AIModelSettings";

const STATUS: Record<WorkflowRun["status"], string> = {
  ready: "可以生成下一段",
  generating: "正在生成",
  paused: "已暂停",
  interrupted: "上次生成中断，请确认后恢复",
  completed: "本轮已完成",
};
const SOURCE_LABELS: Record<string, string> = {
  current_chapter: "当前章节",
  outline: "小说大纲",
  story_bible: "小说设定",
  volume: "当前卷",
  previous_chapter: "前一章",
  characters: "人物",
  project: "小说简介",
};

export function AIWorkflowAssistant({
  chapterId,
  writing,
  selection,
  client = aiWorkflowClient,
}: {
  readonly chapterId: string;
  readonly writing: ReturnType<typeof useChapterWriting>;
  readonly selection: SelectionSnapshot | null;
  readonly client?: AIWorkflowClient;
}) {
  const ai = useAIWorkflow(chapterId, writing, client);
  const [profileId, setProfileId] = useState("");
  const [instruction, setInstruction] = useState("");
  const [steps, setSteps] = useState("5");
  const [confirmedRunId, setConfirmedRunId] = useState<string | null>(null);
  const [formError, setFormError] = useState("");
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
  const unavailable =
    ai.busy ||
    ai.loading ||
    ai.upgradeRequired ||
    writing.state.reloading ||
    writing.state.reloadFailed;
  const prepare = (operation: "continue" | "rewrite") => {
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
  const canSend =
    runProfile?.kind !== "cloud" || confirmedRunId === run?.run_id;
  return (
    <section
      aria-label="AI写作助手"
      className="ai-writing-assistant"
      data-feature-id="ai.workflow"
    >
      <h3>AI协作写作</h3>
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
      {ai.error || formError ? (
        <p role="alert">{ai.error || formError}</p>
      ) : null}
      <AIModelSettings
        models={ai.models}
        disabled={ai.busy || ai.upgradeRequired}
        onUpgradeRequired={ai.modelError}
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
        {ai.models.length === 0 ? <option value="">请先添加模型</option> : null}
        {ai.models.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name} · {item.kind === "cloud" ? "云端" : "本地"}
          </option>
        ))}
      </select>
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
        type="button"
        disabled={unavailable || !profile}
        onClick={() => prepare("continue")}
      >
        续写
      </button>
      <button
        type="button"
        disabled={unavailable || !profile || !selection?.text.trim()}
        onClick={() => prepare("rewrite")}
      >
        改写选中文本
      </button>
      <p>
        先准备上下文，再确认生成。每次采纳后可选择继续下一段，达到本轮上限即停止。
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
                {index + 1}. {item.operation === "continue" ? "续写" : "改写"} ·{" "}
                {STATUS[item.status]} · {item.generated_steps}/{item.max_steps}{" "}
                段
              </option>
            ))}
          </select>
        </>
      ) : null}
      {run ? (
        <section aria-label="当前AI任务">
          <p role="status">
            {STATUS[run.status]} · 已生成 {run.generated_steps}/{run.max_steps}{" "}
            段，{run.generated_characters}/{run.max_output_characters} 字
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
                。服务商可能计费；本应用限制段数和输出量，不在未知费率时估算金额。
              </p>
              <label>
                <input
                  type="checkbox"
                  checked={confirmedRunId === run.run_id}
                  onChange={(event) =>
                    setConfirmedRunId(event.target.checked ? run.run_id : null)
                  }
                />
                我同意本轮任务向该模型发送上述内容
              </label>
            </div>
          ) : null}
          {run.last_error ? (
            <p role="alert">
              上一步未完成：{run.last_error}。未自动重新调用模型。
            </p>
          ) : null}
          {ai.busy ? (
            <p role="status">正在处理，请稍候。可以暂停后续生成。</p>
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
              <button
                type="button"
                disabled={unavailable || writing.state.status !== "saved"}
                onClick={() => void ai.adopt(pending, false)}
              >
                {run.operation === "continue" ? "追加到正文" : "替换选中文本"}
              </button>
              {run.operation === "continue" &&
              run.generated_steps < run.max_steps &&
              run.status !== "paused" ? (
                <button
                  type="button"
                  disabled={
                    unavailable || writing.state.status !== "saved" || !canSend
                  }
                  onClick={() => void ai.adopt(pending, true)}
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
                      {item.status === "adopted" ? "已采纳" : "已丢弃"}
                      <pre>{item.text}</pre>
                    </li>
                  ))}
              </ol>
            </details>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
