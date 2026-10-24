import { useState } from "react";

import { downloadText, draftFilename, type StoredDraft } from "./drafts";
import type { InstanceState } from "./useLocalDraft";
import { VersionComparison } from "./VersionComparison";

function when(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

/**
 * 重开章节时发现的本机草稿。只提供比较、恢复到编辑区、下载和丢弃；恢复后仍须经过
 * 正常保存（带版本条件），即使基线相同也不自动写回服务器。
 */
export function LocalDraftRecovery({
  instance,
  storageError,
  recoverable,
  foreign,
  savedContent,
  savedRevisionId,
  canRestore,
  onRestore,
  onDiscard,
  onDismiss,
}: {
  readonly instance: InstanceState;
  readonly storageError: boolean;
  readonly recoverable: readonly StoredDraft[];
  readonly foreign: number;
  readonly savedContent: string;
  readonly savedRevisionId: string;
  readonly canRestore: boolean;
  readonly onRestore: (content: string) => void;
  readonly onDiscard: (key: string) => void;
  readonly onDismiss: (key: string) => void;
}) {
  const [comparing, setComparing] = useState<string | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState<string | null>(null);
  return (
    <>
      {storageError ? (
        <p role="alert">
          本机草稿未能保存（浏览器存储不可用或空间不足），不能依赖它恢复。请先保存正文，或用“下载本地副本”留存。
        </p>
      ) : null}
      {instance.status === "unavailable" ? (
        <p className="local-draft__note">
          暂时无法核对本机数据根，本页不保存本机草稿；正文仍按原方式自动保存。
        </p>
      ) : null}
      {foreign ? (
        <p className="local-draft__note">
          另有 {foreign}{" "}
          份来自其他数据根（例如恢复副本或旧数据目录）的本机草稿，不会套用到本章；可在作品结构页的“本机草稿”中下载或清理。
        </p>
      ) : null}
      {recoverable.map(({ key, draft }) => (
        <section
          key={key}
          aria-label="可恢复的本机草稿"
          className="local-draft"
        >
          <p>
            发现本章的本机草稿（{when(draft.updatedAt)}，{draft.content.length}{" "}
            字符），与服务器已保存的正文不同。
            {draft.baseRevisionId === savedRevisionId
              ? "它基于当前服务器版本。"
              : "它基于较早的服务器版本，服务器之后已有新保存；两份都会保留供比较。"}
            草稿只在本机浏览器中，不属于服务器备份，清除浏览器数据会删除它。
          </p>
          <button
            type="button"
            aria-expanded={comparing === key}
            onClick={() =>
              setComparing((value) => (value === key ? null : key))
            }
          >
            {comparing === key ? "收起比较" : "比较草稿与已保存正文"}
          </button>
          <button
            type="button"
            disabled={!canRestore}
            onClick={() => {
              onRestore(draft.content);
              onDismiss(key);
            }}
          >
            恢复到编辑区
          </button>
          <button
            type="button"
            onClick={() =>
              downloadText(
                draftFilename(draft.chapterTitle, draft.updatedAt),
                draft.content,
              )
            }
          >
            下载本地副本
          </button>
          {confirmDiscard === key ? (
            <>
              <button type="button" onClick={() => onDiscard(key)}>
                确认丢弃此草稿
              </button>
              <button type="button" onClick={() => setConfirmDiscard(null)}>
                取消
              </button>
            </>
          ) : (
            <button type="button" onClick={() => setConfirmDiscard(key)}>
              丢弃此草稿
            </button>
          )}
          {!canRestore ? (
            <p>
              编辑区有未保存或冲突的内容，先处理后才能恢复草稿；可先下载或比较。
            </p>
          ) : (
            <p>恢复只放入编辑区，之后照常保存（带版本检查）才会写入服务器。</p>
          )}
          {comparing === key ? (
            <VersionComparison
              label="本机草稿与已保存正文对照"
              leftLabel="服务器已保存正文"
              rightLabel="本机草稿"
              left={savedContent}
              right={draft.content}
            />
          ) : null}
        </section>
      ))}
    </>
  );
}
