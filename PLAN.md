# 当前交付

更新：2026-10-20。[长篇记忆与评审 RF-11–14 / #30](https://github.com/King70404/AI-Writer-project/issues/30) 已通过 [PR #31](https://github.com/King70404/AI-Writer-project/pull/31) 合并。当前阶段 RF-15–17（分支 `feature/rf15-17-backup-longform-release`）：RF-15 作者备份/校验/恢复已在 Linux 本地完成，待 Windows 完整门禁；下一项 RF-16。规则见 `AGENTS.md`。

## 当前已交付能力

- 小说、设定、人物、卷章、正文自动保存、历史版本与 TXT 导出；受保护模型配置、冻结上下文、持久候选、作者确认采纳及逐段连续生成。
- 粘贴范文对照分析，作者确认不可变写作规则；章节重点、冲突、场景/节拍和关联资料进入生成上下文。见 [范文与规划](docs/REFERENCE_WRITING.md)。
- 原文引文及修订绑定的候选事实，由作者确认或驳回；召回同一小说中来源有效的前文确认事实，保存版本依据。
- 显式预览并发送一致性评审，提取候选事实和定向修改建议，接通既有改写、生成和作者采用；在章节内统一操作。
- 正文、事实、卷章顺序变化后，提示需要复核的事实、评审和已有生成任务涉及的章节；既有任务快照保持不变。操作与预算见 [长篇记忆与评审](docs/LONGFORM_MEMORY.md)。
- 0006/0007/0008 旧库可由作者显式备份验证后升级至 0009，保留已有创作及协作数据；普通启动不迁移旧库。
- RF-15（未合并）：“数据备份”页面与 `scripts/author_backup.ps1` 创建并全量校验作者数据库备份、下载 ZIP，恢复只生成独立新数据根，不覆盖当前数据；不含模型配置与 Key。见 [作者备份与恢复](docs/AUTHOR_BACKUP.md)。

## 最新有效证据

验收代码 `098e6f6be3da8c9ed8b7eb9a5c2fdfa047e518a6`，Git 树 `a28903899fd88e3cef949ec3488f4ad60e2f1a9a`；合并提交 `277ac0ea8ad11824cf38856aa6757bf39721c079` 的树完全一致。[完整证据](https://github.com/King70404/AI-Writer-project/issues/30#issuecomment-6232003816) 已同步。

完整 `scripts/quality_gate.ps1 -IncludeE2E` PASS，退出码 0，日志 `.runtime/memory-quality-full-3.log`：后端 3038 项，语句/分支 97.28%/92.27%；前端 809 项，94.29%/90.21%；25 个浏览器场景及清理通过。mypy 227 文件、格式、lint、构建、依赖、安全及架构边界均通过。

E2E-INT-021 用时 5.8 秒，三次受控真实 HTTP 调用贯通跨章事实、评审、改写、作者采用和来源失效；不代表付费 DeepSeek 或长篇文学质量实测。[GitHub 源码检查](https://github.com/King70404/AI-Writer-project/actions/runs/39019225397) 在本次状态更新时仍运行中，尚未记录远端 PASS。仅状态文档更新复用有效本地证据。

## 活动工作：RF-15–17

RF-15 Linux 本地证据（分支未推送，非共享事实）：后端 3049 通过，85 项失败均为既有 Windows 专属用例（powershell.exe、Windows 路径、SO_EXCLUSIVEADDRUSE），与基线失败集合一致，语句/分支 97.20%/92.37%；新增架构脚本检查 3 项通过；前端 `npm run quality` 864 项，94.46%/90.40%；ruff、mypy --platform win32、security AST、安全基线与仓库卫生规则的 Python 移植扫描通过。隔离服务上 21 个集成场景（E2E-INT-001–018、020–022）通过；E2E-INT-019 保存云模型 Key 需 Windows DPAPI，Linux 上按设计返回 503。开发模式、缺失构建场景及 PowerShell 数据库验后检查未在 Linux 运行。

待办阻断：作者 Windows 机器运行 `scripts/quality_gate.ps1 -IncludeE2E`（26 个场景、PowerShell 检查与数据库验后检查）后记录精确 SHA，再推送/开 PR。下一项 RF-16：十万字规模写作质量、稳定性与费用验证，随后 RF-17 发布验收。召回有数量和字符预算，不宣称全书事实全覆盖或百万字一致性。

## 必须守住

测试仅用自有隔离根，不读取、迁移或枚举正式 `%LOCALAPPDATA%\AIWebNovel` 作者数据、备份或真实 Key。运行时 AI 不自动确认事实、规则或采纳正文。不降低测试/coverage，不静音错误，不改 M0–M7 tags 与 24 份冻结文件。GitHub 同步状态是共同事实源，详细证据保留在对应任务。
