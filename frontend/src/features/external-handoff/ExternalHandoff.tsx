import { useRef, useState, type ChangeEvent } from "react";
import type { useChapterWriting } from "../novel-structure/hooks/useChapterWriting";
import {
  handoffClient,
  type Handoff,
  type HandoffCandidate,
  type HandoffClient,
  type Preview,
} from "./client";
import "./handoff.css";

export function ExternalHandoff({
  chapterId,
  writing,
  client = handoffClient,
}: {
  readonly chapterId: string;
  readonly writing: ReturnType<typeof useChapterWriting>;
  readonly client?: HandoffClient;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [instruction, setInstruction] = useState("");
  const [include, setInclude] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [list, setList] = useState<readonly Handoff[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [text, setText] = useState("");
  const [rawFile, setRawFile] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<HandoffCandidate | null>(null);
  const keys = useRef<Record<string, string>>({});
  const selected = list.find((h) => h.handoff_id === selectedId);
  const load = async () => {
    const items = await client.list(chapterId);
    setList(items);
    return items;
  };
  const toggle = () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setBusy(true);
    void load()
      .catch(() => setError("无法读取本章交接任务，请检查连接后重新打开。"))
      .finally(() => setBusy(false));
  };
  const prepare = async () => {
    setBusy(true);
    setError("");
    try {
      if (!(await writing.flush())) throw new Error("请先保存正文并解决冲突。");
      setPreview(
        await client.preview(chapterId, {
          instruction,
          include_manuscript: include,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "预览失败，请重试。");
    } finally {
      setBusy(false);
    }
  };
  const create = async () => {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const saved = await client.create(chapterId, {
        instruction,
        include_manuscript: include,
        context_sha256: preview.context_sha256,
      });
      if (!saved.handoff_id) throw new Error("未能保存交接任务。");
      const items = await load();
      setSelectedId(saved.handoff_id);
      setCandidate(
        items
          .find((h) => h.handoff_id === saved.handoff_id)
          ?.candidates.at(-1) ?? null,
      );
      setPreview(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  };
  const download = async () => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const blob = await client.download(chapterId, selected.handoff_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "外部AI交接.zip";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "下载失败。");
    } finally {
      setBusy(false);
    }
  };
  const chooseFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 256 * 1024) {
      setError("返回文件超过 256 KiB，请缩小后再导入。");
      return;
    }
    try {
      const value = new TextDecoder("utf-8", { fatal: true }).decode(
        await file.arrayBuffer(),
      );
      if (file.name.toLowerCase().endsWith(".json")) {
        setRawFile(value);
        setText("");
      } else {
        setRawFile(null);
        setText(value);
      }
      setError("");
    } catch {
      setError("文件不是有效的 UTF-8。");
    } finally {
      e.target.value = "";
    }
  };
  const receive = async () => {
    if (!selected) return;
    const raw =
      rawFile ??
      JSON.stringify({
        format_version: 1,
        handoff_id: selected.handoff_id,
        context_sha256: selected.context_sha256,
        text,
      });
    if (new TextEncoder().encode(raw).length > 256 * 1024) {
      setError("返回内容超过 256 KiB，请缩小后再导入。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await client.candidate(
        chapterId,
        selected.handoff_id,
        raw,
      );
      setCandidate(result);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "导入失败。");
    } finally {
      setBusy(false);
    }
  };
  const adopt = async () => {
    if (!selected || !candidate) return;
    setBusy(true);
    setError("");
    try {
      keys.current[candidate.candidate_id] ??= crypto.randomUUID();
      const done = await writing.acceptExternal(() =>
        client.adopt(
          chapterId,
          selected.handoff_id,
          candidate.candidate_id,
          writing.state.snapshot.etag,
          keys.current[candidate.candidate_id],
        ),
      );
      if (!done) throw new Error("请先保存正文并解决冲突。");
      setCandidate({ ...candidate, status: "adopted" });
      await load();
    } catch {
      setError(
        "采用未完成：正文或来源可能已经改变，请先核对并重新准备交接。候选仍保留。",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="external-handoff" aria-label="外部 AI 交接">
      <button type="button" onClick={toggle} aria-expanded={open}>
        {open ? "收起外部 AI 交接" : "外部 AI 交接"}
      </button>
      {open ? (
        <div>
          <h4>外部 AI 交接</h4>
          <p>
            选择发送内容，下载后自行交给外部 AI；外部服务是否计费由该服务决定。
          </p>
          {error ? <p role="alert">{error}</p> : null}
          <label>
            本次任务说明
            <textarea
              value={instruction}
              onChange={(e) => {
                setInstruction(e.target.value);
                setPreview(null);
              }}
              disabled={busy}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={include}
              onChange={(e) => {
                setInclude(e.target.checked);
                setPreview(null);
              }}
              disabled={busy}
            />
            包含当前章节已保存正文
          </label>
          <p>本版本仅支持选择当前章节正文；规划、规则和事实暂不可选。</p>
          <button type="button" disabled={busy} onClick={() => void prepare()}>
            预览交接内容
          </button>
          {preview ? (
            <div>
              <h5>确认交接内容</h5>
              <pre>{preview.context}</pre>
              <p>
                {Array.from(preview.context).length}{" "}
                字符；未选择的内容不会导出。
              </p>
              <button
                type="button"
                disabled={busy || writing.state.status !== "saved"}
                onClick={() => void create()}
              >
                确认保存交接任务
              </button>
            </div>
          ) : null}
          {list.length ? (
            <>
              <label>
                选择已有交接任务
                <select
                  value={selectedId}
                  onChange={(e) => {
                    const id = e.target.value;
                    setSelectedId(id);
                    setCandidate(
                      list
                        .find((h) => h.handoff_id === id)
                        ?.candidates.at(-1) ?? null,
                    );
                    setText("");
                    setRawFile(null);
                  }}
                >
                  <option value="">请选择</option>
                  {list.map((item, index) => (
                    <option key={item.handoff_id} value={item.handoff_id}>
                      本章交接任务 {index + 1} · 正文版本 {item.base_version}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : null}
          {selected ? (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => void download()}
              >
                下载交接包
              </button>
              <label>
                粘贴外部返回正文
                <textarea
                  value={text}
                  onChange={(e) => {
                    setText(e.target.value);
                    setRawFile(null);
                  }}
                  disabled={busy}
                />
              </label>
              <label>
                或选择外部返回文件
                <input
                  type="file"
                  accept=".json,.txt,application/json,text/plain"
                  disabled={busy}
                  onChange={(e) => void chooseFile(e)}
                />
              </label>
              {rawFile !== null ? (
                <p>已读取 JSON 返回文件，提交时会校验任务归属。</p>
              ) : null}
              <button
                type="button"
                disabled={busy || (!text && rawFile === null)}
                onClick={() => void receive()}
              >
                导入为外部候选
              </button>
            </>
          ) : null}
          {candidate ? (
            <section aria-label="外部候选对照">
              <h5>作者导入的外部候选</h5>
              <p>当前正文末尾</p>
              <pre>{writing.state.content.slice(-500)}</pre>
              <p>拟追加的候选</p>
              <pre>{candidate.text}</pre>
              {candidate.status === "adopted" ? (
                <p>已采用</p>
              ) : (
                <button
                  type="button"
                  disabled={busy || writing.state.status !== "saved"}
                  onClick={() => void adopt()}
                >
                  确认追加候选到正文
                </button>
              )}
            </section>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
