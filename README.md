# AIWebNovel

AIWebNovel 是项目暂定名称，目标是开发一套面向中文男频网文作者、在 Windows 11 本地运行，并由 Codex 提供在线创作与语义评审能力的多 Agent 长篇小说创作系统。

## 当前阶段与状态

阶段 0——工程底座已通过 DEV-0.11 正式验收并冻结为 M0。阶段 1 当前里程碑为 M1：DEV-1.1至DEV-1.4建立通用领域原语、Project三表与Repository、应用命令和Snapshot；DEV-1.5新增严格的Project创建、当前读取和完整修订HTTP API。当前仍没有Project列表、历史、删除、归档或前端项目管理页面。M0正式结果与冻结范围见 [M0 正式验收报告](docs/M0_ACCEPTANCE_REPORT.md)，Project HTTP契约见 [Project HTTP API](docs/PROJECT_HTTP_API.md)。

当前工程基础页会通过相对 `/api/v1` 请求真实检查本地 FastAPI、安全配置、存储目录访问能力与 SQLite 基础状态。开发模式由 Vite 仅代理 `/api`，生产集成模式可由 FastAPI 提供本地 Vite 构建与受限 SPA 回退。默认用户数据根是 `%LOCALAPPDATA%\AIWebNovel`，正式数据不存放在 Git 仓库。迁移`0002_create_project_foundation`定义Project、Revision和Head结构，应用启动不会自动执行迁移；未迁移数据库上的Project API安全返回503。项目仍没有用户登录、小说创作业务、Agent、Skill、Prompt、工作流或Project前端界面；健康检查通过不代表系统已经能够创作小说。

## 本地运行模式

先从仓库根目录运行只读环境诊断。诊断不会联网安装、升级或修复软件，也不会修改项目、Git 配置或正式用户数据：

```powershell
.\scripts\environment_doctor.ps1 -Mode Development
```

开发模式由一个前台脚本启动 FastAPI 与 Vite，二者都只绑定 `127.0.0.1`：

```powershell
.\scripts\start_development.ps1
```

浏览器访问 `http://127.0.0.1:5173`。Vite 只把 `/api` 代理到本次启动的后端端口。默认数据根为 `%LOCALAPPDATA%\AIWebNovel-Development`，与正式 `%LOCALAPPDATA%\AIWebNovel` 隔离。

生产集成模式默认使用已有 `frontend/dist`，只启动提供 API 和静态前端的 FastAPI：

```powershell
.\scripts\start_integrated.ps1
```

此时浏览器只访问 `http://127.0.0.1:8000`。默认集成数据根为 `%LOCALAPPDATA%\AIWebNovel-Integrated-Development`。只有显式传入 `-BuildFrontend` 才会运行本地构建；两个启动入口都不会安装依赖、运行迁移或自动打开浏览器。按 `Ctrl+C` 停止时，脚本只清理本次拥有且 PID 与启动时间均匹配的进程树，并检查端口释放。参数、失败行为和数据隔离规则见 [本地统一启动](docs/LOCAL_STARTUP.md)。

## 计划技术栈

- 后端：Python 3.12.10、FastAPI、Uvicorn、Pydantic、SQLAlchemy 2.x、Alembic；
- 前端：React、TypeScript、Vite；
- 数据库：SQLite，当前基础设施已启用 WAL 和外键；
- 架构：Windows 11 本地优先、模块化单体、本地浏览器界面和持久化工作流；
- 数据治理：候选数据、正式数据与分支数据严格隔离；
- Codex：通过统一的 CodexExecutor 适配器接入。

以上包含已冻结的 M0 工程基础、Project内部持久化结构、事务Repository与内部应用用例，以及后续阶段计划，不表示用户可见Project功能或完整系统已经完成，也不表示备份、导出、模型管理、文件日志、小说创作或 Codex 能力已经实现。

## 本地质量门禁

在仓库根目录运行 `.\scripts\quality_gate.ps1` 可统一检查 Git 差异、仓库卫生、安全与启动脚本静态基线、Diagnostics 单元测试、后端格式、类型、测试和覆盖率，以及前端格式、lint、类型、测试、覆盖率和构建。默认门禁不依赖网络，也不启动长期服务；任一检查失败都不得开始下一编号任务。单项命令、覆盖率阈值和可选依赖审计见 [本地质量门禁](docs/QUALITY_GATES.md)。门禁通过只证明当前工程基线满足质量要求，不代表小说业务功能已实现。

M0 预验收使用 `.\scripts\m0_preflight.ps1`，按固定顺序组合严格诊断、完整门禁、真实启动、存储与安全烟测以及清理检查，并在被 Git 忽略的 `.runtime/m0-preflight/` 生成证据。预验收本身仍只表示已准备好等待正式阶段验收；M0 的正式通过结论以 [M0 正式验收报告](docs/M0_ACCEPTANCE_REPORT.md) 和 [M0 验收清单](docs/M0_ACCEPTANCE_CHECKLIST.md) 为准。

## 浏览器端到端测试

在 `frontend` 目录运行 `npm run e2e:dev`、`npm run e2e:integrated` 或 `npm run e2e`，可用 Playwright 管理的无头 Chromium 验证开发与生产集成启动。浏览器只访问 E2E 专用的 `127.0.0.1` 端口，每个场景使用独立临时数据根，其 SQLite 位于 `data/`、运行数据位于 `runtime/`，并在结束后清理自有进程、端口和整个临时根。浏览器安装、失败诊断和 `-IncludeE2E` 可选门禁说明见 [浏览器端到端测试](docs/E2E_TESTING.md)。这些验收不代表已经存在小说业务功能。

## 开发规范

所有开发工作必须遵守 [Codex 全局开发说明](docs/CODEX_GLOBAL_INSTRUCTIONS.md)，并按 [开发工作流](docs/DEVELOPMENT_WORKFLOW.md) 一次执行一个编号任务。模块所有权与交互限制见 [架构边界](docs/ARCHITECTURE_BOUNDARIES.md)。
