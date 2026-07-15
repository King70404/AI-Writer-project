# AIWebNovel

AIWebNovel 是项目暂定名称，目标是开发一套面向中文男频网文作者、在 Windows 11 本地运行，并由 Codex 提供在线创作与语义评审能力的多 Agent 长篇小说创作系统。

## 当前阶段与状态

项目当前处于阶段 0——工程底座。DEV-0.3 已建立可测试的 SQLite、SQLAlchemy 与 Alembic 数据库基础，DEV-0.4 已建立 React、TypeScript 与 Vite 前端工程基础，DEV-0.5 已建立本地前后端健康检查集成与可选生产静态服务，DEV-0.6 已建立本地质量门禁，DEV-0.7 已建立真实本地服务的 Chromium 浏览器验收；仓库仍未实现任何小说业务功能。

当前工程基础页会通过相对 `/api/v1` 请求真实检查本地 FastAPI 与 SQLite 基础状态。开发模式由 Vite 仅代理 `/api`，生产集成模式可由 FastAPI 提供本地 Vite 构建与受限 SPA 回退。项目仍没有小说业务表、Agent、Skill、Prompt、工作流或小说业务界面；健康检查通过只代表工程基础可用，不代表系统已经能够创作小说。后端环境、数据库迁移和测试说明见 [后端 README](backend/README.md)，前端环境与命令见 [前端 README](frontend/README.md)，已实现工程能力见 [功能真实性矩阵](docs/FEATURE_REALITY_MATRIX.md)。

## 本地运行模式

开发模式分别启动后端和前端，且都只绑定 `127.0.0.1`：

```powershell
.\.venv\Scripts\python.exe -m aiwebnovel
Set-Location frontend
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。Vite 只把 `/api` 代理到 `http://127.0.0.1:8000`，不代理其他路径或 WebSocket。

生产集成模式先构建前端，再显式启用后端静态服务：

```powershell
Set-Location frontend
npm run build
Set-Location ..
$env:AIWEBNOVEL_SERVE_FRONTEND = "true"
.\.venv\Scripts\python.exe -m aiwebnovel
Remove-Item Env:AIWEBNOVEL_SERVE_FRONTEND
```

此时浏览器只访问 `http://127.0.0.1:8000`。默认 CORS 来源是明确的 `http://127.0.0.1:5173`，不使用通配符，也不启用跨域凭据。

## 计划技术栈

- 后端：Python 3.12.10、FastAPI、Uvicorn、Pydantic、SQLAlchemy 2.x、Alembic；
- 前端：React、TypeScript、Vite；
- 数据库：SQLite，当前基础设施已启用 WAL 和外键；
- 架构：Windows 11 本地优先、模块化单体、本地浏览器界面和持久化工作流；
- 数据治理：候选数据、正式数据与分支数据严格隔离；
- Codex：通过统一的 CodexExecutor 适配器接入。

以上包含当前基础设施和后续阶段计划，不表示业务模型、正式数据存储或完整系统已经完成，也不表示 M0 已完成。M0 后续仍有正式本地数据目录等任务。

## 本地质量门禁

在仓库根目录运行 `.\scripts\quality_gate.ps1` 可统一检查 Git 差异与仓库卫生、后端格式、类型、测试和覆盖率，以及前端格式、lint、类型、测试、覆盖率和构建。默认门禁不依赖网络；任一检查失败都不得开始下一编号任务。单项命令、覆盖率阈值和可选依赖审计见 [本地质量门禁](docs/QUALITY_GATES.md)。门禁通过只证明当前工程基线满足质量要求，不代表小说业务功能已实现。

## 浏览器端到端测试

在 `frontend` 目录运行 `npm run e2e:dev`、`npm run e2e:integrated` 或 `npm run e2e`，可用 Playwright 管理的无头 Chromium 验证开发与生产集成启动。浏览器只访问 E2E 专用的 `127.0.0.1` 端口，服务使用独立临时 SQLite，并在结束后清理自有进程、端口和临时数据。浏览器安装、失败诊断和 `-IncludeE2E` 可选门禁说明见 [浏览器端到端测试](docs/E2E_TESTING.md)。这些验收不代表已经存在小说业务功能。

## 开发规范

所有开发工作必须遵守 [Codex 全局开发说明](docs/CODEX_GLOBAL_INSTRUCTIONS.md)，并按 [开发工作流](docs/DEVELOPMENT_WORKFLOW.md) 一次执行一个编号任务。模块所有权与交互限制见 [架构边界](docs/ARCHITECTURE_BOUNDARIES.md)。
