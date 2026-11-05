# B-1 Windows 完整门禁（2026-11-06）

结论：本机完整门禁 PASS，PR #40 等待用户授权合并。GitHub Actions 的同候选 Windows Default 两项成功；Windows Full 仅失败于 E2E-INT-025 将并发取消的 usage 请求 `net::ERR_ABORTED` 记录为意外请求失败。本机完整 34 场景通过。该远端 E2E 失败保留，不宣称 GitHub Full PASS。

## 候选与基线

- 最新 main：PR #39 merge `ef7160bbb62518c4d85a2b6ce16fb5557981479d`。
- B-1 功能源提交：原 `c71a5d2`，已基于最新 main rebase。
- 本机验证 head：`7b079f9e80fc2d6fd9d3bc695aa571d3aecabe96`，包含仅排序修复。
- PR #40 head 与本机验证 head 一致；base 为 main。

## 本机结果

命令：仓库根 `scripts/quality_gate.ps1 -IncludeE2E`；最终运行 `.runtime/b1-full-gate-20261105-r11.log`，退出码 **0**。

- 后端与架构：**3248 passed**，语句 **97.71%**、分支 **92.94%**。
- 前端：**77 文件 / 1071 项通过**；语句/分支/函数/行 **94.24% / 90.20% / 95.97% / 95.40%**。
- E2E：**34 场景通过**，含 E2E-INT-025 与 D3 INT-030；浏览器审计和 E2E 清理复核通过。
- 格式、Ruff、mypy、Python/npm 依赖检查、前端 lint/type/build 均通过。
- 日志 SHA-256：`A1A51516B99B31370988E5D386FB36136359DE87334CC443BF264E389B1741C1`。
- 后端保留 5 条依赖弃用 warning；Node 启动器有 NO_COLOR/FORCE_COLOR 提示，未静音。

## 失败与恢复记录

- 首次 rebase 后 Ruff 发现 1 个导入排序问题；`7b079f9` 修正后推送。
- 复用 D3 worktree 环境的首次测试收集用了错误的 editable 源路径。隔离启动配置恢复后，以本机 `.runtime/sitecustomize.py` 将测试解释器限定到当前 B-1 或各自隔离临时仓库；启动钩子未提交。
- 先前本机完整轮次因 B-1 worktree 缺 `frontend/dist`，补建前端后复验；隔离 runner 测试首次受到临时路径钩子的影响，定向确认和修正后，后续完整轮次通过。
- 全量前端有一次章节导航测试的瞬时失败；定向重跑通过，最终全量轮次 1071 项通过。
- GitHub Actions Windows Full 在相同 head `7b079f9` 失败于 INT-025：作者关闭/切换页面时 `/usage` 请求收到 `net::ERR_ABORTED`，浏览器审计误记为意外失败；Default 两项成功。本机重跑同场景及 34 场景全套通过。此 CI 差异待独立修复，不删除断言、不屏蔽失败。

## 功能边界

旧 `/ai/continue` 与 `/ai/rewrite` 通过模型网关，发送前写用量台账、执行预算判断，台账不可用时拒绝；旧客户端响应字段兼容。测试只用 fake provider，不调用真实/付费模型，不接触正式创作数据、备份或真实 Key。

B-1 不包括 B-2/B-3/B-4；分析/评审发送前预估、缓存 token 计价、费用 CSV 列仍未交付。下一步等待用户授权合并 #40；其后 B-4 按序 rebase 最新 main 并运行门禁。#39 CI 的同类 INT-025 取消请求失败也已在 D3 报告说明。
