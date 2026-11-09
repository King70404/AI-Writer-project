import { useCallback, useEffect, useRef, useState } from "react";
import { analysisEstimateClient } from "../../usage/api/budget";
import { OperationSendGuard } from "../../usage/components/SendEstimatePanel";
import { Link } from "react-router";
import type { ModelProfile } from "../api/ai-workflow";
import {
  storyMemoryClient,
  memoryError,
  type FactInput,
  type MemoryFact,
  type MemoryReview,
  type MemoryWorkspace,
  type StoryMemoryClient,
  type SuggestedFact,
} from "../api/story-memory";

const FACT_STATUS = {
  pending: "待确认",
  confirmed: "已确认",
  rejected: "已驳回",
};
export function StoryMemoryWorkbench({
  projectId,
  chapterId,
  sourceRevision,
  profile,
  disabled,
  onRewrite,
  client = storyMemoryClient,
}: {
  readonly projectId: string;
  readonly chapterId: string;
  readonly sourceRevision: string;
  readonly profile: ModelProfile | undefined;
  readonly disabled: boolean;
  readonly onRewrite: (
    quote: string,
    instruction: string,
    revision: string,
  ) => void;
  readonly client?: StoryMemoryClient;
}) {
  const [workspace, setWorkspace] = useState<MemoryWorkspace | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [draft, setDraft] = useState<SuggestedFact>({
    title: "",
    text: "",
    quote: "",
  });
  const [editing, setEditing] = useState<MemoryFact | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [consentId, setConsentId] = useState("");
  const lock = useRef(false);
  const alive = useRef(false);
  const blocked =
    disabled || busy || workspace?.source_revision !== sourceRevision;
  const selected =
    workspace?.reviews.find((item) => item.id === selectedId) ??
    workspace?.reviews[0];
  const loadEstimate = useCallback(
    () => analysisEstimateClient.review(chapterId, selected?.id ?? ""),
    [chapterId, selected?.id],
  );
  useEffect(() => {
    alive.current = true;
    void client
      .workspace(projectId, chapterId)
      .then((value) => {
        if (alive.current) setWorkspace(value);
      })
      .catch((failure) => {
        if (alive.current) setError(memoryError(failure).message);
      });
    return () => {
      alive.current = false;
    };
  }, [chapterId, projectId, client]);
  const action = async (run: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await run();
    } catch (failure) {
      if (alive.current) setError(memoryError(failure).message);
    } finally {
      // A read reconciles a lost response without resending the model request.
      try {
        const value = await client.workspace(projectId, chapterId);
        if (alive.current) setWorkspace(value);
      } catch (failure) {
        if (alive.current)
          setError((previous) => previous || memoryError(failure).message);
      }
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  };
  const save = async (status: FactInput["status"], fact = editing) => {
    const input = fact && fact !== editing ? fact : draft;
    await client.fact(
      projectId,
      chapterId,
      {
        title: input.title,
        text: input.text,
        quote: input.quote,
        status,
        source_revision:
          status === "rejected" && fact ? fact.source_revision : sourceRevision,
        expected_version: fact?.version ?? 0,
      },
      fact?.id,
    );
    if (alive.current) {
      setDraft({ title: "", text: "", quote: "" });
      setEditing(null);
      setMessage(
        status === "confirmed"
          ? "事实已由你确认，可供后文章节召回。"
          : "事实状态已保存。",
      );
    }
  };
  const insert = (suggestion: SuggestedFact) => {
    setEditing(null);
    setDraft(suggestion);
  };
  const prepare = async () => {
    if (!profile) return;
    const review = await client.prepare(
      projectId,
      chapterId,
      sourceRevision,
      profile.id,
    );
    if (alive.current) {
      setSelectedId(review.id);
      setConsentId("");
      setMessage("评审已准备，请查看发送内容后确认。此时尚未调用模型。");
    }
  };
  const send = async (review: MemoryReview) => {
    const result = await client.send(
      projectId,
      chapterId,
      review,
      consentId === review.id,
    );
    if (alive.current) {
      setSelectedId(result.id);
      setMessage("评审完成。候选事实需要你逐项确认，修改建议可准备定向改写。");
    }
  };
  return (
    <section aria-label="长篇记忆与评审工作台">
      <h4>长篇记忆与一致性评审</h4>
      <p>
        先从正文提取候选事实，再由你确认。后文章节会召回来源未变化的已确认事实；来源变化后需要复核。
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {message ? <p role="status">{message}</p> : null}
      {busy ? <p role="status">正在处理记忆或评审，请勿重复发送…</p> : null}
      {disabled ? <p>请先保存正文并处理冲突，再使用记忆与评审。</p> : null}
      {workspace && workspace.source_revision !== sourceRevision ? (
        <p>正文已更新，请刷新记忆并核对来源版本。</p>
      ) : null}
      <button
        type="button"
        disabled={busy}
        onClick={() => void action(() => Promise.resolve())}
      >
        刷新记忆与评审
      </button>
      <fieldset disabled={blocked}>
        <legend>{editing ? "编辑事实并核对最新原文" : "添加候选事实"}</legend>
        <label>
          事实标题
          <input
            value={draft.title}
            maxLength={1000}
            onChange={(event) =>
              setDraft({ ...draft, title: event.target.value })
            }
          />
        </label>
        <label>
          事实内容
          <textarea
            value={draft.text}
            maxLength={1000}
            onChange={(event) =>
              setDraft({ ...draft, text: event.target.value })
            }
          />
        </label>
        <label>
          事实原文引文
          <textarea
            value={draft.quote}
            maxLength={2000}
            onChange={(event) =>
              setDraft({ ...draft, quote: event.target.value })
            }
          />
        </label>
        <button
          type="button"
          disabled={
            !draft.title.trim() || !draft.text.trim() || !draft.quote.trim()
          }
          onClick={() => void action(() => save("pending"))}
        >
          保存为待确认事实
        </button>
        {editing ? (
          <>
            <button
              type="button"
              onClick={() => void action(() => save("confirmed"))}
            >
              确认编辑后的事实
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setDraft({ title: "", text: "", quote: "" });
              }}
            >
              取消事实编辑
            </button>
          </>
        ) : null}
      </fieldset>
      <h5>本章事实</h5>
      <ul>
        {workspace?.facts
          .filter((fact) => fact.chapter_id === chapterId)
          .map((fact) => (
            <li key={fact.id}>
              <strong>{fact.title}</strong> · {FACT_STATUS[fact.status]}
              {fact.stale ? " · 来源已变，需要复核" : ""}
              <p>{fact.text}</p>
              <blockquote>{fact.quote}</blockquote>
              <button
                type="button"
                disabled={blocked}
                onClick={() => {
                  setEditing(fact);
                  setDraft({
                    title: fact.title,
                    text: fact.text,
                    quote: fact.quote,
                  });
                }}
              >
                编辑并核对原文
              </button>
              {fact.status !== "confirmed" && !fact.stale ? (
                <button
                  type="button"
                  disabled={blocked}
                  onClick={() => void action(() => save("confirmed", fact))}
                >
                  确认此事实
                </button>
              ) : null}
              {fact.status !== "rejected" ? (
                <button
                  type="button"
                  disabled={blocked}
                  onClick={() => void action(() => save("rejected", fact))}
                >
                  驳回此事实
                </button>
              ) : null}
            </li>
          ))}
      </ul>
      <details>
        <summary>
          查看本章可召回的前文事实（{workspace?.recalled_facts.length ?? 0}）
        </summary>
        <p>
          最多24项、10000字符，按文字关联和前文顺序选择；另省略{" "}
          {workspace?.omitted_facts ?? 0} 项。
        </p>
        <ul>
          {workspace?.recalled_facts.map((fact) => (
            <li key={fact.id}>
              {fact.title}：{fact.text}
              <blockquote>{fact.quote}</blockquote>
            </li>
          ))}
        </ul>
      </details>
      <h5>一致性评审与候选事实提取</h5>
      <button
        type="button"
        disabled={blocked || !profile}
        onClick={() => void action(prepare)}
      >
        准备本章评审
      </button>
      {workspace?.reviews.length ? (
        <label>
          已保存的评审
          <select
            value={selected?.id ?? ""}
            disabled={busy}
            onChange={(event) => {
              setSelectedId(event.target.value);
              setConsentId("");
            }}
          >
            {workspace.reviews.map((review, index) => (
              <option key={review.id} value={review.id}>
                {index + 1}.{" "}
                {review.status === "completed"
                  ? "已完成"
                  : review.status === "ready"
                    ? "待发送"
                    : review.status === "running"
                      ? "正在评审"
                      : "失败或中断"}
                {review.stale ? " · 需要复核" : ""}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {selected ? (
        <section aria-label="当前一致性评审">
          <p>
            模型：{selected.model.name}；已尝试 {selected.attempts}/3 次。
          </p>
          {selected.stale ? (
            <p role="status">
              正文或依据事实已变化，此评审仅供追溯。请重新准备评审。
            </p>
          ) : null}
          <details>
            <summary>查看评审实际发送内容</summary>
            <textarea
              aria-label="评审发送正文"
              readOnly
              rows={6}
              value={selected.content}
            />
            <p>
              {selected.content_truncated
                ? "只发送正文末尾24000字符。"
                : "正文未截取。"}
              已纳入 {selected.facts.length} 项前文确认事实，另省略{" "}
              {selected.omitted_facts} 项。
            </p>
            <pre>{JSON.stringify(selected.facts, null, 2)}</pre>
          </details>
          {selected.model.kind === "cloud" ? (
            <label>
              <input
                type="checkbox"
                checked={consentId === selected.id}
                disabled={busy}
                onChange={(event) =>
                  setConsentId(event.target.checked ? selected.id : "")
                }
              />
              我同意向 {selected.model.base_url}{" "}
              发送上述正文和确认事实以进行评审
            </label>
          ) : null}
          {selected.status === "ready" || selected.status === "failed" ? (
            <OperationSendGuard
              key={`${selected.id}:${selected.version}`}
              loadEstimate={loadEstimate}
              refreshKey={`${selected.id}:${selected.version}`}
            >
              {(allowed) => (
                <button
                  type="button"
                  disabled={
                    !allowed ||
                    blocked ||
                    selected.stale ||
                    selected.attempts >= 3 ||
                    (selected.model.kind === "cloud" &&
                      consentId !== selected.id)
                  }
                  onClick={() => void action(() => send(selected))}
                >
                  确认发送并评审
                </button>
              )}
            </OperationSendGuard>
          ) : null}
          {selected.last_error ? (
            <p role="alert">
              上次评审未完成，请检查模型和输出上限；不会自动重发。可核对服务商状态后手动重试。
            </p>
          ) : null}
          {selected.result ? (
            <>
              <p>{selected.result.summary}</p>
              <h5>提取的候选事实</h5>
              <ul>
                {selected.result.facts.map((fact, index) => (
                  <li key={index}>
                    <p>
                      {fact.title}：{fact.text}
                    </p>
                    <blockquote>{fact.quote}</blockquote>
                    <button
                      type="button"
                      disabled={blocked || selected.stale}
                      onClick={() => insert(fact)}
                    >
                      编辑这条候选事实
                    </button>
                  </li>
                ))}
              </ul>
              <h5>一致性问题与修改建议</h5>
              {!selected.result.findings.length ? (
                <p>本次没有发现有充分依据的矛盾；这不保证全书没有问题。</p>
              ) : null}
              <ul>
                {selected.result.findings.map((finding, index) => (
                  <li key={index}>
                    <blockquote>{finding.quote}</blockquote>
                    <p>{finding.explanation}</p>
                    <p>{finding.instruction}</p>
                    <button
                      type="button"
                      disabled={blocked || selected.stale || !profile}
                      onClick={() =>
                        onRewrite(
                          finding.quote,
                          finding.instruction,
                          selected.source_revision,
                        )
                      }
                    >
                      按此建议准备改写
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>
      ) : null}
      <h5>需要复核的来源与后文章节</h5>
      {!workspace?.impacts.length ? (
        <p>当前没有检测到已记录来源的变化。</p>
      ) : null}
      <ul>
        {workspace?.impacts.map((impact) => (
          <li key={impact.chapter_id}>
            <Link
              to={`/projects/${projectId}/chapters/${impact.chapter_id}/write`}
            >
              {impact.title}
            </Link>
            ：{impact.reason}
          </li>
        ))}
      </ul>
    </section>
  );
}
