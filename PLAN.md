# 当前交付

更新：2026-11-07。

## 当前状态

main dea6eaf：PR #38、#39、#40、#41、#42 均经用户授权合并。D2 三个缺口已修复；B-4 当前只含用量 CSV，费用列待 B-3。

## 活动工作与证据

A1-2 分支 codex/a1-2-planning-next，实现 1571239，Windows 完整 IncludeE2E exit 0：后端 3248 项，前端 1077 项，E2E 34 场景与清理通过。详见 [报告](docs/A1_2_WINDOWS_GATE_20261107.md)。等待合并授权；基于 015c82c，合并前同步最新 main 并检查受影响部分。

## 下一步

依次 A1-1、A2-1、A2-2、B-2、B-3，每项独立分支，遵循 [AB_FOLLOWUPS](docs/product/AB_FOLLOWUPS.md)。B-3 包括缓存 token 迁移和 CSV 单价、币种、逐条金额列。随后实施 FUNCTION_DESIGN 的 F08。上述剩余项尚未完成。

## 边界

只用假传输与隔离测试数据；不得接触正式创作数据或真实 Key；不打 tag、不发布。任何 PR 合并前均须用户明确授权。运行时内容仍由作者确认后采用，不改冻结文件。
