# 当前交付

更新：2026-11-17。D2、D3、B-1、B-4 及 D2 后续 PR #42 已合入 `main`，当前 `main` 为 `dea6eafc53f92eab6a1d19b8be6017af902d97c4`。

## 已合并能力

- D2 外部 AI 交接基础流程：PR #38，merge `35480b8`。支持作者选择来源、冻结交接快照、导出 ZIP、导入外部候选并显式采用。
- D3 跨章写作任务：PR #39，merge `ef7160b`。
- B-1 旧 `/ai/continue`、`/ai/rewrite` 经网关计量并受预算约束：PR #40，merge `324cab5`。
- B-4 用量 CSV：PR #41，merge `015c82c`。费用单价、币种、逐条金额和缓存 token 列未完成，留待 B-3。
- D1 旧稿导入与窄屏写作助手：PR #37，merge `f1caf4e`。

## 活动交付

- 第四步各项均已实现并推送，尚未合并：A1-2 [PR #43](https://github.com/King70404/AI-Writer-project/pull/43)、A1-1 [#44](https://github.com/King70404/AI-Writer-project/pull/44)、A2-1 [#47](https://github.com/King70404/AI-Writer-project/pull/47)、A2-2 [#48](https://github.com/King70404/AI-Writer-project/pull/48)、B-2 [#45](https://github.com/King70404/AI-Writer-project/pull/45)、B-3 及费用 CSV [#46](https://github.com/King70404/AI-Writer-project/pull/46)。各项验证范围见 PR 与报告；A2、B-3 最终组合完整门禁已通过。
- E 方法验证 [PR #49](https://github.com/King70404/AI-Writer-project/pull/49) 包含上述代码依赖、手工标注、两份显式 A/B 候选、作者评分及跨书模板。当前修复同试验重叠发送冲突，并补 E2E-INT-024 的初始读取完成等待；专项测试通过，完整门禁待重验，PR 保持草稿。操作与边界见 [方法验证](docs/METHOD_VALIDATION.md)。

## 下一步

完成 F08 最终完整门禁并记录精确版本；按依赖顺序在用户分别授权后合并。不会把未合并候选称为 main 已交付，不发布或打 tag。

## 边界

不调用真实或付费模型；不接触正式创作数据或真实 Key；不打 tag、不发布。任何 PR 合并前先取得用户明确授权。不把未合并或未实现功能记为已交付；不改冻结验收文件。
