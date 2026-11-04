import { useState, type ChangeEvent, type FormEvent } from "react";
import { Link } from "react-router";

import { ApiError } from "../../../api/errors";
import { fetchStorageInstance } from "../../local-drafts/drafts";
import { chapterWritingPath } from "../../novel-structure/routing";
import { projectStructurePath } from "../../projects/routing";
import {
  importClient,
  type ChapterBoundary,
  type CommitInput,
  type HeadingMode,
  type ImportClient,
  type ImportPreview,
  type ImportReceipt,
} from "../api/client";
import "./ImportWorkbench.css";

const LIMIT_BYTES = 10 * 1024 * 1024;
const RECOVERY_KEY = "aiwebnovel:legacy-import:v1";
interface Recovery {
  readonly previewId: string;
  readonly pending?: CommitInput;
}
function recoveryKey(instance: string): string {
  return `${RECOVERY_KEY}:${instance}`;
}
function loadRecovery(instance: string): Recovery | null {
  try {
    const raw: unknown = JSON.parse(
      localStorage.getItem(recoveryKey(instance)) ?? "null",
    );
    if (
      typeof raw !== "object" ||
      raw === null ||
      !("previewId" in raw) ||
      typeof raw.previewId !== "string"
    )
      return null;
    return raw as Recovery;
  } catch {
    return null;
  }
}
function persistRecovery(instance: string, value: Recovery | null): void {
  try {
    if (value === null) localStorage.removeItem(recoveryKey(instance));
    else localStorage.setItem(recoveryKey(instance), JSON.stringify(value));
  } catch {
    /* Preview still works in this window when storage is unavailable. */
  }
}
function message(error: unknown): string {
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      IMPORT_UNAVAILABLE:
        "当前数据库需要升级后才能导入。请先停止服务、备份并升级数据库。",
      IMPORT_INVALID_ENCODING: "原稿不是有效的 UTF-8，请转换编码后重新预览。",
      IMPORT_TOO_LARGE: "原稿超过 10 MiB，请缩小后重新预览。",
      IMPORT_TOO_MANY_CHAPTERS: "章节超过 500 章，请分批导入。",
      IMPORT_INVALID_CHAPTER:
        "有章节的标题或正文不符合要求，请调整后重新预览。",
      IMPORT_INVALID: "导入信息不符合要求，请检查书名、章节标题和正文。",
      IMPORT_NOT_FOUND: "没有找到此导入预览，请重新选择原稿。",
      IMPORT_PREVIEW_EXPIRED: "预览已过期，请重新选择文件或粘贴原文。",
      IMPORT_CONFLICT:
        "导入预览已发生变化或已经导入，请恢复预览或查询导入结果。",
      IMPORT_PROJECT_DELETED: "导入的小说已被删除，无法再次打开。",
    };
    if (error.code === "IMPORT_INVALID_CHAPTER") {
      const match = /^Chapter (\d+) has invalid title or content\.$/u.exec(
        error.message,
      );
      if (match)
        return `第 ${match[1]} 章的标题或正文不符合要求，请调整后重新预览。`;
    }
    return messages[error.code] ?? "导入未完成，请检查输入和连接后重试。";
  }
  return "暂时无法完成操作。请检查连接后重试，原稿不会被修改。";
}

function boundary(chapter: ChapterBoundary): ChapterBoundary {
  return {
    title: chapter.title,
    start: chapter.start,
    body_start: chapter.body_start,
    end: chapter.end,
  };
}

// Textareas display CRLF and CR as LF. Map their cursor back to source code points.
function sourceOffset(body: string, displayedPrefix: string): number {
  const target = Array.from(displayedPrefix).length;
  const chars = Array.from(body);
  let source = 0;
  let displayed = 0;
  while (source < chars.length && displayed < target) {
    if (chars[source] === "\r" && chars[source + 1] === "\n") source += 2;
    else source += 1;
    displayed += 1;
  }
  return source;
}

export function ImportWorkbench({
  client = importClient,
  loadInstance = fetchStorageInstance,
}: {
  readonly client?: ImportClient;
  readonly loadInstance?: () => Promise<string>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("");
  const [mode, setMode] = useState<HeadingMode>("auto");
  const [bookTitle, setBookTitle] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [instance, setInstance] = useState<string | null>(null);
  const [checkingInstance, setCheckingInstance] = useState(false);
  const [recovery, setRecovery] = useState<Recovery | null>(null);
  const [receipt, setReceipt] = useState<ImportReceipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [selection, setSelection] = useState<Record<number, number>>({});
  const [titles, setTitles] = useState<Record<number, string>>({});

  const remember = (value: Recovery | null) => {
    setRecovery(value);
    if (instance !== null) persistRecovery(instance, value);
  };
  const openImporter = () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (instance !== null || checkingInstance) return;
    setCheckingInstance(true);
    setNotice("");
    void loadInstance()
      .then((id) => {
        setInstance(id);
        setRecovery(loadRecovery(id));
      })
      .catch(() => {
        setNotice(
          "无法确认当前数据根，请检查服务后收起并重新打开导入面板。原稿未上传。",
        );
      })
      .finally(() => setCheckingInstance(false));
  };
  const fileChanged = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setNotice("");
    if (!/\.(?:txt|md)$/iu.test(file.name)) {
      setNotice("请选择 TXT 或 Markdown 文件。");
      event.target.value = "";
      return;
    }
    if (file.size > LIMIT_BYTES) {
      setNotice("文件超过 10 MiB，请缩小后再导入。");
      event.target.value = "";
      return;
    }
    setBusy(true);
    try {
      const content = new TextDecoder("utf-8", { fatal: true }).decode(
        await file.arrayBuffer(),
      );
      setText(content);
      setFilename(file.name);
    } catch {
      setNotice("文件不是有效的 UTF-8，请先转换编码。原文件未更改。");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  };
  const createPreview = async (event: FormEvent) => {
    event.preventDefault();
    if (new TextEncoder().encode(text).length > LIMIT_BYTES) {
      setNotice("原文超过 10 MiB，请缩小后再导入。");
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const next = await client.preview(text, mode);
      setPreview(next);
      setTitles({});
      setSelection({});
      remember({ previewId: next.preview_id });
    } catch (error) {
      setNotice(message(error));
    } finally {
      setBusy(false);
    }
  };
  const restore = async () => {
    if (!recovery) return;
    setBusy(true);
    setNotice("");
    try {
      if (recovery.pending) {
        try {
          const done = await client.receipt(recovery.previewId);
          setReceipt(done);
          remember(null);
          return;
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) throw error;
        }
        setBookTitle(recovery.pending.title);
      }
      const saved = await client.getPreview(recovery.previewId);
      setPreview(saved);
      setTitles({});
      setSelection({});
    } catch (error) {
      setNotice(message(error));
    } finally {
      setBusy(false);
    }
  };
  const update = async (chapters: readonly ChapterBoundary[]) => {
    if (!preview || recovery?.pending) return;
    setBusy(true);
    setNotice("");
    try {
      const updated = await client.update(
        preview.preview_id,
        preview.version,
        chapters,
      );
      setPreview(updated);
      setTitles({});
      setSelection({});
    } catch (error) {
      setNotice(message(error));
    } finally {
      setBusy(false);
    }
  };
  const saveTitle = (index: number) => {
    if (!preview) return;
    const current = preview.chapters[index];
    const title = titles[index] ?? current.title;
    if (title === current.title) return;
    if (!title.trim()) {
      setNotice("章节标题不能为空。");
      return;
    }
    void update(
      preview.chapters.map((chapter, i) => ({
        ...boundary(chapter),
        ...(i === index ? { title } : {}),
      })),
    );
  };
  const split = (index: number) => {
    if (!preview) return;
    const chapter = preview.chapters[index];
    const offset = selection[index] ?? 0;
    const point = chapter.body_start + offset;
    if (point <= chapter.body_start || point >= chapter.end) {
      setNotice("请先在章节正文中选择拆分位置。");
      return;
    }
    const chapters = preview.chapters.map(boundary);
    chapters.splice(
      index,
      1,
      { ...chapters[index], end: point },
      { title: "新章节", start: point, body_start: point, end: chapter.end },
    );
    void update(chapters);
  };
  const merge = (index: number) => {
    if (!preview || index + 1 >= preview.chapters.length) return;
    const chapters = preview.chapters.map(boundary);
    chapters.splice(index, 2, {
      ...chapters[index],
      end: chapters[index + 1].end,
    });
    void update(chapters);
  };
  const commit = async () => {
    if (!preview) return;
    if (!recovery?.pending && !bookTitle.trim()) {
      setNotice("请填写新小说的书名。");
      return;
    }
    const input = recovery?.pending ?? {
      preview_version: preview.version,
      source_sha256: preview.source_sha256,
      idempotency_key: crypto.randomUUID(),
      title: bookTitle.trim(),
    };
    remember({ previewId: preview.preview_id, pending: input });
    setBusy(true);
    setNotice("");
    try {
      const done = await client.commit(preview.preview_id, input);
      setReceipt(done);
      remember(null);
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.status >= 400 &&
        error.status < 500 &&
        error.status !== 408 &&
        error.status !== 409
      ) {
        // A validation or authorization response means this commit was rejected.
        remember({ previewId: preview.preview_id });
        setNotice(message(error));
      } else {
        setNotice(`${message(error)} 可以使用同一请求再次确认，避免重复创建。`);
      }
    } finally {
      setBusy(false);
    }
  };
  const reset = () => {
    setPreview(null);
    setReceipt(null);
    setText("");
    setFilename("");
    setBookTitle("");
    setTitles({});
    setSelection({});
    setNotice("");
    remember(null);
  };
  const pending = Boolean(recovery?.pending);
  const unsavedTitles =
    preview !== null &&
    Object.entries(titles).some(
      ([index, title]) => title !== preview.chapters[Number(index)]?.title,
    );
  return (
    <section className="legacy-import" aria-label="导入旧稿">
      <button type="button" onClick={openImporter} aria-expanded={open}>
        {open ? "收起导入旧稿" : "导入旧稿"}
      </button>
      {open ? (
        <div className="legacy-import__body">
          <h3>导入旧稿为新小说</h3>
          <p>导入不会发送给模型，也不会覆盖现有小说。</p>
          {notice ? <p role="alert">{notice}</p> : null}
          {receipt ? (
            <div role="status">
              <p>小说已创建，旧稿导入完成。</p>
              <Link
                to={chapterWritingPath(
                  receipt.project_id,
                  receipt.first_chapter_id,
                )}
              >
                打开第一章
              </Link>
              {" · "}
              <Link to={projectStructurePath(receipt.project_id)}>
                查看全书结构
              </Link>
              <p>
                <button type="button" onClick={reset}>
                  导入另一部
                </button>
              </p>
            </div>
          ) : null}
          {!preview && !receipt ? (
            <>
              {recovery ? (
                <p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void restore()}
                  >
                    恢复上次导入预览
                  </button>
                </p>
              ) : null}
              <form onSubmit={(event) => void createPreview(event)}>
                <label>
                  选择 TXT 或 Markdown 文件
                  <input
                    type="file"
                    accept=".txt,.md,text/plain,text/markdown"
                    disabled={busy}
                    onChange={(event) => void fileChanged(event)}
                  />
                </label>
                {filename ? <p>已读取：{filename}</p> : null}
                <label>
                  或粘贴旧稿
                  <textarea
                    value={text}
                    onChange={(event) => {
                      setText(event.target.value);
                      setFilename("");
                    }}
                    rows={8}
                    disabled={busy}
                  />
                </label>
                <label>
                  章节标题格式
                  <select
                    value={mode}
                    disabled={busy}
                    onChange={(event) =>
                      setMode(event.target.value as HeadingMode)
                    }
                  >
                    <option value="auto">自动识别</option>
                    <option value="chinese">第 N 章</option>
                    <option value="markdown">Markdown 标题</option>
                    <option value="single">作为一章</option>
                  </select>
                </label>
                <p>UTF-8 编码，最多 10 MiB、500 章；先预览再确认。</p>
                <button
                  type="submit"
                  disabled={
                    busy || checkingInstance || instance === null || !text
                  }
                >
                  预览分章
                </button>
              </form>
            </>
          ) : null}
          {preview && !receipt ? (
            <div>
              <p>
                共 {preview.chapters.length} 章，正文{" "}
                {preview.chapters.reduce(
                  (sum, chapter) => sum + Array.from(chapter.body).length,
                  0,
                )}{" "}
                字符。预览保留原文，确认后创建新小说。
              </p>
              {preview.original_line_endings_normalized ? (
                <p>
                  原稿包含 Windows 或旧式换行；导入后正文中的换行会统一为
                  LF，其他正文内容保持不变。
                </p>
              ) : null}
              {pending ? (
                <p>
                  上次确认的结果尚未查明。再次确认将使用同一请求，不会创建重复小说。
                </p>
              ) : null}
              <ol className="legacy-import__chapters">
                {preview.chapters.map((chapter, index) => (
                  <li key={`${chapter.start}:${chapter.end}`}>
                    <label>
                      第 {index + 1} 章标题
                      <input
                        value={titles[index] ?? chapter.title}
                        disabled={busy || pending}
                        onChange={(event) =>
                          setTitles((old) => ({
                            ...old,
                            [index]: event.target.value,
                          }))
                        }
                        onBlur={() => saveTitle(index)}
                      />
                    </label>
                    <label>
                      第 {index + 1} 章正文（选择拆分位置）
                      <textarea
                        readOnly
                        rows={5}
                        value={chapter.body}
                        onSelect={(event) => {
                          const offset = sourceOffset(
                            chapter.body,
                            event.currentTarget.value.slice(
                              0,
                              event.currentTarget.selectionStart,
                            ),
                          );
                          setSelection((old) => ({ ...old, [index]: offset }));
                        }}
                      />
                    </label>
                    <div>
                      <button
                        type="button"
                        disabled={busy || pending || unsavedTitles}
                        onClick={() => split(index)}
                      >
                        从光标处拆分
                      </button>{" "}
                      <button
                        type="button"
                        disabled={
                          busy ||
                          pending ||
                          unsavedTitles ||
                          index === preview.chapters.length - 1
                        }
                        onClick={() => merge(index)}
                      >
                        与下一章合并
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
              <label>
                新小说书名
                <input
                  value={bookTitle}
                  onChange={(event) => setBookTitle(event.target.value)}
                  disabled={busy || pending}
                />
              </label>
              <div>
                <button
                  type="button"
                  disabled={
                    busy || unsavedTitles || (!bookTitle.trim() && !pending)
                  }
                  onClick={() => void commit()}
                >
                  {pending ? "再次确认导入" : "确认导入为新小说"}
                </button>{" "}
                {pending ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void restore()}
                  >
                    查询导入结果
                  </button>
                ) : null}{" "}
                <button
                  type="button"
                  disabled={busy || pending}
                  onClick={reset}
                >
                  取消导入
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
