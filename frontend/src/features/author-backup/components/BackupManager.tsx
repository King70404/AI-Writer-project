import { useEffect, useState } from "react";

import {
  backupClient,
  backupErrorMessage,
  isPlainFolderName,
  type BackupItem,
  type BackupRestore,
  type BackupSummary,
  type BackupVerification,
} from "../api/backups";
import { formatBytes, formatCreatedAt } from "../formatting";

export type BackupClient = typeof backupClient;

const VERIFICATION_TEXT: Readonly<
  Record<BackupVerification["status"], string>
> = {
  valid: "校验通过：备份完整，正文、历史、确认事实与任务记录都与备份清单一致。",
  corrupt: "校验失败：备份已损坏或被修改，不能用于恢复。请改用其他备份。",
  incompatible: "该备份来自不兼容的版本，当前版本不能恢复它。",
};

function SummaryFacts({ summary }: { readonly summary: BackupSummary }) {
  const { counts } = summary;
  return (
    <p>
      {counts.projects} 部小说 · {counts.chapters} 章 ·{" "}
      {counts.chapter_revisions} 个正文历史版本 · {counts.confirmed_facts}{" "}
      条已确认事实 · {counts.workflow_runs} 个 AI 任务
      {summary.requires_upgrade ? " · 旧版数据，恢复后需在副本中显式升级" : ""}
    </p>
  );
}

function RestoreForm({
  item,
  client,
  onRestored,
}: {
  readonly item: BackupItem;
  readonly client: BackupClient;
  readonly onRestored: (result: BackupRestore) => void;
}) {
  const [name, setName] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const trimmed = name.trim();
  const nameValid = isPlainFolderName(trimmed);
  const inputId = `restore-name-${item.backup_id}`;
  const confirmId = `restore-confirm-${item.backup_id}`;

  const restore = async () => {
    if (!nameValid || !confirmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      onRestored(await client.restore(item.backup_id, trimmed));
    } catch (reason) {
      setError(backupErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="backup-restore">
      <div className="form-field">
        <label htmlFor={inputId}>新副本文件夹名称</label>
        <input
          id={inputId}
          type="text"
          autoComplete="off"
          maxLength={64}
          value={name}
          aria-invalid={trimmed.length > 0 && !nameValid}
          aria-describedby={`${inputId}-hint`}
          onChange={(event) => setName(event.target.value)}
          disabled={busy}
        />
        <p className="field-count" id={`${inputId}-hint`}>
          副本会建在当前数据文件夹旁边的新文件夹中；已有且非空的文件夹会被拒绝。
        </p>
        {trimmed.length > 0 && !nameValid ? (
          <p className="field-error">
            只用文字、数字、点、短横线或下划线，不能以点或短横线开头或结尾。
          </p>
        ) : null}
      </div>
      <label htmlFor={confirmId} className="backup-restore__confirm">
        <input
          id={confirmId}
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
          disabled={busy}
        />{" "}
        我了解：恢复会创建独立的新副本，不会覆盖或修改当前创作数据。
      </label>
      <button
        type="button"
        onClick={() => void restore()}
        disabled={!nameValid || !confirmed || busy}
      >
        {busy ? "正在校验并恢复…" : "恢复为新副本"}
      </button>
      {error === null ? null : <p role="alert">{error}</p>}
    </div>
  );
}

function BackupRow({
  item,
  client,
  onRestored,
}: {
  readonly item: BackupItem;
  readonly client: BackupClient;
  readonly onRestored: (result: BackupRestore) => void;
}) {
  const [verifying, setVerifying] = useState(false);
  const [verification, setVerification] = useState<BackupVerification | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);

  const verify = async () => {
    setVerifying(true);
    setError(null);
    try {
      setVerification(await client.verify(item.backup_id));
    } catch (reason) {
      setError(backupErrorMessage(reason));
    } finally {
      setVerifying(false);
    }
  };
  const label = formatCreatedAt(item.created_at);

  return (
    <li className="backup-card" aria-label={`备份 ${label}`}>
      <h4>{label}</h4>
      <p>文件大小：{formatBytes(item.file_bytes)}</p>
      {item.summary === null ? (
        <p>无法读取备份清单，该文件可能已损坏。</p>
      ) : (
        <SummaryFacts summary={item.summary} />
      )}
      <div className="backup-card__actions">
        <button
          type="button"
          onClick={() => void verify()}
          disabled={verifying}
        >
          {verifying ? "正在校验…" : "校验完整性"}
        </button>
        {item.readable ? (
          <a href={client.downloadUrl(item.backup_id)} download>
            下载备份
          </a>
        ) : null}
        {item.readable ? (
          <button
            type="button"
            aria-expanded={restoring}
            onClick={() => setRestoring((value) => !value)}
          >
            {restoring ? "取消恢复" : "恢复到新文件夹"}
          </button>
        ) : null}
      </div>
      {verification === null ? null : (
        <p role="status">{VERIFICATION_TEXT[verification.status]}</p>
      )}
      {error === null ? null : <p role="alert">{error}</p>}
      {restoring ? (
        <RestoreForm item={item} client={client} onRestored={onRestored} />
      ) : null}
    </li>
  );
}

export function BackupManager({
  client = backupClient,
}: {
  readonly client?: BackupClient;
}) {
  const [items, setItems] = useState<readonly BackupItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [restored, setRestored] = useState<BackupRestore | null>(null);

  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    let active = true;
    client.list().then(
      (listed) => {
        if (active) setItems(listed);
      },
      (reason: unknown) => {
        if (active) setLoadError(backupErrorMessage(reason));
      },
    );
    return () => {
      active = false;
    };
  }, [client, reloads]);

  const reload = () => {
    setLoadError(null);
    setReloads((value) => value + 1);
  };

  const create = async () => {
    setCreating(true);
    setNotice(null);
    setActionError(null);
    try {
      const created = await client.create();
      setNotice(
        `已创建并校验备份（${formatCreatedAt(created.created_at)}）。建议下载一份保存到其他磁盘。`,
      );
      reload();
    } catch (reason) {
      setActionError(backupErrorMessage(reason));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="backup-manager">
      <section aria-labelledby="backup-create-title">
        <h3 id="backup-create-title">创建备份</h3>
        <p>
          备份包含全部小说、设定、人物、卷章、正文及历史版本、已确认事实、范文与规划，以及
          AI 任务和候选。备份在写作时也能安全进行，完成后会自动校验。模型配置和
          API Key 不包含在备份中。
        </p>
        <button type="button" onClick={() => void create()} disabled={creating}>
          {creating ? "正在备份并校验…" : "立即备份"}
        </button>
        {notice === null ? null : <p role="status">{notice}</p>}
        {actionError === null ? null : <p role="alert">{actionError}</p>}
      </section>

      {restored === null ? null : (
        <section aria-labelledby="backup-restored-title" role="status">
          <h3 id="backup-restored-title">已恢复为独立副本</h3>
          <p>
            副本位于当前数据文件夹旁边的“{restored.target_name}
            ”文件夹，恢复后已再次校验。当前创作数据没有任何改变。
          </p>
          <SummaryFacts summary={restored.summary} />
          <p>
            如需打开副本，请在仓库根目录运行 start_integrated.ps1，并用
            -DataRoot 指向该文件夹；不要把副本复制回当前数据文件夹。
          </p>
        </section>
      )}

      <section aria-labelledby="backup-list-title">
        <h3 id="backup-list-title">已有备份</h3>
        {loadError !== null ? (
          <div role="alert">
            <p>{loadError}</p>
            <button type="button" onClick={reload}>
              重新加载
            </button>
          </div>
        ) : items === null ? (
          <p role="status">正在读取备份列表…</p>
        ) : items.length === 0 ? (
          <p>还没有备份。建议在大量修改前先备份一次。</p>
        ) : (
          <ul className="backup-list">
            {items.map((item) => (
              <BackupRow
                key={item.backup_id}
                item={item}
                client={client}
                onRestored={setRestored}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
