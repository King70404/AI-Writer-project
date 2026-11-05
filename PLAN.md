# 当前交付

更新：2026-11-06。D2、D3、B-1、B-4 的前序 PR 已依次合入 `main`。当前 `main` 为 `015c82c36558543fb4554f78700cb7e38c557631`。

## 已合并能力

- D2 外部 AI 交接基础流程：PR #38，merge `35480b8`。支持作者选择来源、冻结交接快照、导出 ZIP、导入外部候选并显式采用。
- D3 跨章写作任务：PR #39，merge `ef7160b`。
- B-1 旧 `/ai/continue`、`/ai/rewrite` 经网关计量并受预算约束：PR #40，merge `324cab5`。
- B-4 用量 CSV：PR #41，merge `015c82c`。费用单价、币种、逐条金额和缓存 token 列未完成，留待 B-3。
- D1 旧稿导入与窄屏写作助手：PR #37，merge `f1caf4e`。

## 活动交付

- D2 后续缺口 PR #42：[`codex/d2-handoff-followups`](https://github.com/King70404/AI-Writer-project/pull/42)，代码提交 `ea7f14a391899f9bb6d0e5771bfbbb014a5bc4f4`。来源变化/缺失/超限时候选显示“待重新核对”且不提供采用操作；服务端仍复核来源。前后端及 E2E 统一交接文件名 `handoff.zip`。契约文档说明独立 `text/plain` 接口已删除，粘贴正文继续封装为快照绑定 JSON。Windows 完整门禁 PASS，报告见 [D2 后续验证](docs/D2_FOLLOWUP_WINDOWS_GATE_20261106.md)。PR 尚未合并，等待用户授权。

## 最新有效验证

- D2 后续代码 `ea7f14a391899f9bb6d0e5771bfbbb014a5bc4f4`：`scripts/quality_gate.ps1 -IncludeE2E` exit 0；后端 3,249 项通过，语句/分支覆盖率 97.71%/92.95%；前端 78 文件、1,076 项通过，覆盖率 94.26/90.23/95.99/95.42；E2E 34 场景及清理检查通过。日志散列、告警与环境边界见上述报告。该候选在 PR 合并前不视为 main 已交付。

## 下一步

1. 等待用户授权合并 PR #42；未经授权不合并。
2. A/B 剩余项按 A1-2、A1-1、A2-1、A2-2、B-2、B-3 顺序实施，每项一个分支并遵循 [AB_FOLLOWUPS](docs/product/AB_FOLLOWUPS.md)。B-3 包括缓存 token 计价与迁移，并补齐 B-4 CSV 的单价、币种和逐条金额列。
3. 依赖 B 的账本与候选隔离后，按 [FUNCTION_DESIGN.md](docs/product/FUNCTION_DESIGN.md) 实现 E 方法验证 F08，仅用假传输测试。

## 边界

不调用真实或付费模型；不接触正式创作数据或真实 Key；不打 tag、不发布。任何 PR 合并前先取得用户明确授权。不把未合并或未实现功能记为已交付；不改冻结验收文件。
