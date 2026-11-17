# 当前交付

更新：2026-11-18。A1-2、A1-1 已经用户授权合入 main（PR #43 merge `530a8ce`；PR #44 merge `eca5975`）。用户已授权继续合并后续 PR，无需逐项再次确认。

## 已合并能力与有效证据

PR #38、#39、#40、#41、#42 已在此前经用户授权合并，包含 D2、D3、旧接口网关计量与预算、用量 CSV，以及 D2 三项后续修复。

A1-2 [PR #43](https://github.com/King70404/AI-Writer-project/pull/43) 已合并：规划有修改时可保存并切换至生成准备，保存失败保留草稿，不自动发送或采用。实现提交 `157123995fc60a68945f3463a2e27019d1343426` 的 Windows 完整 IncludeE2E 通过：后端 3,248 项、前端 1,077 项、E2E 34 场景及清理通过，见 [验证报告](docs/A1_2_WINDOWS_GATE_20261107.md)。同步 D2 后仅解决 PLAN 文档冲突，合并时复用 A1-2 与 D2 各自有效证据，不声称重新运行过 PR head 的整套门禁。

PR #43 的 GitHub Windows 检查因账户付款/额度问题未启动，未执行步骤；不能记为云端测试通过。本地 Windows 证据与云端状态分开记录。

## 已实现验证、尚未合并的候选

- A1-1 检查连接 [PR #44](https://github.com/King70404/AI-Writer-project/pull/44) 已合并为 `eca5975`，独立完整门禁和 main 同步补验证据见 [报告](docs/A1_1_WINDOWS_GATE_20261109.md)。
- A2-1 全书架汇总 [PR #47](https://github.com/King70404/AI-Writer-project/pull/47) 已合并为 `8543a06`；A2-2 到期伏笔与预算提醒 [PR #48](https://github.com/King70404/AI-Writer-project/pull/48) 已同步最新 main，等待合并。
- B-2 分析/评审发送前预估：[PR #45](https://github.com/King70404/AI-Writer-project/pull/45)；B-3 缓存计价、迁移及 B-4 费用 CSV：[PR #46](https://github.com/King70404/AI-Writer-project/pull/46)。main 的 CSV 当前仍只有用量列。
- E/F08 方法验证：[PR #49](https://github.com/King70404/AI-Writer-project/pull/49)，代码 `8dcf46cfa9b91806acb5225268e37ccdb3301a15` 完整 Windows 门禁通过：后端 3,334、前端 1,098、E2E 34 场景及清理通过。包含上述代码依赖；报告与操作契约在该 PR 分支。未合并，不称为 main 已交付。

各 PR 记录精确候选和验证范围，后续仅文档提交不清零已验证且未变化的代码证据。

## 下一步

按已取得的连续合并授权，依次处理 A2-1 → A2-2 → B-2 → B-3 → F08；每项先同步最新 main 并核对受影响验证。

## 边界

只用假传输与自有隔离测试数据；不接触正式创作数据或真实 Key；不打 tag、不发布。用户已授权本轮余下 PR 连续合并；不绕过保护或 force push。运行时内容仍由作者确认后采用，不改冻结验收文件。
