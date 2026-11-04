# 当前交付

更新：2026-11-05。D1 旧稿导入与窄屏写作助手已在 Windows 完成完整质量门禁并合并 main（[PR #37](https://github.com/King70404/AI-Writer-project/pull/37)，merge `f1caf4e`）。A1/A2/B1/B2/C 已在 Windows 验证并合并（PR #35，merge `12d19d5`）。

## 当前状态

- main `35480b897212caf00a941a166e074bf6d1e906e2`；D1 候选 `e6a4666ea87b6e141034d12a73dae4caa0fe3840`；A1–C 候选 `b5117b2`。
- 既有 V1、AI 协作、范文/章节规划、记忆评审、备份与规模评测见 [发布验收](docs/RELEASE_ACCEPTANCE.md)。
- A1：作者首页/书架、三栏写作、专注、保存切章、原地模型设置、范文规则捷径。
- A2：全书字数、分页、章节状态、派生待办。
- B1/B2：候选对照与编辑采用、用量、作者填写价格、预算拒绝与提示、本机草稿隔离及冲突对照。
- C：全书/卷规划、伏笔证据与到期提醒、故事时间线、人物状态区间、可调事实召回和准备时冻结作者规划。
- D1：旧稿导入（TXT/Markdown/粘贴、分章预览、分片上传、单事务建书与幂等回执）及窄屏写作助手抽屉（Esc、焦点管理、草稿保持）。

## 活动开发

- D3 跨章写作任务（PR #39，分支 `codex/d3-writing-jobs`，迁移 0016/0017，E2E-INT-030）：2026-11-04 由 Hark 接手并合入 D2。已实现持久任务清单（最多 10 章、按作者顺序）、run 绑定（同一步骤只能绑定一个未发送 run）、任务级总请求/总输出额度（在既有发送事务内预留，原 generate 路径同样受限，本地预算拒绝退回额度，失败/中断保留预留）、暂停/恢复/终止/结束本章（不改定稿状态）及生成/采用字数统计。Linux 验证：写作任务后端 9 项、前端 25 项通过（模块覆盖 97.7/94.7/100/100）；受影响的清单/迁移回归通过（其余失败均为缺 PowerShell 的 Windows 基线）；E2E 34 项中 33 通过，仅 INT-019 缺 DPAPI。最新 main 已合入，Windows 首轮门禁在 Ruff 导入排序检查 FAIL（9 个测试文件）；已只修正排序，待新候选完整复验，未合并。与规格的差异：用 `bind-run` 绑定由现有流程创建的 run，替代 `prepare-step`；任务状态只有 planned/paused/cancelled/completed，ready/running/waiting_author 由所绑定 run 的状态体现。

- D1 已交付：完整 `quality_gate.ps1 -IncludeE2E` 通过，后述数字见“最新有效验证”；导入不调用模型，失败回滚，重复提交不重复建书。
- D2 外部 AI 交接 [PR #38](https://github.com/King70404/AI-Writer-project/pull/38)：候选 `d08e5c8` Windows 完整 IncludeE2E PASS（2026-11-05），已于 2026-11-05 获用户授权并合并 main（merge `35480b8`）。支持选择来源、ZIP 导出、外部候选导入及作者采用。来源变化快照标记、统一下载文件名、纯文本入口删除的文档同步仍待合并后新分支修复。详见 [Windows 报告](docs/D2_WINDOWS_GATE_20261105.md)。
- B-1 [PR #40](https://github.com/King70404/AI-Writer-project/pull/40)（实现 `c71a5d2`，记录 `5015121`）、B-4 [PR #41](https://github.com/King70404/AI-Writer-project/pull/41)（实现 `3eeb277`，记录 `aed1117`）已推送，均未合并。B-1 交接记录 Linux 定向 285 项通过；两者 Windows 门禁待 #38/#39 后按序 rebase 再执行。B-4 尚无费用列，待 B-3 补齐。
- A/B 补全项见 [AB_FOLLOWUPS](docs/product/AB_FOLLOWUPS.md)。

## 最新有效验证

[Windows 模块记录](docs/WINDOWS_MODULE_VALIDATION.md)保存 A1–C 的精确候选、来源、日志散列和限制；D1 结果如下。

- D2 Windows 完整门禁：`d08e5c8`，exit 0；后端 3233 passed，语句/分支 97.68%/93.00%；前端 75 文件/1046 项，覆盖 94.44/90.76/96.24/95.55%；E2E 33 场景及清理通过。精确 SHA、日志散列与 warning 见 [D2 报告](docs/D2_WINDOWS_GATE_20261105.md)。

- D1 Windows 完整门禁（`e6a4666`，`.runtime/d1-full-gate-20261104.log`）：`quality_gate.ps1 -IncludeE2E` **passed，exit 0**；E2E 清理验证通过。
- 后端 3225 passed / 1 skipped（本机无 PowerShell 7 可选参数）；语句/分支覆盖 97.66%/92.99%。
- 前端 72 文件 1012 项通过；语句/分支/函数/行 94.31%/90.71%/96.13%/95.39%；类型、格式、构建、依赖检查通过。
- 浏览器：集成 E2E INT-001–028 加 STARTUP-001 共 29 项通过，含 Windows Key/升级、备份、C 与 D1 导入。
- D1 当时 GitHub Actions 因账号账单/额度不可用；该限制不代表当前状态。2026-11-05 查询 #38 最新 Windows Default/Full checks 均成功，本轮另有本机完整门禁通过证据。

## 下一步

1. #38 已授权合并；最新 main 合入 D3 / #39，执行完整门禁（含 E2E 34 场景和前端全量覆盖率），报告并等待授权。
2. B-1 / #40、B-4 / #41 依次 rebase 最新 main、运行门禁、报告并各自等待合并授权。
3. #38 合并后新分支修复 D2 三个缺口：来源变化快照标记、统一文件名、同步纯文本入口已删除。
4. A/B 按 A1-2、A1-1、A2-1、A2-2、B-2、B-3 顺序，每项一个分支并遵循 [AB_FOLLOWUPS](docs/product/AB_FOLLOWUPS.md)；B-3 含缓存迁移与 B-4 单价/币种/逐条金额列。之后按 FUNCTION_DESIGN 的 F08 实现 E 方法验证。
5. C 其他缺口及真实付费模型文学质量/实际费用评价未纳入本轮交付。
## 边界

正式创作数据、备份及真实 Key 不进入开发验收；作者确认后才采用 AI 正文/事实/规则。本轮禁止真实/付费模型、正式数据、真实 Key、tag 与发布；任何 PR 合并均须先获用户明确授权。不改冻结文件。实际能力见 [功能索引](docs/FEATURE_REALITY_MATRIX.md)。
