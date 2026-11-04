# 当前交付

更新：2026-11-04。D1 旧稿导入与窄屏写作助手已在 Windows 完成完整质量门禁并合并 main（[PR #37](https://github.com/King70404/AI-Writer-project/pull/37)，merge `f1caf4e`）。A1/A2/B1/B2/C 已在 Windows 验证并合并（PR #35，merge `12d19d5`）。

## 当前状态

- main `f1caf4e93efba46f3f1c32f1ff60e9c76b1d4e2c`；D1 候选 `e6a4666ea87b6e141034d12a73dae4caa0fe3840`；A1–C 候选 `b5117b2`。
- 既有 V1、AI 协作、范文/章节规划、记忆评审、备份与规模评测见 [发布验收](docs/RELEASE_ACCEPTANCE.md)。
- A1：作者首页/书架、三栏写作、专注、保存切章、原地模型设置、范文规则捷径。
- A2：全书字数、分页、章节状态、派生待办。
- B1/B2：候选对照与编辑采用、用量、作者填写价格、预算拒绝与提示、本机草稿隔离及冲突对照。
- C：全书/卷规划、伏笔证据与到期提醒、故事时间线、人物状态区间、可调事实召回和准备时冻结作者规划。
- D1：旧稿导入（TXT/Markdown/粘贴、分章预览、分片上传、单事务建书与幂等回执）及窄屏写作助手抽屉（Esc、焦点管理、草稿保持）。

## 活动开发

- D1 已交付：完整 `quality_gate.ps1 -IncludeE2E` 通过，后述数字见“最新有效验证”；导入不调用模型，失败回滚，重复提交不重复建书。
- D2 外部 AI 交接、D3 跨章写作任务仍为独立 WIP 分支（PR #38/#39），未合并且不冒充已交付。
- A/B 补全项见 [AB_FOLLOWUPS](docs/product/AB_FOLLOWUPS.md)。

## 最新有效验证

[Windows 模块记录](docs/WINDOWS_MODULE_VALIDATION.md)保存 A1–C 的精确候选、来源、日志散列和限制；D1 结果如下。

- D1 Windows 完整门禁（`e6a4666`，`.runtime/d1-full-gate-20261104.log`）：`quality_gate.ps1 -IncludeE2E` **passed，exit 0**；E2E 清理验证通过。
- 后端 3225 passed / 1 skipped（本机无 PowerShell 7 可选参数）；语句/分支覆盖 97.66%/92.99%。
- 前端 72 文件 1012 项通过；语句/分支/函数/行 94.31%/90.71%/96.13%/95.39%；类型、格式、构建、依赖检查通过。
- 浏览器：集成 E2E INT-001–028 加 STARTUP-001 共 29 项通过，含 Windows Key/升级、备份、C 与 D1 导入。
- GitHub Actions 当前因账号账单/额度无法启动 job（2 秒失败、无步骤），因此 GitHub checks 不可用；D1 以本地完整门禁证据合并，未降低断言或覆盖率。

## 下一步

1. 按 [D 阶段交接](docs/product/D_IMPLEMENTATION_HANDOFF.md)推进 D2：本地快照权威的选择性导出、严格返回校验、外部候选对照与作者采用；D3 跨章任务继续保持独立分支。
2. A/B 补全按 [任务清单](docs/product/AB_FOLLOWUPS.md)领取；高成本功能继续按设计交接范围推进。
3. C 尚缺：可选 AI 拆分规划/伏笔抽取、语义索引、评审使用召回策略、到期伏笔进入 A2 待办、人物状态事实关联 UI、拖拽排序。
4. 旧 `/ai/continue`、`/ai/rewrite` 不计量、不受预算约束；分析/评审发送前预估 UI、缓存 token 计价、CSV 导出仍未实现。模型文学质量与真实费用不由受控测试代替。

## 边界

正式创作数据、备份及真实 Key 不进入开发验收；作者确认后才采用 AI 正文/事实/规则。不改冻结文件和 tag；后续发布、正式数据操作和不可逆动作仍需明确授权。实际能力见 [功能索引](docs/FEATURE_REALITY_MATRIX.md)。