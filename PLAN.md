# 当前交付

更新：2026-11-16。D2、D3、B-1、B-4 和 D2 后续 PR #42 已合入 `main`，当前 `main` 为 `dea6eafc53f92eab6a1d19b8be6017af902d97c4`。

## 已合并能力

- D2 外部 AI 交接基础流程：PR #38，merge `35480b8`。支持作者选择来源、冻结交接快照、导出 ZIP、导入外部候选并显式采用。
- D3 跨章写作任务：PR #39，merge `ef7160b`。
- B-1 旧 `/ai/continue`、`/ai/rewrite` 经网关计量并受预算约束：PR #40，merge `324cab5`。
- B-4 用量 CSV：PR #41，merge `015c82c`。费用单价、币种、逐条金额和缓存 token 列未完成，留待 B-3。
- D1 旧稿导入与窄屏写作助手：PR #37，merge `f1caf4e`。

## 活动交付

- A1-2 [PR #43](https://github.com/King70404/AI-Writer-project/pull/43)、A1-1 [PR #44](https://github.com/King70404/AI-Writer-project/pull/44) 与 B-2 [PR #45](https://github.com/King70404/AI-Writer-project/pull/45) 未合并，分别等待授权。
- A2-1 [PR #47](https://github.com/King70404/AI-Writer-project/pull/47)：代码候选 `c4cd77d7edddf588905883b0cbf5dc56bc3edacb`，完整 Windows 门禁通过，详见 [验证记录](docs/A2_1_WINDOWS_GATE_20261116.md)；尚未合并，等待用户授权。
- A2-2 与 E 方法验证 F08 仍在开发和验证；B-3 独立候选已通过全量门禁，草稿 [PR #46](https://github.com/King70404/AI-Writer-project/pull/46) 尚需与 A2-2 整合后重验。

## 下一步

完成 A2-1、A2-2、B-3 的组合与全量门禁，逐项提交推送并记录；完成依赖 B 台账与候选隔离的 F08。所有 PR 合并前分别取得用户授权。

## 边界

不调用真实或付费模型；不接触正式创作数据或真实 Key；不打 tag、不发布。任何 PR 合并前先取得用户明确授权。不把未合并或未实现功能记为已交付；不改冻结验收文件。
