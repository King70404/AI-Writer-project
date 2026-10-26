import { useEffect, useRef, useState } from "react";

import {
  EDITORIAL_LABELS,
  workbenchError,
  workspaceClient,
  type EditorialState,
  type EditorialStatus,
  type WorkspaceClient,
} from "../api/workspace";

type LoadState =
  | { readonly status: "loading" }
  | { readonly status: "error"; readonly message: string }
  | { readonly status: "ready"; readonly state: EditorialState };

const STATUSES: readonly EditorialStatus[] = ["draft", "review", "final"];

/**
 * 作者手动选择“草稿 / 待检查 / 定稿”。状态绑定当前已保存的正文版本：
 * 修改前先保存正文；生成完成、刷新或采用候选都不会自动改变状态。
 */
export function EditorialStatusControl({
  chapterId,
  savedRevisionId,
  flush,
  client = workspaceClient,
}: {
  readonly chapterId: string;
  readonly savedRevisionId: string;
  readonly flush: () => Promise<boolean>;
  readonly client?: WorkspaceClient;
}) {
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [pendingFinal, setPendingFinal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const saving = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      setLoad({ status: "loading" });
      client
        .editorial(chapterId)
        .then((state) => {
          if (!controller.signal.aborted) setLoad({ status: "ready", state });
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted)
            setLoad({
              status: "error",
              message: workbenchError(error).message,
            });
        });
    });
    return () => controller.abort();
  }, [attempt, chapterId, client]);

  if (load.status === "loading")
    return <p className="editorial-status">章节状态读取中…</p>;
  if (load.status === "error")
    return (
      <div className="editorial-status" role="alert">
        <p>章节状态：{load.message}</p>
        <button type="button" onClick={() => setAttempt((v) => v + 1)}>
          重新读取状态
        </button>
      </div>
    );

  const current = load.state;
  const changedSinceMark =
    current.chapter_revision_id !== null &&
    current.chapter_revision_id !== savedRevisionId;

  const commit = async (status: EditorialStatus) => {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setPendingFinal(false);
    setMessage("");
    try {
      if (!(await flush())) {
        setMessage("正文尚未保存，章节状态未修改。请先处理保存状态。");
        return;
      }
      const saved = await client.saveEditorial(
        chapterId,
        status,
        current.version,
      );
      setLoad({ status: "ready", state: saved });
      setMessage(`已标记为“${EDITORIAL_LABELS[saved.status]}”。`);
    } catch (error) {
      const failure = workbenchError(error);
      setMessage(failure.message);
      if (failure.code === "EDITORIAL_CONFLICT") setAttempt((v) => v + 1);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  };

  const choose = (status: EditorialStatus) => {
    if (status === current.status && !changedSinceMark) return;
    if (status === "final" && current.open_actions > 0) {
      setPendingFinal(true);
      return;
    }
    void commit(status);
  };

  return (
    <div className="editorial-status" data-feature-id="workbench.editorial">
      <label htmlFor={`editorial-${chapterId}`}>章节状态</label>
      <select
        id={`editorial-${chapterId}`}
        value={current.status}
        disabled={busy}
        onChange={(event) => choose(event.target.value as EditorialStatus)}
      >
        {STATUSES.map((status) => (
          <option key={status} value={status}>
            {EDITORIAL_LABELS[status]}
          </option>
        ))}
      </select>
      {changedSinceMark ? (
        <span className="editorial-status__changed">
          标记后正文已修改
          <button
            type="button"
            disabled={busy}
            onClick={() => choose(current.status)}
          >
            按当前正文重新标记
          </button>
        </span>
      ) : null}
      {pendingFinal ? (
        <div role="alert" className="editorial-status__confirm">
          <p>
            本章还有 {current.open_actions}{" "}
            项待处理（候选、事实或评审）。仍要标为定稿吗？
          </p>
          <button type="button" onClick={() => void commit("final")}>
            仍标为定稿
          </button>
          <button type="button" onClick={() => setPendingFinal(false)}>
            暂不标记
          </button>
        </div>
      ) : null}
      {message ? <p className="editorial-status__message">{message}</p> : null}
    </div>
  );
}
