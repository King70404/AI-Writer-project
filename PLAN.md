# 当前接力：现在在哪里，下一步交付什么

更新：2026-09-15。先按 [AGENTS.md](AGENTS.md) 核对 GitHub；本页只保存当前有效状态。

## 当前阶段与已完成成果

**处于第一阶段“稳定现有 V1”的收尾，尚未进入新一轮 AI 能力开发。**

- M7/V1 已正式验收：小说/设定/人物管理，大纲/卷/章，正文编辑与自动保存，本地 AI 续写/改写、作者确认采用、TXT 导出。实际前提与限制见 [功能索引](docs/FEATURE_REALITY_MATRIX.md)。
- [PR #9](https://github.com/King70404/AI-Writer-project/pull/9) 仍 OPEN、未合并。UX 产品修复提交 `014205985d5e3acfe5cd38cc60d108df495ed42d`；[R4 #20](https://github.com/King70404/AI-Writer-project/issues/20#issuecomment-5677994354) 已关闭 completed。
- R4 开发证据：Default PASS；后端 2778、前端 676、完整浏览器 24 项通过；已知 structure 测试完成 20+5 次稳定性验证。**这是开发结果，尚无新 RC/formal PASS。**
- 最近核实的远端 `main`：`0939e3a0a753dc819ab0f5bc6f4496198c3290dd`。文档整理会产生新的 PR head，下一 RC 必须重新读取并冻结精确 SHA，不复用 R4 开发日志作为新 SHA 验收。
- 旧失败仅作追溯：[Q1 #10](https://github.com/King70404/AI-Writer-project/issues/10)、[Q2 #14](https://github.com/King70404/AI-Writer-project/issues/14)、[RC1 #18](https://github.com/King70404/AI-Writer-project/issues/18#issuecomment-5646556594)；不重开这些轮次。

## 最近完成的整理

[DOC-GOV-2 #21](https://github.com/King70404/AI-Writer-project/issues/21)：已精简入口、删除过期协调快照、修正 README、归档旧愿景，并形成五阶段路线。默认入口文字量减少约 60%，28 份历史正文退出普通搜索；67 条链接与 9 项文档相关契约测试通过。源码、24 份冻结文件和 8 个本地 tag 不变；最终提交及结项记录见 #21。

## 当前 blocker 与下一步

GitHub 连接已恢复，R4 收尾已同步。当前剩余的是候选/基线验证，而非此前已修复的 locator、NaN 或历史读取漏洞。

**下一步一次交付“可放心继续开发的 V1 基线”**，按以下依赖连续完成：

1. 同步文档后的 PR head 与最新 main，记录新的 RC2；按 [稳定性协议](docs/ACCEPTANCE_STABILITY.md) 在同一冻结 SHA 完成 Default、两次 IncludeE2E、真实根 launcher 隔离 smoke、完整作者 UX/delete smoke 及边界验证。
2. 全部通过后创建独立 formal acceptance；正式 PASS 后合并 PR #9、结束 UX，记录最终 main SHA。
3. 完成 [Windows CI #17](https://github.com/King70404/AI-Writer-project/issues/17)，使最新提交有真实 GitHub 检查；满足前置条件后关闭 [RF-00 #11](https://github.com/King70404/AI-Writer-project/issues/11)。

待核实项：本地 8 个冻结 tag 未变，但此前远端 tag 清单为空，需核实可见性，不能擅自补推；GitHub required rules 曾受套餐/owner 权限限制，CI 实际运行与管理设置须分别如实记录。当前未运行 RC2，不存在可宣称已通过的新正式候选。

## 再下一步与后续

| 顺序       | 完整交付成果                                                 | 原 RF 清单       |
| ---------- | ------------------------------------------------------------ | ---------------- |
| 1 当前     | 稳定 V1、完成验收与 CI、锁定基线                             | RF-00 + UX + #17 |
| 2 再下一步 | 故事规划基础：场景、剧情推进点、故事资产与写作规则           | RF-01–05         |
| 3          | 可控 AI 写作闭环：模型接入、上下文、候选、确认采纳、连续生成 | RF-06–10         |
| 4          | 长篇记忆、一致性评审与统一作者工作台                         | RF-11–14         |
| 5          | 安全升级/备份恢复、长篇评测与发布                            | RF-15–17         |

每阶段的完成定义见 [交付路线](docs/REFRACTOR_ROADMAP.md)。阶段内 RF 项串行推进，不因每个小项完成而要求用户再次“继续”。

## 当前禁止事项

未完成基线前不开始 RF-01+ 产品实现；不提前合并 PR #9，不复用旧失败轮次，不降低质量/安全门，不动正式作者数据、冻结 tag 和验收历史。旧 V1-AI-1 不另开旁路，模型能力统一进入第三阶段。
