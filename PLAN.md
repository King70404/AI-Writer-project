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
- D2 外部 AI 交接（PR #38，分支 `codex/d2-external-handoff`）：当前章正文、规划、规则版本与有效事实可显式选取，支持 ZIP 导出、外部候选导入和作者明确采用。已合入最新 main；2026-11-04 Linux 复验（`1cd3b8f`）：修复迁移 0015 引起的架构/启动测试期望（表清单、修订版、触发器 39），修复非法/不存在章节 ID 返回 500 的问题（改为 422/404），删除被 JSON 中间件拦截而不可达的 text/plain 分支，补齐前后端交接测试（handoff/web.py 98%，前端交接模块 97–100%）。前端 75 文件 1046 项通过，覆盖 94.44/90.75/96.24/95.55；后端 3141 通过/86 失败（均为 Linux 缺 PowerShell 的 Windows 基线）/2 跳过，语句/分支 97.32%/92.39%；Linux E2E 33 项中 32 通过，仅 E2E-INT-019 因无 DPAPI 失败（预期）。Windows 完整门禁待运行，未合并。已知缺口：合法快照但来源已变时，导入阶段不标记“待重新核对”，仅在采用时拒绝。
- D3 跨章写作任务（PR #39，分支 `codex/d3-writing-jobs`，迁移 0016/0017，E2E-INT-030）：2026-11-04 由 Hark 接手并合入 D2。已实现持久任务清单（最多 10 章、按作者顺序）、run 绑定（同一步骤只能绑定一个未发送 run）、任务级总请求/总输出额度（在既有发送事务内预留，原 generate 路径同样受限，本地预算拒绝退回额度，失败/中断保留预留）、暂停/恢复/终止/结束本章（不改定稿状态）及生成/采用字数统计。Linux 验证：写作任务后端 9 项、前端 25 项通过（模块覆盖 97.7/94.7/100/100）；受影响的清单/迁移回归通过（其余失败均为缺 PowerShell 的 Windows 基线）；E2E 34 项中 33 通过，仅 INT-019 缺 DPAPI。后端全量与 Windows 完整门禁待运行，未合并。与规格的差异：用 `bind-run` 绑定由现有流程创建的 run，替代 `prepare-step`；任务状态只有 planned/paused/cancelled/completed，ready/running/waiting_author 由所绑定 run 的状态体现。
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