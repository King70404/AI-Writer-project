# Windows 模块加载与测试

日期：2026-10-25。输入：`feature/product-design-implementation` / `868f4714974eb39c8b49e3242be82ae3c9538896`。工作分支：`codex/windows-module-validation`。

## 范围与恢复入口

加载 A1 作者工作台、A2 进度汇总、B1 候选对照与用量、B2 候选编辑与预算。用户要求按模块推送检查点；完整验收尚未通过，不合并或发布。采用独立工作目录保护原目录的未提交修改；所有测试使用自有隔离根，不读取正式创作数据或 Key。

## 当前结果

| 模块 | Windows 专项结果 | 浏览器流程 | 状态 |
| --- | --- | --- | --- |
| A1 | 前端 29/29，类型检查与生产构建通过 | 023 通过，完整作者流程 6.1 秒 | 专项通过 |
| A2 | 后端 17/17，前端 31/31 | 024 待跑 | 部分验证 |
| B1 | 待跑 | 025 待跑 | 已加载未验证 |
| B2 | 待跑 | 026 待跑 | 已加载未验证 |

A1 修复：点击首页后先断言 URL 为首页，再匹配书名。原写作页有两个书名元素，导航完成之前直接匹配会触发 strict mode violation；没有删减业务断言或延长超时。

启动问题已定位：长工作目录叠加隔离根及存储探针文件名超过 Windows 路径限制，ready 返回 503（storage/database failed）；独立复现为探针 FileNotFoundError。缩短工作目录后原 30 秒上限内通过，没有改产品检查、上限或隔离规则。另修复就绪轮询访问异常不存在的 Response 属性；首页离开前断言后端已连接，避免主动取消健康检查污染网络审计。

A1 检查点：E2E-INT-023、29 项前端、生产构建通过；全量门禁仍待后续模块完成。

## 重现命令

仓库根目录：`.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml tests/backend/test_workbench.py -q`。

frontend 目录：`npm run test:run -- ../tests/frontend/author-workbench.test.tsx ../tests/frontend/reference-rule-shortcut.test.tsx`；`npm run test:run -- ../tests/frontend/workspace-summary.test.tsx`；`npm run build`。

仓库根目录：`pwsh -NoProfile -File scripts/run_e2e.ps1 -Mode Integrated -Scenario E2E-INT-023`。后续依次 024/025/026，最后 `scripts/quality_gate.ps1 -IncludeE2E`。

本地原始日志位于工作目录 `.runtime/`（不提交运行产物）。构建保留已有 bundle >500 kB 提示；后端存在已安装 Starlette/httpx 弃用提示，未静音或隐藏。
