# RF-17 发布验收清单与报告

本页是 RF-15–17 候选（分支 `feature/rf15-17-backup-longform-release`）的发布验收入口：列出发布前必须满足的要求、每项当前状态和证据，以及 Windows 执行与记录方法。规则来源：[交付路线](REFRACTOR_ROADMAP.md) 阶段 5、[稳定性协议](ACCEPTANCE_STABILITY.md)、[质量门禁](QUALITY_GATES.md)、[浏览器端到端测试](E2E_TESTING.md)、[Windows CI](CI.md) 与 `AGENTS.md`。候选内容与限制见 [发布说明](RELEASE_NOTES.md)。

> 路线定义：候选满足发布验收和交付要求。**测试通过不等于已经证明小说质量，发布验收通过也不自动授权未批准的外部发布动作。** 本页任何 PASS 都不授权推送、合并、打 tag、创建 GitHub Release 或分发安装包；这些动作需要作者另行明确授权。

## 1. 候选与结论

| 项 | 值 |
| --- | --- |
| 代码候选 | `9739c78`（RF-15/16 全部代码；RF-17 只增加本页、发布说明与 PLAN 文档） |
| Linux 验证所用树 | `9739c78` 的树 `cf19626`（RF-17 文档提交前），详见 §4 |
| 版本号 | `0.0.0`，不升版本：后端 `pyproject.toml`/`aiwebnovel.__version__`、前端 `package.json` 与 E2E 启动环境都固定为 `0.0.0`，仓库没有 CHANGELOG、release 工作流或发版约定 |
| 交付形态 | 源码仓库 + 根目录 `启动 AI 网文助手.cmd`（复用 `scripts/start_integrated.ps1`，提供 `frontend/dist`）；仓库无安装器或打包步骤，CI 只读，不写 release |
| 当前总结论 | **未完成：Linux 部分 PASS，Windows 门禁与作者评估待执行。** 不得合并或发布 |

## 2. 验收清单

状态：**PASS-Linux**＝已在 Linux 沙箱实测通过（附证据）；**PENDING-Windows**＝必须在作者 Windows 机器（或 Windows hosted Full）上对精确 SHA 执行；**PENDING-作者**＝只有作者能判断或授权。

| # | 要求 | 来源 | 状态 | 证据 / 说明 |
| --- | --- | --- | --- | --- |
| A1 | `quality_gate.ps1 -IncludeE2E`（已含 Default：diff/卫生/安全/启动安全/ruff/mypy/后端+覆盖率/pip check/前端 quality/npm ls + 26 个 E2E + 清理）一次通过 | 稳定性协议 §一次完整交付 2 | PENDING-Windows | 需 pwsh、Windows Python 3.12.10、Node 24 |
| A2 | 后端测试与覆盖率（语句 ≥ 80%、分支 ≥ 75%） | QUALITY_GATES | PASS-Linux（部分） | `9739c78`：3060 通过、1 跳过；85 项失败均为既有 Windows 专属用例（powershell.exe、Windows 路径、SO_EXCLUSIVEADDRUSE），与基线集合一致；97.22% / 92.40%，`check_backend_coverage.py` 通过。85 项须在 A1 中于 Windows 通过 |
| A3 | ruff format/lint、mypy（win32 平台）、安全 AST | QUALITY_GATES | PASS-Linux | §4 |
| A4 | 前端 `npm run quality`（格式、lint、类型、测试+覆盖率 80/75/80/80、构建） | QUALITY_GATES | PASS-Linux | §4（Node 22，Windows 门禁要求 Node 24，A1 复核） |
| A5 | 生产集成 E2E：E2E-INT-001–018、020–022（含 RF-15 的 `E2E-INT-022`） | E2E_TESTING | PASS-Linux | §4；Linux 等效运行器逐场景隔离启动，非 `run_e2e.ps1` |
| A6 | 开发模式 E2E-DEV-001–003、缺失构建 E2E-STARTUP-001 | E2E_TESTING | PASS-Linux | §4；Linux 等效运行，正式结论仍以 A1 为准 |
| A7 | `E2E-INT-019`（0006 旧库升级 + DPAPI 受保护模型 Key） | E2E_TESTING | PENDING-Windows | Linux 无 DPAPI，模型配置保存按设计返回 503 |
| A8 | `run_e2e.ps1` 的数据库验后检查（INT-008–016 计数/修订/删除标记）与 `check_e2e_cleanup.ps1` 端口/目录清理复核 | E2E_TESTING | PENDING-Windows | PowerShell 实现，A1 内执行 |
| A9 | `check_repository_hygiene.ps1`、`check_security_baseline.ps1`、`check_startup_safety.ps1` | QUALITY_GATES | PENDING-Windows | A1 内执行；Linux 只运行了其 Python 部分 `check_security_ast.py` |
| A10 | `check_startup_runtime.ps1 -Mode Development` / `-Mode Integrated` 启动烟测 | E2E_TESTING | PENDING-Windows | 单独运行 |
| A11 | 隔离真实启动器作者流程：子进程专属 `LOCALAPPDATA` 下运行根 `启动 AI 网文助手.cmd`，受控浏览器绑定该 URL 完成创作→保存→**备份→校验→下载→恢复到新目录**→以恢复副本启动核对 | 稳定性协议 §仍必须验证的行为 | PENDING-Windows | 窗口标题、退出码或 HTTP 200 不能替代 |
| A12 | `scripts/author_backup.ps1` 首次真实运行（create/list/verify/restore，隔离根） | AUTHOR_BACKUP | PENDING-Windows | Python 模块 `aiwebnovel.backup` 已由后端测试与 E2E-INT-022 覆盖 |
| A13 | `scripts/longform_eval.ps1` 首次真实运行（至少 `-Scale small`；建议 `full` 记录 Windows 性能） | LONGFORM_EVALUATION | PENDING-Windows | Linux `--scale full` 13/13 PASS（测量提交 `90876e3`） |
| A14 | 升级与备份恢复保护已有正文与确认事实（自有隔离数据） | 路线阶段 5 完成定义 | PASS-Linux | 后端备份/升级测试、E2E-INT-022、RF-16 LE-08（25 表 723 行逐行一致） |
| A15 | 长篇评测按预登记样本/长度/质量/成本标准输出证据与限制 | 路线阶段 5 完成定义 | PASS-Linux（软件行为） | [评测 §6](LONGFORM_EVALUATION.md)；限制见 §4 |
| A16 | 浏览器无未解释 React warning、console.error、pageerror、requestfailed | 稳定性协议 | PASS-Linux（A5 范围） | 由 E2E 网络守卫/审计断言强制 |
| A17 | 数据与 Git 边界：无正式数据访问，M0–M7 tag 与 24 份冻结文件未改，工作区无未跟踪产物 | AGENTS | PASS-Linux | §4 |
| A18 | 小说文学质量（情节、文笔、人物一致性） | 路线定义 | PENDING-作者 | 合成样本不具文学价值，任何测试都不能代替 |
| A19 | 真实付费模型（如 DeepSeek）输出质量、长度遵守与实际费用 | LONGFORM_EVALUATION §4 | PENDING-作者 | 需作者提供 Key 并授权费用；仓库不持久化计费字段 |
| A20 | 推送、PR、合并、tag、GitHub Release 等外部动作 | AGENTS / 路线定义 | PENDING-作者授权 | 本候选未执行任何外部动作 |
| A21 | 发布说明与本清单 | RF-17 | PASS | [发布说明](RELEASE_NOTES.md)、本页 |

## 3. Windows 执行步骤（交给 Codex）

在作者 Windows 机器上、仓库根目录、PowerShell 中按顺序执行。全部数据只用自有隔离根；**不读取、枚举、迁移或恢复正式 `%LOCALAPPDATA%\AIWebNovel` 及其备份**。任一步失败：保留日志，修复真实原因后对新 SHA 重跑受影响部分与 A1；不得降低阈值、跳过或重试造绿。

```powershell
git fetch; git switch feature/rf15-17-backup-longform-release
git status --short            # 必须为空
$sha  = git rev-parse HEAD
$tree = git rev-parse 'HEAD^{tree}'
New-Item -ItemType Directory -Force .runtime | Out-Null

# A1（含 A2–A9）：一次完整门禁，26 个场景含 E2E-INT-019
.\scripts\quality_gate.ps1 -IncludeE2E *>&1 | Tee-Object .runtime\rf17-quality-full.log
$LASTEXITCODE

# A10：启动烟测
.\scripts\check_startup_runtime.ps1 -Mode Development *>&1 | Tee-Object .runtime\rf17-startup-dev.log
.\scripts\check_startup_runtime.ps1 -Mode Integrated  *>&1 | Tee-Object .runtime\rf17-startup-int.log

# A12：备份脚本首次真实运行（自建隔离根，结束后只删除自己创建的目录）
$iso = Join-Path $env:TEMP ("AIWebNovel-RF17-" + [guid]::NewGuid().ToString('N'))
#   先用该根启动一次并创建一部测试小说，例如：
#   .\scripts\start_integrated.ps1 -DataRoot "$iso\data" （浏览器中创建小说后 Ctrl+C）
.\scripts\author_backup.ps1 create  -DataRoot "$iso\data"
.\scripts\author_backup.ps1 list    -DataRoot "$iso\data"
.\scripts\author_backup.ps1 verify  -DataRoot "$iso\data" -BackupId <上一步ID>
.\scripts\author_backup.ps1 restore -DataRoot "$iso\data" -BackupId <ID> -Target "$iso\restored"

# A13：长篇评测包装器首次真实运行
.\scripts\longform_eval.ps1 -WorkRoot "$iso\lf-small" -Scale small
.\scripts\longform_eval.ps1 -WorkRoot "$iso\lf-full"  -Scale full   # 记录墙钟/内存
```

A11：新开 `cmd`，`set LOCALAPPDATA=<新建的自有临时目录>` 后运行根目录 `启动 AI 网文助手.cmd`；记录自动打开的入口，用受控浏览器（Playwright 或手动）绑定 `http://127.0.0.1:8000/`，完成“新建小说 → 写正文并自动保存 → 数据备份页立即备份 → 校验完整性 → 下载 ZIP → 恢复到新目录（同名非空目标应被拒绝）”，再以 `start_integrated.ps1 -DataRoot <恢复目录>` 启动核对小说与正文一致；检查控制台无未解释错误；停止后确认端口释放，删除该临时目录。

### 记录结果

1. 在本页 §5 追加一行：日期、`$sha`、`$tree`、每个 A 项的 PASS/FAIL、退出码、关键数字（后端/前端测试数与覆盖率、E2E 场景数、评测墙钟/内存）、日志文件名（`.runtime\rf17-*.log`，Git 忽略，不提交）。
2. 同一内容发到活动交付 Issue（RF-15–17 主任务）评论，作为共享事实源；日志中不得出现绝对用户路径、Key、Cookie。
3. 更新 `PLAN.md` “最新有效证据”为该 SHA。全部 PENDING-Windows 项 PASS 后，才可在作者授权下推送/开 PR；合并与任何发布动作仍需作者单独授权。A18/A19 由作者给出结论后记录在同一 Issue。

## 4. Linux 实测结果（本候选）

2026-10-21，代码 `9739c78223e5f8617603dbcc887cf478e6e6a602`（树 `cf196265e24fa7701299780dc6030c3314165cc0`），工作树干净（仅新增本 RF-17 文档）。环境：Linux 6.12 aarch64 沙箱，2 vCPU；Python 3.12.15、SQLite 3.46.1；Node 22.23.3（门禁要求 Node 24，Windows 复核）；Playwright 1.61.1 / Chromium 149。分支未推送，以下是本地证据，不是 GitHub 共享事实。

| 检查 | 结果 |
| --- | --- |
| 前端 `npm run quality` | **PASS**，退出码 0：格式、lint、`tsc -b`、65 个文件 864 项测试全部通过；覆盖率语句/分支/函数/行 94.46% / 90.40% / 95.65% / 95.44%（门槛 80/75/80/80）；`vite build` 成功。首次运行因并发负载（同时安装浏览器依赖与 mypy）出现 vitest worker 启动超时（`eslint-boundaries.test.ts` 未启动，其余 861 项通过），未改任何代码或配置，空载重跑即通过；记录为环境问题 |
| 集成 E2E（Linux 等效运行器） | **25/26 通过**：E2E-INT-001–018、020–022（含 RF-15 `E2E-INT-022` 2.4 s、`E2E-INT-021` 6.2 s）、E2E-DEV-001–003、E2E-STARTUP-001。**E2E-INT-019 失败（预期）**：保存模型配置返回 503，页面未出现“模型配置已保存”，浏览器审计记录该 503；原因是 Linux 无 DPAPI，需 Windows |
| E2E 运行方式 | 每场景新建 `AIWebNovel-E2E-DataRoot-<随机>` 隔离根（系统临时目录，非仓库、非正式根），按 `run_e2e.ps1` 相同环境变量、端口（18121/18120+14173/18122/18123）与迁移规则（≥006 显式迁移，019 迁至 0006）启动 `python -m aiwebnovel`，`NODE_PATH` 指向前端依赖；结束后结束自有进程并删除运行目录（运行后残留 0）。未执行 `run_e2e.ps1` 的数据库验后检查与 `check_e2e_cleanup.ps1`（A8） |
| 后端 | 未重跑：RF-17 未改后端代码，沿用 `9739c78` 结果（A2） |
| `scripts/check_security_ast.py .` | PASS（退出 0） |
| ruff format --check / ruff check（门禁范围 `backend/src tests/backend tests/architecture`） | PASS：471 文件已格式化；All checks passed。注：门禁范围外的既有 `scripts/initialize_integrated_database.py`（本分支未改）不符合 ruff format，不属于门禁 |
| mypy `--platform win32` | PASS：234 个源文件无问题 |
| 冻结边界 | 相对 main 合并基 `9a67052`，`docs/M[0-7]_*` 与 `docs/history` 改动 0；本地未创建 tag；无推送、PR、Release |

长篇评测（A13/A15）复用 RF-16 结果：`--scale full` 13/13 PASS（测量提交 `90876e3`，墙钟 37.7 s，峰值 118 MiB）；之后评测代码只新增包装器与测试，RF-17 未改。

**限制（不因任何 PASS 而消失）**：未证明文学质量；未调用真实付费模型、未算货币费用；未验证百万字规模、Windows 性能/DPAPI、十万字下浏览器性能与多会话并发；召回有数量与字符预算，不承诺全书事实覆盖。

## 5. Windows 结果记录

| 日期 | SHA / 树 | A1 | A7 | A10 | A11 | A12 | A13 | 备注 / 日志 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| — | — | 待执行 | 待执行 | 待执行 | 待执行 | 待执行 | 待执行 | — |
