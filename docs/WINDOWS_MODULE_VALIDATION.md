# Windows 模块加载与测试

日期：2026-10-25。输入：`feature/product-design-implementation` / `868f4714974eb39c8b49e3242be82ae3c9538896`。工作分支：`codex/windows-module-validation`。

## 范围与恢复入口

加载 A1 作者工作台、A2 进度汇总、B1 候选对照与用量、B2 候选编辑与预算。用户要求按模块推送检查点；完整验收尚未通过，不合并或发布。采用独立工作目录保护原目录的未提交修改；所有测试使用自有隔离根，不读取正式创作数据或 Key。

## 当前结果

| 模块 | Windows 专项结果 | 浏览器流程 | 状态 |
| --- | --- | --- | --- |
| A1 | 前端 29/29，类型检查与生产构建通过 | 023 首次发现导航断言竞态；修复后遇启动超时，待定位 | 处理中 |
| A2 | 后端 17/17，前端 31/31 | 024 待跑 | 部分验证 |
| B1 | 待跑 | 025 待跑 | 已加载未验证 |
| B2 | 待跑 | 026 待跑 | 已加载未验证 |

A1 修复：点击首页后先断言 URL 为首页，再匹配书名。原写作页有两个书名元素，导航完成之前直接匹配会触发 strict mode violation；没有删减业务断言或延长超时。

启动问题：E2E 服务迁移完成并记录进程，但 30 秒 readiness 未成功；PowerShell 5/7 均复现。独立隔离根直接启动曾正常，正在采集就绪响应与进程证据；不能将此记为通过。

## 重现命令

仓库根目录：`.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/backend/test_workbench.py -q`。

frontend 目录：`npm run test:run -- ../tests/frontend/author-workbench.test.tsx ../tests/frontend/reference-rule-shortcut.test.tsx`；`npm run test:run -- ../tests/frontend/workspace-summary.test.tsx`；`npm run build`。

仓库根目录：`pwsh -NoProfile -File scripts/run_e2e.ps1 -Mode Integrated -Scenario E2E-INT-023`。后续依次 024/025/026，最后 `scripts/quality_gate.ps1 -IncludeE2E`。

本地原始日志位于工作目录 `.runtime/`（不提交运行产物）。构建保留已有 bundle >500 kB 提示；后端存在已安装 Starlette/httpx 弃用提示，未静音或隐藏。
