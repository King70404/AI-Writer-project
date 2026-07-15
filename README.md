# AIWebNovel

AIWebNovel 是项目暂定名称，目标是开发一套面向中文男频网文作者、在 Windows 11 本地运行，并由 Codex 提供在线创作与语义评审能力的多 Agent 长篇小说创作系统。

## 当前阶段与状态

项目当前处于阶段 0——工程底座。DEV-0.3 已建立数据库基础，DEV-0.4 至 DEV-0.5 已建立前端与本地健康集成，DEV-0.6 至 DEV-0.7 已建立本地质量门禁和 Chromium 浏览器验收，DEV-0.8 已建立 Windows 本地数据目录与运行时隔离，DEV-0.9 已建立环回、Host、请求限制、本地临时会话、CSRF、安全响应头和日志脱敏基线；仓库仍未实现任何小说业务功能。

当前工程基础页会通过相对 `/api/v1` 请求真实检查本地 FastAPI、安全配置、存储目录访问能力与 SQLite 基础状态。开发模式由 Vite 仅代理 `/api`，生产集成模式可由 FastAPI 提供本地 Vite 构建与受限 SPA 回退。默认用户数据根是 `%LOCALAPPDATA%\AIWebNovel`，正式数据不存放在 Git 仓库；目录只在应用生命周期启动或显式初始化时按需创建。项目仍没有用户登录、小说业务写入 API、业务表、Agent、Skill、Prompt、工作流或小说业务界面；健康检查通过只代表工程基础可用，不代表系统已经能够创作小说。安全边界见 [本地应用安全基线](docs/SECURITY_BASELINE.md)，存储规则见 [本地存储](docs/LOCAL_STORAGE.md)，后端环境、数据库迁移和测试说明见 [后端 README](backend/README.md)，前端环境与命令见 [前端 README](frontend/README.md)，已实现工程能力见 [功能真实性矩阵](docs/FEATURE_REALITY_MATRIX.md)。

## 本地运行模式

开发模式分别启动后端和前端，且都只绑定 `127.0.0.1`：

```powershell
$env:AIWEBNOVEL_DATA_ROOT = Join-Path $env:LOCALAPPDATA "AIWebNovel-Development"
.\.venv\Scripts\python.exe -m aiwebnovel
Remove-Item Env:AIWEBNOVEL_DATA_ROOT

Set-Location frontend
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。Vite 只把 `/api` 代理到 `http://127.0.0.1:8000`，不代理其他路径或 WebSocket。开发者必须使用独立的绝对 `AIWEBNOVEL_DATA_ROOT`，不得把开发运行指向正式默认根。

生产集成模式先构建前端，再显式启用后端静态服务：

```powershell
Set-Location frontend
npm run build
Set-Location ..
$env:AIWEBNOVEL_DATA_ROOT = Join-Path $env:LOCALAPPDATA "AIWebNovel-Development"
$env:AIWEBNOVEL_ENVIRONMENT = "production"
$env:AIWEBNOVEL_SERVE_FRONTEND = "true"
.\.venv\Scripts\python.exe -m aiwebnovel
Remove-Item Env:AIWEBNOVEL_DATA_ROOT
Remove-Item Env:AIWEBNOVEL_ENVIRONMENT
Remove-Item Env:AIWEBNOVEL_SERVE_FRONTEND
```

此时浏览器只访问 `http://127.0.0.1:8000`。默认 CORS 来源是明确的 `http://127.0.0.1:5173`，不使用通配符，也不启用跨域凭据。服务不支持 LAN，不信任代理转发头，production 默认关闭 API 文档。

## 计划技术栈

- 后端：Python 3.12.10、FastAPI、Uvicorn、Pydantic、SQLAlchemy 2.x、Alembic；
- 前端：React、TypeScript、Vite；
- 数据库：SQLite，当前基础设施已启用 WAL 和外键；
- 架构：Windows 11 本地优先、模块化单体、本地浏览器界面和持久化工作流；
- 数据治理：候选数据、正式数据与分支数据严格隔离；
- Codex：通过统一的 CodexExecutor 适配器接入。

以上包含当前基础设施和后续阶段计划，不表示业务模型、业务数据持久化或完整系统已经完成，也不表示备份、导出、模型管理、文件日志或 M0 已经完成。

## 本地质量门禁

在仓库根目录运行 `.\scripts\quality_gate.ps1` 可统一检查 Git 差异、仓库卫生、Git 跟踪代码的安全基线、后端格式、类型、测试和覆盖率，以及前端格式、lint、类型、测试、覆盖率和构建。默认门禁不依赖网络；任一检查失败都不得开始下一编号任务。单项命令、覆盖率阈值和可选依赖审计见 [本地质量门禁](docs/QUALITY_GATES.md)。门禁通过只证明当前工程基线满足质量要求，不代表小说业务功能已实现。

## 浏览器端到端测试

在 `frontend` 目录运行 `npm run e2e:dev`、`npm run e2e:integrated` 或 `npm run e2e`，可用 Playwright 管理的无头 Chromium 验证开发与生产集成启动。浏览器只访问 E2E 专用的 `127.0.0.1` 端口，每个场景使用独立临时数据根，其 SQLite 位于 `data/`、运行数据位于 `runtime/`，并在结束后清理自有进程、端口和整个临时根。浏览器安装、失败诊断和 `-IncludeE2E` 可选门禁说明见 [浏览器端到端测试](docs/E2E_TESTING.md)。这些验收不代表已经存在小说业务功能。

## 开发规范

所有开发工作必须遵守 [Codex 全局开发说明](docs/CODEX_GLOBAL_INSTRUCTIONS.md)，并按 [开发工作流](docs/DEVELOPMENT_WORKFLOW.md) 一次执行一个编号任务。模块所有权与交互限制见 [架构边界](docs/ARCHITECTURE_BOUNDARIES.md)。
