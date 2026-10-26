import { useState } from "react";

import { downloadText, draftFilename } from "../../local-drafts/drafts";
import { VersionComparison } from "../../local-drafts/VersionComparison";

/**
 * 保存时发现服务器版本已变化（WF-06）。先提供保留本地副本，再比较两份正文；替换任何
 * 一方都需作者明确确认，不自动合并，也不按最后写入覆盖。
 */
export function ConflictResolution({
  chapterTitle,
  localContent,
  disabled,
  loadServer,
  onKeepLocal,
  onReloadServer,
}: {
  readonly chapterTitle: string;
  readonly localContent: string;
  readonly disabled: boolean;
  readonly loadServer: () => Promise<string>;
  readonly onKeepLocal: () => Promise<boolean>;
  readonly onReloadServer: () => void;
}) {
  const [server, setServer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [confirmKeep, setConfirmKeep] = useState(false);
  const [confirmReload, setConfirmReload] = useState(false);
  const compare = async () => {
    setLoading(true);
    setFailed(false);
    try {
      setServer(await loadServer());
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };
  return (
    <div role="alert" className="conflict-resolution">
      <p>
        服务器上的章节已在其他窗口或标签页发生变化，当前内容尚未覆盖服务器版本。请先保留本地副本，再比较后决定。
      </p>
      <button
        type="button"
        onClick={() =>
          downloadText(
            draftFilename(chapterTitle, new Date().toISOString()),
            localContent,
          )
        }
      >
        下载本地副本
      </button>
      <button
        type="button"
        disabled={disabled || loading}
        onClick={() => void compare()}
      >
        {loading ? "正在读取服务器版本…" : "比较服务器版本"}
      </button>
      {failed ? <p>服务器版本暂未读取，本地正文仍保留，可稍后重试。</p> : null}
      {server !== null ? (
        <VersionComparison
          label="服务器版本与本地正文对照"
          leftLabel="服务器版本"
          rightLabel="本地正文"
          left={server}
          right={localContent}
        />
      ) : null}
      <label>
        <input
          type="checkbox"
          checked={confirmKeep}
          disabled={disabled}
          onChange={(event) => setConfirmKeep(event.target.checked)}
        />
        我已比较，确认用本地正文替换服务器上的新版本
      </label>
      <button
        type="button"
        disabled={disabled || !confirmKeep}
        onClick={() => void onKeepLocal()}
      >
        保留本地正文并保存
      </button>
      <label>
        <input
          type="checkbox"
          checked={confirmReload}
          disabled={disabled}
          onChange={(event) => setConfirmReload(event.target.checked)}
        />
        我已保留需要的文字，确认丢弃本地正文
      </label>
      <button
        type="button"
        disabled={disabled || !confirmReload}
        onClick={onReloadServer}
      >
        丢弃本地正文并重新加载服务器版本
      </button>
    </div>
  );
}
