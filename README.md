# AIWebNovel

面向中文网文作者的 Windows 本地单用户写作应用。项目目标是让作者管理长篇故事，并在可控上下文和明确确认下使用 AI 写作。

## 现在可以做什么

M7/V1 已验收的流程：

`小说 → 设定/人物 → 大纲/卷/章 → 正文编辑与自动保存 → 本地 AI 续写/改写 → 确认采用 → TXT 导出`

本地 AI 需要已配置、可用的 loopback OpenAI-compatible 模型服务。云模型/API Key、可恢复连续生成、长期故事记忆等见后续路线，当前不宣称已经完成。

作者体验修复已完成开发检查，PR #9 仍等待新的候选验证与正式验收。动态状态只维护在 [PLAN.md](PLAN.md)，能力边界只维护在 [功能索引](docs/FEATURE_REALITY_MATRIX.md)。

## 从哪里开始

- 继续开发：先读 [AGENTS.md](AGENTS.md) 和 [PLAN.md](PLAN.md)。
- 看未来五个交付阶段：[开发路线](docs/REFRACTOR_ROADMAP.md)。
- 启动、停止、数据隔离：[本地启动](docs/LOCAL_STARTUP.md)。
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
