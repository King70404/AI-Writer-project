import { useEffect, useState } from "react";

import {
  downloadText,
  draftFilename,
  fetchStorageInstance,
  listDrafts,
  removeDraft,
  type StoredDraft,
} from "./drafts";

/**
 * 按小说查看与清理本机草稿。未恢复的草稿不按时间自动删除；只有作者在这里丢弃，
 * 或服务器确认已有相同内容时才清理。来自其他数据根的草稿只允许下载或清理。
 */
export function LocalDraftManager({
  projectId,
  chapterTitles,
  loadInstance = fetchStorageInstance,
}: {
  readonly projectId: string;
  readonly chapterTitles: ReadonlyMap<string, string>;
  readonly loadInstance?: () => Promise<string>;
}) {
  const [drafts, setDrafts] = useState<readonly StoredDraft[]>(() =>
    listDrafts(projectId),
  );
  const [instance, setInstance] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    loadInstance()
      .then((id) => {
        if (alive) setInstance(id);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [loadInstance]);
  return (
    <details className="local-draft-manager">
      <summary>本机草稿（{drafts.length}）</summary>
      <p>
        本机草稿只保存在当前浏览器中，用于页面关闭或保存失败后找回文字；不是已保存正文，不属于服务器备份，也不会发送给模型。清除浏览器数据会删除它们。
      </p>
      {drafts.length === 0 ? <p>这本小说当前没有本机草稿。</p> : null}
      <ul>
        {drafts.map(({ key, draft }) => {
          const title =
            chapterTitles.get(draft.chapterId) ?? draft.chapterTitle;
          return (
            <li key={key}>
              <p>
                {title || "未命名章节"} ·{" "}
                {new Date(draft.updatedAt).toLocaleString("zh-CN")} ·{" "}
                {draft.content.length} 字符 ·{" "}
                {instance === null
                  ? "正在核对数据根"
                  : draft.instance === instance
                    ? "本数据根"
                    : "其他数据根（不会自动套用）"}
              </p>
              <button
                type="button"
                onClick={() =>
                  downloadText(
                    draftFilename(title, draft.updatedAt),
                    draft.content,
                  )
                }
              >
                下载
              </button>
              {confirming === key ? (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      removeDraft(key);
                      setDrafts((items) =>
                        items.filter((item) => item.key !== key),
                      );
                      setConfirming(null);
                    }}
                  >
                    确认清理
                  </button>
                  <button type="button" onClick={() => setConfirming(null)}>
                    取消
                  </button>
                </>
              ) : (
                <button type="button" onClick={() => setConfirming(key)}>
                  清理
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
