# AIWebNovel 后端

本目录包含阶段 0 的 Python 后端基础设施。目前提供 FastAPI 应用工厂、类型化配置、严格本地 CORS、标准输出 JSON 日志、请求 ID、统一 API 错误格式、Windows 本地存储路径与访问探针、同步 SQLAlchemy SQLite 引擎、请求级会话管理、Alembic 迁移环境、存活与就绪健康检查，以及可选的 Vite 构建静态服务。

当前没有任何小说业务表、业务 Repository、Codex 调用、工作流或小说业务 API。健康检查成功仅表示基础后端、配置、当前进程的存储读写删除能力、数据库连接和按配置要求的前端构建可用，不表示小说数据已经可以保存，也不表示备份、导出、模型管理、文件日志或小说系统已经完成。

## 环境要求

- Windows 11；
- Python 3.12.10；
- 默认只监听 `127.0.0.1`。

## 创建虚拟环境并安装

在仓库根目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e "backend[dev]"
```

## 开发模式

在仓库根目录启动后端：

```powershell
$env:AIWEBNOVEL_DATA_ROOT = Join-Path $env:LOCALAPPDATA "AIWebNovel-Development"
.\.venv\Scripts\python.exe -m aiwebnovel
Remove-Item Env:AIWEBNOVEL_DATA_ROOT
```

开发运行必须使用独立的绝对 `AIWEBNOVEL_DATA_ROOT`，不能使用正式 `%LOCALAPPDATA%\AIWebNovel`。上例的开发目录与正式默认根不同；测试和 E2E 还会使用各自唯一的临时根。

另一个终端在 `frontend` 目录运行 `npm run dev`，浏览器只访问 `http://127.0.0.1:5173`。Vite 仅代理 `/api` 到本后端的 `127.0.0.1:8000`；后端仍默认只监听 `127.0.0.1`。

默认健康检查地址：

- `http://127.0.0.1:8000/api/v1/health/live`
- `http://127.0.0.1:8000/api/v1/health/ready`

应用生命周期按“加载配置、解析 `StoragePaths`、初始化标准目录、执行访问探针、创建数据库引擎、进入就绪判断”的顺序启动。就绪检查会先报告真实 `checks.storage`，再执行数据库连接、`SELECT 1`、外键状态和文件型 SQLite WAL 状态检查。存储失败时 ready 返回 503，`checks.storage` 与 `checks.database` 统一为 `failed`，live 仍尽量返回 200；响应不包含数据根、数据库、探针路径或底层系统异常。`checks.frontend` 在静态服务关闭、有效构建和无效构建时分别为 `not_required`、`ok` 和 `failed`。应用启动不会静默执行 Alembic 升级，也不会自动创建、删除或重建业务表。

## 生产集成模式

先在前端目录生成被 Git 忽略的本地构建，再显式启用静态服务：

```powershell
Set-Location frontend
npm run build
Set-Location ..
$env:AIWEBNOVEL_DATA_ROOT = Join-Path $env:LOCALAPPDATA "AIWebNovel-Development"
$env:AIWEBNOVEL_SERVE_FRONTEND = "true"
.\.venv\Scripts\python.exe -m aiwebnovel
Remove-Item Env:AIWEBNOVEL_DATA_ROOT
Remove-Item Env:AIWEBNOVEL_SERVE_FRONTEND
```

默认构建路径为仓库根目录下的相对路径 `frontend/dist`。构建有效时，FastAPI 提供 `/`、实际静态资源和仅面向 HTML 客户端路由的 SPA 回退；`/api` 始终保留给 JSON API。构建缺失时 API 仍可启动且 live 仍为 200，但 ready 和前端根路径会安全返回 503，不公开本机路径。

## 前端服务与 CORS 配置

以下环境变量使用现有 `AIWEBNOVEL_` 配置前缀：

- `AIWEBNOVEL_SERVE_FRONTEND`，默认 `false`；
- `AIWEBNOVEL_FRONTEND_DIST_PATH`，默认 `frontend/dist`；
- `AIWEBNOVEL_CORS_ALLOWED_ORIGINS`，默认仅 `http://127.0.0.1:5173`。

CORS 来源必须是明确的 HTTP(S) origin，不能包含通配符、凭据、路径、查询字符串或片段。列表环境变量使用 JSON，例如：

```powershell
$env:AIWEBNOVEL_CORS_ALLOWED_ORIGINS = '["http://127.0.0.1:5173"]'
```

策略仅允许前端健康检查所需的 `GET`、`OPTIONS`、`Accept` 与 `X-Request-ID`，不允许跨域凭据，并只暴露 `X-Request-ID`。生产同源模式不依赖 CORS。

## 本地存储与数据库配置

未显式覆盖时，数据根从当前进程 `LOCALAPPDATA` 解析为 `%LOCALAPPDATA%\AIWebNovel`，数据库 URL 由不可变 `StoragePaths.database_file` 安全派生，等价文件位置为：

```text
%LOCALAPPDATA%\AIWebNovel\data\aiwebnovel.sqlite3
```

旧的仓库相对 `.runtime/aiwebnovel-dev.sqlite3` 不再是默认值。应用不会读取、迁移或删除旧开发数据库，也不会在配置解析或模块导入时创建目录。标准目录只在 FastAPI 生命周期启动或显式调用存储初始化时按需创建；初始化本身不创建数据库或业务文件。

应用支持以下环境变量：

- `AIWEBNOVEL_DATA_ROOT`：可选的绝对数据根覆盖；相对路径、空路径、空字节和文件系统根会被拒绝；
- `AIWEBNOVEL_DATABASE_URL`：可选的显式 SQLite URL，优先于从数据根派生的 URL；
- `AIWEBNOVEL_DATABASE_ECHO`；
- `AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS`。

没有合法 `AIWEBNOVEL_DATA_ROOT` 覆盖且 `LOCALAPPDATA` 缺失、为空或无效时，不会回退到仓库、用户主目录或临时目录；存储和数据库就绪状态为 `failed`。配置解析不会创建 `.env` 或任何目录。

测试或人工迁移时应始终指定独立临时数据根和临时数据库。例如在仓库根目录执行：

```powershell
$env:AIWEBNOVEL_DATA_ROOT = Join-Path $env:TEMP "AIWebNovel-Migration-Test"
$databasePath = (Join-Path $env:TEMP "aiwebnovel-migration-test.sqlite3").Replace('\', '/')
$env:AIWEBNOVEL_DATABASE_URL = "sqlite+pysqlite:///$databasePath"
```

完整目录结构、访问探针、运行时隔离和 Windows 权限边界见 [本地存储](../docs/LOCAL_STORAGE.md)。

## Alembic 迁移

数据库迁移必须由开发者明确执行，不会随应用启动自动运行：

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini downgrade base
Remove-Item Env:AIWEBNOVEL_DATABASE_URL
Remove-Item Env:AIWEBNOVEL_DATA_ROOT
```

当前初始迁移仅建立 Alembic 基线。除 Alembic 自身的版本表外，不包含任何业务表或业务数据。迁移在用于未来正式数据前必须经过对应任务的审查和验证。

## 后端质量检查

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m ruff format --check --config backend/pyproject.toml backend/src tests/backend tests/architecture
.\.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml backend/src tests/backend tests/architecture
.\.venv\Scripts\python.exe -m mypy --config-file backend/pyproject.toml backend/src/aiwebnovel
.\.venv\Scripts\python.exe -m pytest tests/backend tests/architecture --cov=aiwebnovel --cov-branch --cov-config=backend/pyproject.toml
.\.venv\Scripts\python.exe -m pip check
```

完整本地门禁由 `.\scripts\quality_gate.ps1` 负责生成系统临时目录中的覆盖率 JSON，并分别强制语句覆盖率 80% 与分支覆盖率 75%，完成后删除报告。完整命令和失败规则见 [本地质量门禁](../docs/QUALITY_GATES.md)。
