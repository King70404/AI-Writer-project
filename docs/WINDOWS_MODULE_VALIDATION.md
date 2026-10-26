# Windows 模块加载与测试

日期：2026-10-26。输入：`feature/product-design-implementation` / `c1e8ac1`。工作分支：`codex/windows-module-validation`；最终验证候选：`b5117b2ac2a332f3470547e0de1c6c0f142148e6`。

## 范围与恢复入口

加载 A1 作者工作台、A2 进度汇总、B1 候选对照与用量、B2 候选编辑与预算。用户要求按模块推送检查点；后续 C 与最终结果见下方 2026-10-26 接续记录。采用独立工作目录保护原目录的未提交修改；所有测试使用自有隔离根，不读取正式创作数据或 Key。最终候选已通过 Windows CI 并合入 main（见文末）。

## 当前结果

| 模块 | Windows 专项结果 | 浏览器流程 | 状态 |
| --- | --- | --- | --- |
| A1 | 前端 29/29，类型检查与生产构建通过 | 023 通过，完整作者流程 6.1 秒 | 专项通过 |
| A2 | 后端 17/17，前端 31/31 | 024 通过，4.7 秒 | 专项通过 |
| B1 | 后端 19/19；B1/B2 前端合计 62/62 | 025 通过，4.2 秒 | 专项通过 |
| B2 | 后端 18/18；B1/B2 前端合计 62/62 | 026 通过，4.8 秒 | 专项通过 |

A1 修复：点击首页后先断言 URL 为首页，再匹配书名。原写作页有两个书名元素，导航完成之前直接匹配会触发 strict mode violation；没有删减业务断言或延长超时。

启动问题已定位：长工作目录叠加隔离根及存储探针文件名超过 Windows 路径限制，ready 返回 503（storage/database failed）；独立复现为探针 FileNotFoundError。缩短工作目录后原 30 秒上限内通过，没有改产品检查、上限或隔离规则。另修复就绪轮询访问异常不存在的 Response 属性；首页离开前断言后端已连接，避免主动取消健康检查污染网络审计。

A1 检查点：E2E-INT-023、29 项前端、生产构建通过；全量门禁仍待后续模块完成。

## 重现命令

仓库根目录：`.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/backend/test_workbench.py -q`。

frontend 目录：`npm run test:run -- ../tests/frontend/author-workbench.test.tsx ../tests/frontend/reference-rule-shortcut.test.tsx`；`npm run test:run -- ../tests/frontend/workspace-summary.test.tsx`；`npm run build`。

仓库根目录：`pwsh -NoProfile -File scripts/run_e2e.ps1 -Mode Integrated -Scenario E2E-INT-023`。后续依次 024/025/026，最后 `scripts/quality_gate.ps1 -IncludeE2E`。

本地原始日志位于工作目录 `.runtime/`（不提交运行产物）。构建保留已有 bundle >500 kB 提示；后端存在已安装 Starlette/httpx 弃用提示，未静音或隐藏。

A2 检查点：后端 17、前端 31、E2E-INT-024 全部通过，覆盖服务端字数、章节状态和派生待办。就绪异常回归另在 Windows PowerShell 5 与 PowerShell 7 各通过一项。

B1 检查点：已报告 token 与未知用量分开、候选对照不自动采用、重载持久化通过。准备新任务也触发打开的台账刷新，测试先确认台账加载完成再生成，避免连续刷新主动取消上一请求；网络审计保持严格。

B2 检查点：Windows 无符号链接权限时，测试使用真实目录联接继续验证重定向拒绝，不跳过、不 mock 安全判断；18 项通过。E2E 验证作者编辑版采用、严格预算拒绝（模型无请求且台账不增加）、提示预算需确认后发送。完整 IncludeE2E 下一步执行。

## 2026-10-26 接续：C 已加载并同步，验证按有效分段证据收尾

代码候选：`b5117b2ac2a332f3470547e0de1c6c0f142148e6`。C 输入 `c1e8ac1`，通过 `d687c17` 合入；后续修复包括可选 PowerShell 7 环境适配、旧数据库升级前工作台预期 503、首页书名定位限定继续写作区域、模型摘要异步加载竞态、离开写作页时卷章请求的导航取消。代码已推送 PR #35 并合入 main `12d19d50e60f449cadec192ce5380f1bf9618d34`，本地验证分支是 `codex/windows-module-validation-work`。

用户要求优先推进、避免重复检测。保留并复用另一位 AI 在本地的有效结果，仅补最后改动的定向确认，不再重复二十分钟的全后端测试：

| 验证 | 结果与来源 |
| --- | --- |
| 完整默认检查 | `quality-gate-20261026-run5.log`：卫生、安全、Ruff、mypy、后端、依赖、前端全部通过；后端 3219 passed / 1 skipped，语句 97.85%、分支 93.53% |
| GitHub Windows Default | run `40317559488` success（head `b5117b2`，24m7s） |
| GitHub Windows Full | run `40317566348` success（完整 IncludeE2E，30m46s） |
| 本地隔离实例 | `start_integrated.ps1 -Port 8000 -DataRoot %LOCALAPPDATA%\AIWebNovel-Development`：readiness 200，`/` 返回 SPA；未触碰正式数据根 |
| 前端 | 同一日志：71 文件、999 项通过；语句/分支/函数/行 95.56%/91.52%/97.13%/96.54%，构建通过 |
| 集成浏览器 | `e2e-full-check.log`：INT-001–027 加 STARTUP-001，共 28 项通过，含 Windows Key/升级、备份与 C |
| 开发浏览器 | `quality-gate-20261026-run4.log`：DEV-001–003 通过；该轮后续失败在 INT-023，由 061f160 修复，上述集成记录已通过 |
| 最后变更确认 | 本轮 `resume-023.log`：E2E-INT-023 通过，6.0 秒，生产构建通过 |
| 补齐可选环境 | 本轮 `pytest tests/architecture/test_startup_scripts.py -k "e2e_readiness and pwsh" -q`：1 passed；此前 skipped 是当时缺少 pwsh，本轮环境可用后补齐 |
| 清理 | 本轮 `check_e2e_cleanup.ps1` 通过：自有端口释放、运行数据清理 |

结论：A1/A2/B1/B2/C 本地加载完成，受影响功能及回归有上述分段通过证据。`run5` 的 IncludeE2E 包装进程日志止于再次构建，**不宣称本地单次完整脚本退出 0**；GitHub Windows Full（run `40317566348`）对同一候选 `b5117b2` 完成单次完整 IncludeE2E 并通过，GitHub Default（run `40317559488`）亦通过。没有删除旧失败，也没有把分段证据伪称单次全门 PASS。代码已合入 main `12d19d5`。此前旧工作目录 2851978 的 doctor 测试失败已由主目录 run5 的该项通过覆盖，旧失败日志保留。

C 当前可用：全书/卷目标、章节关联、伏笔原句证据与到期提醒、故事时间线、人物状态区间、固定/排除事实及召回预览，准备任务冻结作者规划；新增流程不调用模型。下一阶段按现有设计推进 D 有界跨章任务与外部 AI 交接；A/B 补全任务见 [AB_FOLLOWUPS](product/AB_FOLLOWUPS.md)，不再以重复本轮验收作前置。

### 合并与 CI

- PR [#35](https://github.com/King70404/AI-Writer-project/pull/35) 于 2026-10-26T12:19:21Z 合并到 `main`，merge `12d19d50e60f449cadec192ce5380f1bf9618d34`。
- head `b5117b2`：Windows Default [run 40317559488](https://github.com/King70404/AI-Writer-project/actions/runs/40317559488) 通过；Windows Full [run 40317566348](https://github.com/King70404/AI-Writer-project/actions/runs/40317566348) 通过。

### 复用日志摘要校验

日志保留在本地主目录 `.runtime/`，不提交运行产物；以下散列用于后续核对：

- `quality-gate-20261026-run5.log` SHA-256 `c20721ac1cffda6e25eec11740122f302f4c7bc5b2423c4d6d09320e6842c1b1`
- `e2e-full-check.log` SHA-256 `45cbbe88ca709fe0f53842952bc6d421ebd5157e87b8fc2113fdc5a54f063bdf`
- `quality-gate-20261026-run4.log` SHA-256 `6aa49e3d8ddc2fb4b1551465f22022c3492281bdb1ebe80bf469091a5faf737b`
- `resume-023.log` SHA-256 `da7d5a0954cc85029f3ea53229de316dd7c5588f7397a0877098b5b8318068b0`
