# 当前交付

更新：2026-10-21。[长篇记忆与评审 RF-11–14 / #30](https://github.com/King70404/AI-Writer-project/issues/30) 已通过 [PR #31](https://github.com/King70404/AI-Writer-project/pull/31) 合并。当前阶段 RF-15–17（分支 `feature/rf15-17-backup-longform-release`）：RF-15 作者备份/校验/恢复、RF-16 十万字规模评测与 RF-17 发布验收准备均已在 Linux 与 Windows 本地完成，并通过 Windows 完整质量门禁（代码 `a9d4db1`）；A18/A19 作者评估与外部发布动作仍待作者决定，见 [发布验收](docs/RELEASE_ACCEPTANCE.md)。**未授权任何外部发布动作**（推送、PR、合并、tag、Release）。规则见 `AGENTS.md`。

## 当前已交付能力

- 小说、设定、人物、卷章、正文自动保存、历史版本与 TXT 导出；受保护模型配置、冻结上下文、持久候选、作者确认采纳及逐段连续生成。
- 粘贴范文对照分析，作者确认不可变写作规则；章节重点、冲突、场景/节拍和关联资料进入生成上下文。见 [范文与规划](docs/REFERENCE_WRITING.md)。
- 原文引文及修订绑定的候选事实，由作者确认或驳回；召回同一小说中来源有效的前文确认事实，保存版本依据。
- 显式预览并发送一致性评审，提取候选事实和定向修改建议，接通既有改写、生成和作者采用；在章节内统一操作。
- 正文、事实、卷章顺序变化后，提示需要复核的事实、评审和已有生成任务涉及的章节；既有任务快照保持不变。操作与预算见 [长篇记忆与评审](docs/LONGFORM_MEMORY.md)。
- 0006/0007/0008 旧库可由作者显式备份验证后升级至 0009，保留已有创作及协作数据；普通启动不迁移旧库。
- RF-15（未合并，Windows 已实测）：“数据备份”页面与 `scripts/author_backup.ps1` 创建并全量校验作者数据库备份、下载 ZIP，恢复只生成独立新数据根，不覆盖当前数据；不含模型配置与 Key。见 [作者备份与恢复](docs/AUTHOR_BACKUP.md)。
- RF-16（未合并，Windows 已实测）：`scripts/longform_eval.ps1` 在自有隔离目录构建 48 章约 11.3 万字合成样本并接本地假模型，测量持久化、召回、变更影响、备份恢复、性能与调用计量；不代表文学质量、真实模型费用、Windows 性能或百万字一致性。见 [长篇规模评测](docs/LONGFORM_EVALUATION.md)。

## 最新有效证据

Windows 验收代码 `a9d4db1f13c8ee6906bb16accadf101237567049`，Git 树 `403450737ea1f5df8b3d736d6b1ca5add8d46c78`（A1 门禁实际执行的工作树）；分支 `feature/rf15-17-backup-longform-release`。Windows 结果详见 [发布验收 §5](docs/RELEASE_ACCEPTANCE.md#5-windows-结果记录)，日志 `.runtime/rf17-*.log`（Git 忽略）。

完整 `scripts/quality_gate.ps1 -IncludeE2E`（Windows 11、pwsh 7.6.7）PASS，退出码 0，用时 21.1 分钟：后端 3,146 项通过、语句覆盖 96.62%；前端 864 项，语句/分支/函数/行 94.46%/90.40%/95.65%/95.44%；26 个浏览器场景（E2E-DEV-001–003、E2E-INT-001–022、E2E-STARTUP-001）及清理复核通过，含 E2E-INT-019（DPAPI 旧库升级）与 E2E-INT-022（备份/校验/下载/恢复）；ruff、mypy 234 文件、格式、lint、构建、依赖、安全及架构边界均通过。

Windows 脚本实测：启动烟测 Development/Integrated 均 PASS；隔离真实启动器作者流程（新建小说→写正文自动保存→备份→校验→下载→恢复到新副本→同名非空 409 拒绝→以恢复副本启动核对正文一致）PASS；`author_backup.ps1` create/list/verify/restore PASS（1 部小说/1 章/2 个正文版本，恢复副本 24 张业务表 13 行逻辑一致）；`longform_eval.ps1` small/full 均 PASS，full 13/13 阈值、33.2 秒、112,847 个非空白字符、数据库 10.0 MB、备份 ZIP 0.65 MB、48 章工作台读取 p95 154.9 ms。Windows 上 `resource` 模块不可用，未采集峰值 RSS；峰值内存数字仅来自先前的 Linux 实测（118 MiB）。

Windows 验收修复两处真实兼容问题（代码 `a9d4db1`）：`author_backup.ps1` 在 pwsh 7 下用 `$null` 清除 `AIWEBNOVEL_DATABASE_URL` 会留下空字符串，备份 CLI 因此返回 `CONFIGURATION_UNAVAILABLE`，改用 `[NullString]::Value`；备份恢复符号链接测试在无 `SeCreateSymbolicLinkPrivilege` 的账户下无法创建 symlink（WinError 1314），按 reparse point 语义回退到目录 junction，断言强度不变。

## 活动工作：RF-15–17（Windows 本地验收完成，待作者评估与授权）

Windows 本地证据（分支尚未推送，非共享事实；代码 `a9d4db1`）：

- A1：完整门禁 PASS（详见上节）；A7（E2E-INT-019 DPAPI）、A8（数据库验后检查、E2E 清理复核）、A9（PowerShell 卫生/安全/启动检查）随 A1 通过；A2–A6 由 A1 在同树复核。
- A10：`check_startup_runtime.ps1 -Mode Development` 与 `-Mode Integrated` 均通过（browser_ready、controlled_stop、sentinel_protection、ports_released）。
- A11：以子进程专用 `LOCALAPPDATA` 运行根 `启动 AI 网文助手.cmd`，受控 Chromium 完成创建小说、写正文自动保存、备份、校验、下载 ZIP、恢复为新副本、同名非空目标 409 拒绝；再以 `start_integrated.ps1 -DataRoot <恢复目录>` 启动核对小说与正文完全一致；结束端口释放、隔离目录清理。
- A12：`author_backup.ps1` 首次真实运行 create/list/verify/restore 通过；恢复副本与源库逻辑一致（24 张业务表、13 行、正文 SHA-256 相同、完整性与外键检查通过）。
- A13：`longform_eval.ps1` small/full 真实运行 PASS；full 13/13 阈值、墙钟 33.2 s、48 章 112,847 非空白字符、数据库 10.0 MB、ZIP 0.65 MB；Windows 未采集峰值 RSS（LE-13 内存项无实测值，不作为已测内存声明）。
- A14/A15：升级与备份恢复保护已有正文与确认事实、评测按预登记阈值输出，已随上述 Windows 运行复核。

待办阻断：A18（小说文学质量）与 A19（真实付费模型输出质量与实际费用）需作者评估；A20 推送/合并/tag/Release 仍需作者明确授权。召回有数量和字符预算，不宣称全书事实全覆盖或百万字一致性。

## 必须守住

测试仅用自有隔离根，不读取、迁移或枚举正式 `%LOCALAPPDATA%\AIWebNovel` 作者数据、备份或真实 Key。运行时 AI 不自动确认事实、规则或采纳正文。不降低测试/coverage，不静音错误，不改 M0–M7 tags 与 24 份冻结文件。GitHub 同步状态是共同事实源，详细证据保留在对应任务。
