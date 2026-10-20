# 作者备份、校验与恢复（RF-15）

本页是产品内作者备份的契约：备份包含什么、怎样校验、恢复遵守哪些规则，以及界面、HTTP 和命令行入口。实现位于 `backend/src/aiwebnovel/backup/`，识别的数据库版本与显式升级共用 `backend/src/aiwebnovel/db/author_schema.py`。当前交付状态以 [PLAN.md](../PLAN.md) 为准。

## 备份包含什么

一个备份是数据根 `backups/` 下的一个 ZIP 文件，名称固定为 `aiwebnovel-backup-<备份ID>.zip`，备份 ID 形如 `20261020T091500Z-0123456789ab`（UTC 时间加 12 位随机十六进制）。ZIP 内恰好两个成员：

| 成员 | 内容 |
| --- | --- |
| `aiwebnovel.sqlite3` | 作者数据库的一致快照：小说、设定、人物、卷章、正文及全部历史版本、候选与已确认事实、一致性评审、范文与写作规则、章节规划、AI 任务记录 |
| `manifest.json` | 格式名 `aiwebnovel-author-backup`、格式版本 `1`、备份 ID、创建时间、应用版本、数据库 SHA-256 与字节数、数据库迁移版本、作者可见计数（小说、章节、正文版本、已确认事实、AI 任务），以及每张业务表的行数和按 rowid 排序的内容摘要 |

快照通过 SQLite 在线备份 API 在独立只读连接上一次性读取同一事务视图，不阻塞也不混入并发写入；快照切换为 rollback journal 模式，使校验和稳定。

### 明确不包含

- 模型配置（`config/` 下的 profiles）与 API Key：Key 由 Windows DPAPI 按用户保护，不随备份移动。恢复后的副本需要重新填写模型配置和 Key。
- `assets/`、`exports/`、`logs/`、`runtime/` 和其他备份文件。
- 任何本地绝对路径。错误信息与 HTTP 响应不包含路径或正文内容。

校验和用于发现损坏和不一致的修改，不是加密签名；备份文件本身未加密，作者应像保管正文一样保管它。

## 创建

创建会先校验数据布局（拒绝重解析点、符号链接或缺失的数据库），把快照写到 `runtime/temp/`，汇总并做完整性检查后写入 `backups/.<名称>.partial`，再对该文件执行与“校验”完全相同的全量验证，通过后才原子重命名为正式名称。任何一步失败都会删除临时文件，不留下半成品；当前数据库只被读取。创建、校验和恢复同一时刻只运行一个，并发请求返回 `BACKUP_BUSY`。

## 校验（verify）

依次检查，任一失败即判定：

1. ZIP 可读，且只有上述两个成员，无目录、无加密成员。
2. `manifest.json` 不超过 1 MiB，是 UTF-8 JSON，字段集合完全一致，格式名、备份 ID（与文件名一致）、时间、SHA-256、计数都严格合法。
3. 格式版本不是 `1`，或迁移版本不在识别范围（0006/0007/0008/0009）→ `incompatible`（`BACKUP_INCOMPATIBLE`）。
4. 数据库成员大小与清单一致，且不超过 8 GiB；解压时边读边计数，超过清单声明立即中止。
5. 解压后 SHA-256 与清单一致。
6. SQLite `PRAGMA integrity_check` 为 `ok`，`PRAGMA foreign_key_check` 无结果。
7. 数据库的表和列与其迁移版本完全一致，并与清单的迁移版本、计数和每表摘要逐一相同。

其余失败为 `corrupt`（`BACKUP_CORRUPT`）。列表只读取清单，不代表已通过校验；需要确认时执行“校验完整性”。

## 恢复规则

- **恢复从不写当前数据根。** 恢复总是生成一个独立的新数据根：目标必须是新文件夹或已存在的空文件夹，且与当前数据根互不包含。
- 目标的上级文件夹必须已存在。
- 恢复前完整校验备份；复制到目标 `data/aiwebnovel.sqlite3` 后，再次核对 SHA-256、完整性和全部表摘要。
- 失败时只删除本次恢复创建的数据库、侧文件和目录；已存在的空目标文件夹保留。
- 旧版本备份（0006/0007/0008）按原样恢复，摘要中 `requires_upgrade=true`；需要时在恢复出的副本上按 [AI 协作文档](AI_COLLABORATION.md) 的显式升级流程操作，普通启动不迁移旧库。
- 使用恢复出的副本：以该文件夹作为数据根启动集成应用（`start_integrated.ps1 -DataRoot <副本路径>`），确认无误后再由作者自行决定是否替换原数据。应用不提供“覆盖当前数据”的操作。

## 界面

主导航“数据备份”打开“备份与恢复”页面（`/backups`）：立即备份、列出已有备份及计数、逐个“校验完整性”、下载 ZIP、“恢复到新文件夹”。界面恢复只接受一个普通文件夹名（字母、数字、`_`、`.`、`-`，最长 64 字符，不能是 Windows 保留名），副本创建在当前数据根的同级目录；必须勾选“恢复会创建独立的新副本”后才可提交。

## HTTP 接口

所有接口位于 `/api/v1/backups`，响应 `Cache-Control: no-store`；写操作需要标准 Session/CSRF 与 JSON 请求体，严格拒绝多余字段。

| 方法与路径 | 请求体 | 成功 |
| --- | --- | --- |
| `GET /api/v1/backups` | — | 200，最新在前，最多 200 项 |
| `POST /api/v1/backups` | `{}` | 201，新备份及摘要 |
| `POST /api/v1/backups/{backup_id}/verify` | `{}` | 200，`status` 为 `valid`/`corrupt`/`incompatible` |
| `GET /api/v1/backups/{backup_id}/download` | — | 200，`application/zip` 附件 |
| `POST /api/v1/backups/{backup_id}/restore` | `{"target_name": "...", "confirm_new_copy": true}` | 200，副本文件夹名及摘要 |

错误码：`BACKUP_BUSY` 409（可重试）、`BACKUP_NOT_FOUND` 404、`BACKUP_UNAVAILABLE` 503、`RESTORE_TARGET_INVALID` 422、`RESTORE_TARGET_NOT_EMPTY` 409、`RESTORE_CONFIRMATION_REQUIRED` 422、`BACKUP_CORRUPT` 422、`BACKUP_INCOMPATIBLE` 409、其他 `BACKUP_FAILED` 503（当前数据不变）。当 `AIWEBNOVEL_DATABASE_URL` 指向受管数据根之外的数据库时，备份整体不可用。

## 命令行

从仓库根目录运行，必须显式给出数据根（没有默认值；测试与诊断只能传自有隔离根，作者备份正式数据时需明确传入自己的正式根）：

```powershell
.\scripts\author_backup.ps1 create  -DataRoot <数据根>
.\scripts\author_backup.ps1 list    -DataRoot <数据根>
.\scripts\author_backup.ps1 verify  -DataRoot <数据根> -BackupId <备份ID>
.\scripts\author_backup.ps1 restore -DataRoot <数据根> -BackupId <备份ID> -Target <新的绝对路径>
```

脚本校验数据根（绝对 Windows 路径、不与仓库重叠、不经过重解析点），清除 `AIWEBNOVEL_DATABASE_URL`，然后调用 `.venv/Scripts/python.exe -m aiwebnovel.backup`。输出一行 JSON；退出码 0 成功、1 被拒绝或失败、2 参数无效、3 备份损坏或不兼容。`-Target` 必须是绝对路径且不在仓库内。

## 限制

- 只备份 SQLite 作者数据库；单个数据库上限 8 GiB，列表最多显示 200 个备份。
- 不自动定时备份，不自动清理旧备份，不加密；下载后由作者自行保存到其他磁盘。
- 恢复不会替换当前数据根；切换到副本需作者手动以新数据根启动。
- 测试、E2E 和诊断只使用自有隔离数据根，不读取、枚举或恢复作者正式数据和正式备份。
