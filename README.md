# AIWebNovel

AIWebNovel 是项目暂定名称，目标是开发一套面向中文男频网文作者、在 Windows 11 本地运行，并由 Codex 提供在线创作与语义评审能力的多 Agent 长篇小说创作系统。

## 当前阶段与状态

项目当前处于阶段 0——工程底座。DEV-0.2 正在建立可安装、可启动和可测试的最小后端基础；仓库仍未实现任何小说业务功能。

当前仅有 FastAPI 健康检查等后端基础设施，没有可运行的前端，也没有初始化数据库、Agent、Skill、Prompt、工作流或用户界面。基础服务或目录存在不代表对应小说功能已经完成。后端环境、启动和测试说明见 [后端 README](backend/README.md)。

## 计划技术栈

- 后端：Python 3.12.10、FastAPI、Uvicorn、Pydantic、SQLAlchemy 2.x、Alembic；
- 前端：React、TypeScript、Vite；
- 数据库：SQLite，计划启用 WAL 和外键；
- 架构：Windows 11 本地优先、模块化单体、本地浏览器界面和持久化工作流；
- 数据治理：候选数据、正式数据与分支数据严格隔离；
- Codex：通过统一的 CodexExecutor 适配器接入。

以上均为后续阶段的技术计划，不表示已经完成依赖安装、应用初始化或数据库初始化。

## 开发规范

所有开发工作必须遵守 [Codex 全局开发说明](docs/CODEX_GLOBAL_INSTRUCTIONS.md)，并按 [开发工作流](docs/DEVELOPMENT_WORKFLOW.md) 一次执行一个编号任务。模块所有权与交互限制见 [架构边界](docs/ARCHITECTURE_BOUNDARIES.md)。
