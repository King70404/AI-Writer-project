# AIWebNovel

AIWebNovel 是项目暂定名称，目标是开发一套面向中文男频网文作者、在 Windows 11 本地运行，并由 Codex 提供在线创作与语义评审能力的多 Agent 长篇小说创作系统。

## 当前阶段与状态

项目当前处于阶段 0——工程底座。DEV-0.3 已建立可测试的 SQLite、SQLAlchemy 与 Alembic 数据库基础，DEV-0.4 已建立 React、TypeScript 与 Vite 前端工程基础；仓库仍未实现任何小说业务功能。

当前已有 FastAPI、数据库连接和迁移基线等后端基础设施，以及独立运行的前端工程基础页；前端尚未连接后端，也没有小说业务表、Agent、Skill、Prompt、工作流或小说业务界面。基础服务、SQLite 文件、迁移基线或前端目录存在都不代表小说业务已经完成。后端环境、数据库迁移和测试说明见 [后端 README](backend/README.md)，前端环境与命令见 [前端 README](frontend/README.md)。

## 计划技术栈

- 后端：Python 3.12.10、FastAPI、Uvicorn、Pydantic、SQLAlchemy 2.x、Alembic；
- 前端：React、TypeScript、Vite；
- 数据库：SQLite，当前基础设施已启用 WAL 和外键；
- 架构：Windows 11 本地优先、模块化单体、本地浏览器界面和持久化工作流；
- 数据治理：候选数据、正式数据与分支数据严格隔离；
- Codex：通过统一的 CodexExecutor 适配器接入。

以上包含当前基础设施和后续阶段计划，不表示业务模型、正式数据存储、前后端集成或完整系统已经完成，也不表示 M0 已完成。

## 开发规范

所有开发工作必须遵守 [Codex 全局开发说明](docs/CODEX_GLOBAL_INSTRUCTIONS.md)，并按 [开发工作流](docs/DEVELOPMENT_WORKFLOW.md) 一次执行一个编号任务。模块所有权与交互限制见 [架构边界](docs/ARCHITECTURE_BOUNDARIES.md)。
