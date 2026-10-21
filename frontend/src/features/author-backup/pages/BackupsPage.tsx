import { BackupManager } from "../components/BackupManager";

export function BackupsPage() {
  return (
    <section className="backups-page" aria-labelledby="backups-page-title">
      <p className="section-kicker">数据安全</p>
      <h2 id="backups-page-title">备份与恢复</h2>
      <p>
        备份保存在本机数据文件夹的 backups 中。恢复只会创建一个全新的独立副本，
        绝不覆盖当前正在使用的创作数据。
      </p>
      <BackupManager />
    </section>
  );
}
