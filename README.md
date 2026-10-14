# AIWebNovel

面向中文网文作者的 Windows 本地单用户写作应用。项目目标是让作者管理长篇故事，并在可控上下文和明确确认下使用 AI 写作。

## 现在可以做什么

M7/V1 已验收的流程：

`小说 → 设定/人物 → 大纲/卷/章 → 正文编辑与自动保存 → 本地 AI 续写/改写 → 确认采用 → TXT 导出`

RF-06–10 的 AI 协作流程已完成，通过完整 CI 与隔离作者流程，并在 [PR #25](https://github.com/King70404/AI-Writer-project/pull/25) 合并：

`配置本地/云端模型 → 预览实际上下文 → 生成并保留候选 → 作者确认采纳 → 继续生成、暂停或恢复`

需自备 OpenAI-compatible 模型服务；云端 API Key 受 Windows DPAPI 保护。任务与候选持久保存，连续生成每段 200–300 字，未经作者确认不写入正文。使用方法和限制见 [AI 协作说明](docs/AI_COLLABORATION.md)；长期故事记忆仍属后续阶段。

范文学习与长篇准备的使用入口见 [范文分析与章节规划](docs/REFERENCE_WRITING.md)：粘贴句段、对照分析、确认可复用的方法，再按章选用规则、场景与连续性要求。当前实现及验证状态以 [PLAN.md](PLAN.md) 为准。

当前交付状态见 [PLAN.md](PLAN.md)，能力边界见 [功能索引](docs/FEATURE_REALITY_MATRIX.md)。

## 从哪里开始

- 继续开发：先读 [AGENTS.md](AGENTS.md) 和 [PLAN.md](PLAN.md)。
- 看未来五个交付阶段：[开发路线](docs/REFRACTOR_ROADMAP.md)。
- 启动、停止、数据隔离：[本地启动](docs/LOCAL_STARTUP.md)。
- 配置模型、查看上下文、采纳候选与暂停恢复：[AI 协作说明](docs/AI_COLLABORATION.md)。
- 运行检查：[质量门](docs/QUALITY_GATES.md)；浏览器检查：[E2E](docs/E2E_TESTING.md)。
- 修改模块时再读对应契约与 [架构边界](docs/ARCHITECTURE_BOUNDARIES.md)。历史材料不属于默认阅读入口。

## 本地运行

开发环境诊断与启动：

```powershell
.\scripts\environment_doctor.ps1 -Mode Development
.\scripts\start_development.ps1
```

开发根为 `%LOCALAPPDATA%\AIWebNovel-Development`。普通作者可双击根目录 `启动 AI 网文助手.cmd`；它使用集成启动和正式 `%LOCALAPPDATA%\AIWebNovel`。测试、smoke 和诊断写入必须显式使用自有隔离根。

集成模式使用已有 `frontend/dist`，在 `http://127.0.0.1:8000` 提供应用；显式 `-BuildFrontend` 才构建。新数据库可自动初始化，已有数据库不会被启动脚本自动迁移或重置。环境前提与完整参数见启动文档。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / Alembic / SQLite；React / TypeScript / Vite；服务只监听 loopback。
