# 当前接力：现在在哪里，下一步交付什么

更新：2026-09-24。先按 [AGENTS.md](AGENTS.md) 核对 GitHub；本页只保存当前有效状态。

## 当前阶段与已完成成果

**正在执行 V1 收尾；完成后立即进入完整 AI 协作流程。用户已明确把原故事规划阶段后移。**

- M7/V1 已正式验收：小说/设定/人物管理，大纲/卷/章，正文编辑与自动保存，本地 AI 续写/改写、作者确认采用、TXT 导出。实际前提与限制见 [功能索引](docs/FEATURE_REALITY_MATRIX.md)。
- [PR #9](https://github.com/King70404/AI-Writer-project/pull/9) 仍 OPEN、未合并。UX 产品修复提交 `014205985d5e3acfe5cd38cc60d108df495ed42d`；[R4 #20](https://github.com/King70404/AI-Writer-project/issues/20#issuecomment-5677994354) 已关闭 completed。
- R4 开发证据：Default PASS；后端 2778、前端 676、完整浏览器 24 项通过；已知 structure 测试完成 20+5 次稳定性验证。**这是开发结果，尚无新 RC/formal PASS。**
- 最近核实的远端 `main`：`0939e3a0a753dc819ab0f5bc6f4496198c3290dd`。[RC2 #22](https://github.com/King70404/AI-Writer-project/issues/22) 冻结候选 `e81754ed` 因 GitHub CI 在分配任何 job 前失败，已保留 FAIL。当前进入 [CI 恢复 #23](https://github.com/King70404/AI-Writer-project/issues/23)，修复后将形成新候选，不能复用 RC2 的计数。
- 旧失败仅作追溯：[Q1 #10](https://github.com/King70404/AI-Writer-project/issues/10)、[Q2 #14](https://github.com/King70404/AI-Writer-project/issues/14)、[RC1 #18](https://github.com/King70404/AI-Writer-project/issues/18#issuecomment-5646556594)；不重开这些轮次。

## 最近完成的整理

[DOC-GOV-2 #21](https://github.com/King70404/AI-Writer-project/issues/21)：已精简入口、删除过期协调快照、修正 README、归档旧愿景，并形成五阶段路线。默认入口文字量减少约 60%，28 份历史正文退出普通搜索；67 条链接与 9 项文档相关契约测试通过。源码、24 份冻结文件和 8 个本地 tag 不变；最终提交及结项记录见 #21。

## 当前 blocker 与下一步

R4 产品修复、历史整理和 Windows CI 接线已同步。真实根启动器和完整隔离作者 smoke 已在开发环境通过；创建、正文保存、序号清空、删除保护、9 个旧页面拒绝访问及 7 条原修订不变均已核对。这些开发证据不替代冻结验收。

当前恢复入口为 #23。CI 的环境表达式、首次构建顺序、动态 TypeScript 测试缓存和 Default 所需 Chromium 安装均已修正。`8c81d314` 的真实 GitHub Windows Default / Full 已全部 PASS（[运行记录](https://github.com/King70404/AI-Writer-project/actions/runs/35875839092)）。本地 CI 模式完整前端质量门 PASS（676 项，覆盖率 statements 96.11%、branches 92.13%），CI 架构测试 9 项通过。

最后补齐稳定性脚本对 UTF-8 中文报告的显式读取，并将编排测试改为真实编码的中文样例；9 项回归及实际 20 次指定测试、5 次完整文件测试全部通过。发布该修复后的精确 SHA 将成为新候选；新 SHA 的 hosted Default / Full 通过后，连续完成独立 RC 和 formal，动态结果只写 Issue / PR，不在冻结期间追加状态提交。

**下一步一次交付“可放心继续开发的 V1 基线”**，按以下依赖连续完成：

1. 完成 [CI 恢复 #23](https://github.com/King70404/AI-Writer-project/issues/23)，在新 SHA 上核对真实 `Windows Default` / `Windows Full` 能启动并得到结果；另建 RC，在同一冻结 SHA 按 [稳定性协议](docs/ACCEPTANCE_STABILITY.md) 完成 Default、两次 IncludeE2E、真实根 launcher、完整作者 UX/delete smoke 及边界验证。
2. 全部通过后创建独立 formal acceptance；正式 PASS 后合并 PR #9、结束 UX，记录最终 main SHA。
3. 核实 #17 的 GitHub 最新提交检查与管理限制，关闭 [RF-00 #11](https://github.com/King70404/AI-Writer-project/issues/11)，随即实施 AI 闭环；不再要求用户逐步“继续”。

已核实：本地 8 个冻结 tag 未变，Git 与 GitHub API 均确认远端未公布 tag；验收记录起止清单和原对象/祖先关系，不擅自补推。GitHub required rules 受套餐/owner 权限限制，CI 实际运行与管理设置分别记录。RC2 已 FAIL 并关闭，新 RC 尚未冻结，不存在新正式 PASS。

## 再下一步与后续

| 顺序       | 完整交付成果                                                 | 原 RF 清单          |
| ---------- | ------------------------------------------------------------ | ------------------- |
| 1 当前     | 稳定 V1、完成验收与 CI、锁定基线                             | RF-00 + UX + #17    |
| 2 立即接续 | 完整 AI 协作：模型接入、上下文、持久候选、确认采纳、连续生成 | RF-06–10 + 必要契约 |
| 后移       | 故事规划基础：场景、剧情推进点、故事资产与写作规则           | RF-01–05            |
| 4          | 长篇记忆、一致性评审与统一作者工作台                         | RF-11–14            |
| 5          | 安全升级/备份恢复、长篇评测与发布                            | RF-15–17            |

每阶段的完成定义见 [交付路线](docs/REFRACTOR_ROADMAP.md)。阶段内 RF 项串行推进，不因每个小项完成而要求用户再次“继续”。

## 当前禁止事项

未完成基线前不启动 AI 产品实现；不提前合并 PR #9，不复用旧失败轮次，不降低质量/安全门，不动正式作者数据、冻结 tag 和验收历史。旧 V1-AI-1 不另开旁路；模型能力直接进入接续的 AI 阶段，故事规划不再是其前置。
