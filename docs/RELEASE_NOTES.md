# 发布说明

每个候选一节，最新在上。版本号仍为 `0.0.0`（后端 `pyproject.toml`/`__version__`、前端 `package.json` 均未建立发版约定，本候选不升版本）。验收状态见 [发布验收](RELEASE_ACCEPTANCE.md)。

## RF-15–17 候选（分支 `feature/rf15-17-backup-longform-release`，未合并、未发布）

代码候选 `9739c78`（RF-17 只增加文档）。本节描述候选内容，不代表已经发布或已通过 Windows 正式门禁；未经作者明确授权不创建 GitHub Release、tag 或推送。

### 新增

- **作者备份、校验与恢复（RF-15）**：“数据备份”页面与 `scripts/author_backup.ps1` 对作者数据库做一致快照，生成 `aiwebnovel-backup-<ID>.zip`（数据库 + `manifest.json`：SHA-256、迁移版本、作者可见计数及每表行数/内容摘要）。创建后立即全量校验才落盘；可随时“校验完整性”、下载 ZIP。恢复只写入新的或空的独立数据根，永不覆盖当前数据。契约见 [作者备份与恢复](AUTHOR_BACKUP.md)；浏览器场景 `E2E-INT-022`。
- **十万字规模评测（RF-16）**：`scripts/longform_eval.ps1`（Linux 为 `scripts/longform_eval.py`）在自有隔离目录生成确定性 48 章约 11.3 万字合成样本，接本地假模型，按预登记 13 项阈值测量持久化、召回、变更影响、备份恢复、性能和调用计量。Linux 首次完整运行 13/13 PASS。见 [长篇规模评测](LONGFORM_EVALUATION.md)。
- **发布验收（RF-17）**：[发布验收清单与报告](RELEASE_ACCEPTANCE.md) 及本说明。

### 已知限制

- 备份不含模型配置与 API Key（DPAPI 按用户保护），恢复后需重新填写；备份未加密，不自动定时、不自动清理；单库上限 8 GiB，列表最多 200 个；切换到恢复副本需作者手动以新数据根启动。
- 评测样本是无文学价值的合成文本：**不证明小说文学质量**；未调用真实付费模型，token 为估算、未算货币费用；未覆盖百万字、Windows 性能/DPAPI、十万字下浏览器渲染及多会话并发。召回为确定性二元组关联，有数量和字符预算，不承诺全书事实覆盖。
- 本候选的 Windows 完整门禁（`quality_gate.ps1 -IncludeE2E`、26 个浏览器场景含 DPAPI 的 `E2E-INT-019`、PowerShell 安全/启动检查、隔离真实启动器作者流程、两个新脚本的首次真实运行）尚未执行。

### 升级与兼容

- 无新数据库迁移（仍为 0009）；0006/0007/0008 旧库仍需作者显式备份验证后升级，普通启动不迁移。
- 新增 HTTP 接口仅限备份域，沿用既有 loopback、Host、Origin、Session、CSRF 边界。
