import { useCallback, useEffect, useRef, useState } from "react";

import { OperationSendGuard } from "../../usage/components/SendEstimatePanel";
import {
  chapterDraftClient,
  chapterDraftError,
  type ChapterDraft,
  type ChapterDraftClient,
  type DraftStatus,
} from "../api/chapter-draft";

const STATUS: Record<DraftStatus, string> = {
  ready: "可以继续生成",
  running: "正在生成",
  failed: "上一段失败，已停止（不会自动重试）",
  exhausted: "额度已用完",
};
const ERRORS: Record<string, string> = {
  ChapterDraftOutputInvalid: "模型返回的字数不在本段范围内",
  AIProviderInterrupted: "上次发送时程序退出，结果未知",
  AIProviderUnavailable: "模型服务不可用",
  BudgetRefused: "严格预算拒绝，未发送",
};
const TAIL = 300;

/**
 * 章节候选稿：在作者确认的单章额度内逐段生成（每段一次单独计量的请求），
 * 之前未采用的段落只作为“本次候选稿”给下一段参考。准备、预估、对照都不调用模型；
 * 只有“采用”才写入正文，且正文自基线后被手改时服务端拒绝，候选稿保留供比较。
 */
export function ChapterDraftPanel({
  chapterId,
  profileId,
  jobId,
  savedContent,
  savedRevisionId,
  saved,
  acceptExternal,
  client = chapterDraftClient,
}: {
  readonly chapterId: string;
  /** 作者在助手里选定的模型；为空时不能准备。 */
  readonly profileId: string;
  readonly jobId?: string;
  readonly savedContent: string;
  readonly savedRevisionId: string;
  readonly saved: boolean;
  /** 锁定编辑器、执行写入并重新读取已保存正文；未保存或冲突时返回 false。 */
  readonly acceptExternal: (commit: () => Promise<void>) => Promise<boolean>;
  readonly client?: ChapterDraftClient;
}) {
  const [draft, setDraft] = useState<ChapterDraft | null>(null);
  const [instruction, setInstruction] = useState("");
  const [maxSegments, setMaxSegments] = useState("10");
  const [maxCharacters, setMaxCharacters] = useState("3000");
  const [count, setCount] = useState("1");
  const [consent, setConsent] = useState(false);
  const [bindJob, setBindJob] = useState(false);
  const [selected, setSelected] = useState<readonly number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const keys = useRef(new Map<string, string>());

  useEffect(() => {
    let cancelled = false;
    void client
      .list(chapterId)
      .then(async (items) => {
        const latest = items[0];
        if (!latest || cancelled) return;
        const loaded = await client.get(chapterId, latest.id);
        if (!cancelled) setDraft(loaded);
      })
      .catch(() => {
        // 读取失败不影响写作；作者仍可重新准备。
      });
    return () => {
      cancelled = true;
    };
  }, [chapterId, client]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (failure) {
      setError(chapterDraftError(failure).message);
    } finally {
      setBusy(false);
    }
  };

  const prepare = () =>
    run(async () => {
      const segments = Number(maxSegments);
      const characters = Number(maxCharacters);
      if (
        !Number.isInteger(segments) ||
        segments < 1 ||
        segments > 10 ||
        !Number.isInteger(characters) ||
        characters < 200 ||
        characters > 3000
      ) {
        setError("段数须为 1–10，总字数须为 200–3000。");
        return;
      }
      if (!saved) {
        setError("正文有未保存修改，请先保存，再为最新正文准备候选稿。");
        return;
      }
      setSelected([]);
      setDraft(
        await client.prepare(chapterId, {
          profileId,
          instruction,
          maxSegments: segments,
          maxOutputCharacters: characters,
          ...(bindJob && jobId ? { writingJobId: jobId } : {}),
        }),
      );
    });

  const send = (current: ChapterDraft) =>
    run(async () => {
      const segments = Number(count);
      if (
        !Number.isInteger(segments) ||
        segments < 1 ||
        segments > current.remaining_requests
      ) {
        setError("本次段数须在剩余请求次数之内。");
        return;
      }
      try {
        setDraft(await client.send(chapterId, current, segments, consent));
      } finally {
        // 无论成功、失败或被拒，都以服务端记录为准。
        setDraft(await client.get(chapterId, current.id).catch(() => current));
      }
    });

  const adopt = (current: ChapterDraft, indexes: readonly number[] | null) =>
    run(async () => {
      const receipt = `${current.id}:${indexes === null ? "all" : indexes.join(",")}`;
      const key = keys.current.get(receipt) ?? crypto.randomUUID();
      keys.current.set(receipt, key);
      let result: ChapterDraft | null = null;
      let failure: Error | null = null;
      const accepted = await acceptExternal(async () => {
        try {
          result = await client.adopt(chapterId, current.id, key, indexes);
        } catch (caught) {
          failure = chapterDraftError(caught);
        }
      });
      const refused = failure as Error | null;
      if (refused !== null) {
        setDraft(await client.get(chapterId, current.id).catch(() => current));
        throw refused;
      }
      if (!accepted) throw new Error("请先保存或处理正文冲突，再确认采用。");
      const adopted = result as ChapterDraft | null;
      if (adopted) setDraft(adopted);
      setSelected([]);
      setNotice("已采用，正文已更新。");
    });

  const loadEstimate = useCallback(
    () =>
      draft
        ? client.estimate(chapterId, draft.id)
        : Promise.reject(new Error("no draft")),
    [chapterId, client, draft],
  );

  const pending = draft?.segments.filter((item) => item.status === "pending");
  const stale = !!draft && draft.current_revision_id !== savedRevisionId;
  return (
    <section aria-label="章节候选稿" data-feature-id="ai.chapter-draft">
      <h4>章节候选稿（单章，多段）</h4>
      <p>
        在你确认的额度内逐段生成本章候选稿（最多 10 次请求、合计不超过 3000
        字，每段 200–300
        字）。每段单独预估、单独计费；失败即停止，不自动重试。之前未采用的段落只作为“本次候选稿”给下一段参考，不会成为事实，也不进入其他任务。
      </p>
      <fieldset disabled={busy}>
        <legend>准备（不调用模型）</legend>
        <label>
          额外要求
          <textarea
            value={instruction}
            maxLength={4000}
            onChange={(event) => setInstruction(event.target.value)}
          />
        </label>
        <label>
          最多请求次数
          <input
            type="number"
            min={1}
            max={10}
            value={maxSegments}
            onChange={(event) => setMaxSegments(event.target.value)}
          />
        </label>
        <label>
          总字数上限
          <input
            type="number"
            min={200}
            max={3000}
            value={maxCharacters}
            onChange={(event) => setMaxCharacters(event.target.value)}
          />
        </label>
        {jobId ? (
          <label>
            <input
              type="checkbox"
              checked={bindJob}
              onChange={(event) => setBindJob(event.target.checked)}
            />
            计入当前跨章任务的额度（占用本章任务步骤）
          </label>
        ) : null}
        <button
          type="button"
          disabled={!profileId}
          onClick={() => void prepare()}
        >
          准备候选稿
        </button>
        {profileId ? null : <p>请先在上方选择模型。</p>}
      </fieldset>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {draft ? (
        <div>
          <p>
            状态：{STATUS[draft.status]} · 模型 {draft.model_name} · 已请求{" "}
            {draft.attempts}/{draft.max_segments} 次 · 已生成{" "}
            {draft.generated_characters}/{draft.max_output_characters} 字 · 剩余{" "}
            {draft.remaining_requests} 次 / {draft.remaining_characters} 字
          </p>
          <details>
            <summary>下一段将发送的内容</summary>
            <p>来源：{draft.included_sources.join("、") || "无"}</p>
            <pre>{draft.next_request_preview}</pre>
          </details>
          {draft.failures.length ? (
            <ul aria-label="失败记录">
              {draft.failures.map((item) => (
                <li key={`${item.attempt}:${item.error}`}>
                  第 {item.attempt} 次请求：{ERRORS[item.error] ?? item.error}
                  {item.evidence ? (
                    <q>
                      {item.evidence}
                      {item.evidence_truncated ? "…" : ""}
                    </q>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
          {draft.can_send && !stale ? (
            <OperationSendGuard
              loadEstimate={loadEstimate}
              refreshKey={`${draft.id}:${draft.version}`}
            >
              {(allowed) => (
                <div>
                  <label>
                    本次生成段数
                    <input
                      type="number"
                      min={1}
                      max={draft.remaining_requests}
                      value={count}
                      onChange={(event) => setCount(event.target.value)}
                    />
                  </label>
                  {draft.model_kind === "cloud" ? (
                    <label>
                      <input
                        type="checkbox"
                        checked={consent}
                        onChange={(event) => setConsent(event.target.checked)}
                      />
                      同意把本章上下文与候选稿发送给云端模型
                    </label>
                  ) : null}
                  <button
                    type="button"
                    disabled={
                      busy ||
                      !allowed ||
                      (draft.model_kind === "cloud" && !consent)
                    }
                    onClick={() => void send(draft)}
                  >
                    {draft.status === "failed"
                      ? "确认重试（新的计费请求）"
                      : "确认发送"}
                  </button>
                  <p>预估针对下一段；多段时每段发送前都会再按预算检查。</p>
                </div>
              )}
            </OperationSendGuard>
          ) : null}
          <h5>整章对照</h5>
          {stale ? (
            <p role="alert">
              正文在候选稿基线之后已被修改，不能采用；候选稿保留供比较，可重新准备。
            </p>
          ) : null}
          <div aria-label="整章候选稿对照">
            {stale ? null : (
              <p>
                <span>
                  {savedContent.length > TAIL ? "…" : ""}
                  {savedContent.slice(-TAIL)}
                </span>
              </p>
            )}
            {pending?.map((item) => (
              <p key={item.index}>
                <label>
                  <input
                    type="checkbox"
                    aria-label={`选择第 ${item.index + 1} 段`}
                    disabled={stale || busy}
                    checked={selected.includes(item.index)}
                    onChange={(event) =>
                      setSelected((current) =>
                        event.target.checked
                          ? [...current, item.index].sort((a, b) => a - b)
                          : current.filter((index) => index !== item.index),
                      )
                    }
                  />
                  第 {item.index + 1} 段（{item.characters} 字）
                </label>
                <ins>{item.text}</ins>
              </p>
            ))}
          </div>
          <p>
            已采用 {draft.segments.length - (pending?.length ?? 0)} 段，未采用{" "}
            {pending?.length ?? 0} 段。
          </p>
          <button
            type="button"
            disabled={busy || stale || !selected.length}
            onClick={() => void adopt(draft, selected)}
          >
            采用所选段落
          </button>
          <button
            type="button"
            disabled={busy || stale || !pending?.length}
            onClick={() => void adopt(draft, null)}
          >
            采用全部未采用段落
          </button>
        </div>
      ) : null}
    </section>
  );
}
