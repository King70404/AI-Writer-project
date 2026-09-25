# 当前接力：现在在哪里，下一步交付什么

更新：2026-09-26。GitHub 是跨 ChatGPT、Codex 与审阅线程的唯一共同事实源；开始任务前先核对最新 `main`、活动 PR/Issue 与本页。

## 当前阶段

**正在执行 V1 收尾。V1 正式完成后立即进入完整 AI 协作流程（RF-06–10）；原故事规划阶段 RF-01–05 后移。**

M0–M7 / V1 的既有正式冻结历史保持不变。当前阻塞不是基础能力缺失，而是 V1-UX-1 PR #9 仍需完成新的独立 RC → formal acceptance → merge 闭环。

## 当前 GitHub 状态

- 当前同步的 `main`：`d6d071b2faa3bacefa22013471cb3db124068e8f`；该提交只更新状态文档。
- [PR #9](https://github.com/King70404/AI-Writer-project/pull/9) 仍 OPEN、未合并。本轮正常合并最新 main 并解决唯一的 PLAN 文档冲突；产品源码与测试不因这次合并改变。
- 合并前开发 head 为 `e7442e546ed78c3f768f9d83f988ee5b2b6ae225`。合并后的精确 SHA、最新检查和冻结结果以 #23 / 后续 RC 记录为准。
- [CI 恢复 #23](https://github.com/King70404/AI-Writer-project/issues/23) 仍 OPEN；[RC2 #22](https://github.com/King70404/AI-Writer-project/issues/22) 保留 FAIL，不复用旧轮次计数。
- 最新 hosted Windows Quality run `35947089758` 已完成：Windows Default 与 Windows Full 均 SUCCESS。
- 本地 CI 模式前端质量门：676 项 PASS；CI 编排测试 9 项 PASS。
- 已知结构稳定性验证：20 次 targeted + 5 次完整文件运行全部 PASS。
- 真正根启动器已在隔离数据根下达到 ready/live/home HTTP 200，6 项 readiness 全部通过，数据库位于任务自有根，browser opener exit 0。
- **真实浏览器观察仍未 PASS。** 当次 Computer Use 无法可靠确认 Windows 浏览器当前 URL，因此停止；不得把自动打开的 Edge 窗口或 launcher 成功冒充 browser smoke PASS。
- 无新冻结 RC，无新 formal PASS，因此 **PR #9 当前不得合并，V1 不得宣布完成**。

## 当前恢复任务

当前唯一恢复入口是 [#23 V1-CI-R1](https://github.com/King70404/AI-Writer-project/issues/23)。

已完成的恢复工作包括：

1. 修正 GitHub Actions 中 `runner.temp` 的上下文使用位置。
2. 为全新 Windows runner 补齐 Integrated doctor 需要的前端构建准备。
3. 修正 CI=true 下动态 TypeScript/ESLint fixture 的 parser 生命周期问题，不弱化边界规则。
4. 修正 Windows PowerShell 5 对 BOM-free UTF-8 中文 Vitest 报告的读取问题。
5. 保留原质量阈值、测试、超时和失败证据；未使用 retry/sleep/skip/降低 coverage 等方式制造绿色。
6. 最新开发 SHA `e7442e546ed78c3f768f9d83f988ee5b2b6ae225` 的 hosted Windows Default / Full 已全部通过。

当前恢复工作：使用明确绑定本地 URL 的受控浏览器补齐实际页面观察及作者操作证据；默认浏览器自动打开的证据单独保留，不把进程退出码或窗口标题当作页面功能验证。原生 Computer Use 无法可靠识别 URL 的限制不得绕过，不能重写旧失败。临时 launcher harness 已修正阶段计时：原 90 秒整体上限与后端创建后的原 30 秒就绪上限同时生效。

## 下一步顺序

1. 在最新 `main` 与 PR #9 同步后形成新的精确 candidate；任何新 commit 都重置候选计数。
2. 创建独立 RC，在同一冻结 SHA 按稳定性协议完成：
   - Default PASS；
   - Full / IncludeE2E 连续两次 PASS；
   - 真实根 launcher smoke；
   - 完整隔离 author UX/delete smoke；
   - 已知 timing-sensitive 稳定性验证；
   - 浏览器 console/page/request 诊断；
   - Git / migration / tag / frozen-history / 正式数据边界。
3. RC 全部通过后创建独立 formal acceptance。
4. formal PASS 后才合并 PR #9，并记录新的唯一 `main` 基线 SHA。
5. 核实 #17 的 GitHub latest-SHA checks 与仓库管理限制，完成 RF-00 #11。
6. 随即进入完整 AI 协作阶段 RF-06–10；RF-01–05 故事规划阶段继续后移。

## 后续交付路线

| 顺序 | 完整交付成果 | 原 RF 范围 |
| --- | --- | --- |
| 当前 | 稳定 V1、完成验收与 CI、锁定基线 | RF-00 + UX + #17 |
| 下一阶段 | 完整 AI 协作：模型接入、上下文、持久候选、确认采纳、连续生成 | RF-06–10 + 必要契约 |
| 后移 | 故事规划基础：场景、剧情推进点、故事资产与写作规则 | RF-01–05 |
| 后续 | 长篇记忆、一致性评审与统一作者工作台 | RF-11–14 |
| 最后 | 安全升级/备份恢复、长篇评测与发布 | RF-15–17 |

## 当前禁止事项

- 未完成新的独立 formal PASS 前，不合并 PR #9。
- 不复用 #22 或其他旧失败轮次的绿色计数。
- 不通过 timeout inflation、sleep、retry、skip、删除/弱化测试、降低 coverage 或静音 warning 制造通过。
- 不读取、枚举、修改、删除或重置作者正式 `%LOCALAPPDATA%\AIWebNovel` 数据用于测试或验收。
- 不移动或改写 M0–M7 冻结 tag、验收历史或冻结文件。
- V1 基线锁定前不启动 RF-06–10 的产品实现；RF-01–05 继续后移。
- 旧 V1-AI-1 不另开旁路。

## main 与 PR #9 的同步边界

本轮把 `main@d6d071b` 正常合并进 PR #9，保持 main 的未验收产品边界。合并后的新 SHA 必须重新取得 hosted CI 和完整 RC 证据，不沿用 `e7442e5` 的门禁计数。冻结期间动态结果只写 Issue / PR；不再为协调状态提交文档打断候选。

## 接力维护规则

重要需求、方向、候选 SHA、formal PASS/FAIL、新 blocker、PR merge/close 与最终基线变化必须同步到 GitHub。动态验收结果优先写活动 Issue / PR；冻结期间不为状态说明额外改变 candidate。

不要把聊天记录当项目状态库；不得在协调文档中记录 API Key、密码、Cookie、令牌、私钥或作者正式创作内容。
