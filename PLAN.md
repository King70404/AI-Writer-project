# 当前交付

更新：2026-10-25。当前任务：加载 GitHub 更新，在 Windows 分模块测试、修复并逐模块推送。活动 [PR #35](https://github.com/King70404/AI-Writer-project/pull/35)，分支 `codex/windows-module-validation`，目标为 `feature/product-design-implementation`。

## 当前事实与能力

- main：`b1ac8a4f064dd6a5c041e9e672bc987670c786ed`；已交付 V1、AI 协作、范文与章节规划、长篇记忆评审、备份与工程规模评测。既有 Windows 发布证据见 [发布验收](docs/RELEASE_ACCEPTANCE.md)，不能代替本轮新代码验证。
- 本轮输入：远端 `feature/product-design-implementation` / `868f4714974eb39c8b49e3242be82ae3c9538896`，含 A1/A2/B1/B2，已下载到独立工作目录。原工作目录未提交修改保留；未混入本轮。
- A1：作者首页、书架、三栏写作台、专注模式、保存切章、原地模型设置、范文规则捷径。
- A2：服务端字数汇总、分页、作者章节状态与六类派生待办。
- B1：候选对照、模型用量台账；服务商未报告的用量标为未知。
- B2：不可变作者候选修改、作者填写价格、单任务/月预算、发送预估、本机草稿按数据根隔离与冲突对照。
- C–E 仍为设计，入口见 [产品交接](docs/product/README.md)。详细能力边界见 [功能索引](docs/FEATURE_REALITY_MATRIX.md)。

## 当前验证与活动工作

[Windows 模块记录与恢复命令](docs/WINDOWS_MODULE_VALIDATION.md)是本轮恢复入口。用户要求每模块推送检查点，检查点不代表完整验收已通过。

- A1：29 项前端、生产构建、E2E-INT-023 通过，已推送检查点 `4fcebc4`。
- A2：17 项后端、31 项前端、E2E-INT-024 通过，已推送检查点 `ab95116`。
- B1：19 项后端、B1/B2 合计 62 项前端、E2E-INT-025 通过，已推送检查点 `3ccc2f4`。
- B2：18 项后端及 E2E-INT-026 通过；本检查点提交后立即推送。
- 已处理：导航/台账断言的异步竞态、就绪轮询异常属性兼容、Windows 无 symlink 权限的真实目录联接测试。测试工作目录缩短以避免探针超 Windows 路径限制，未提高超时或降低检查。
- 下一步：一次完整 `scripts/quality_gate.ps1 -IncludeE2E`，含升级、Windows Key 保护、备份及清理复核。尚未整体验收通过，不合并/发布。

## 后续顺序与限制

1. 完成本轮 Windows 集成验证并同步精确结果；当前无新的功能扩展。
2. 后续补全书/卷规划、伏笔时间线、可调召回，再接有界跨章任务与旧稿/外部 AI 交接。
3. 仍未实现：检查模型连接、规划保存并准备合并动作、窄屏抽屉助手、全书架汇总；分析/评审发送前预估 UI、缓存 token 计价和 CSV 导出。旧 `/ai/continue`、`/ai/rewrite` 不计量、不受预算约束。
4. 不把受控测试模型的通过写成真实付费模型质量或文学质量已通过；真实费用仍待作者验证。安装包、tag、Release 不在本轮范围。

## 禁止事项

只使用自有隔离根，不读取、迁移或枚举正式创作数据、备份和真实 Key。AI 不自动确认事实/规则或采用正文。不降低测试/coverage，不静音错误，不改 M0–M7 tags 和冻结验收文件。GitHub 已同步状态才是共同事实源。
