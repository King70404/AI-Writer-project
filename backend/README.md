# AIWebNovel 后端

本目录包含阶段 0 的 Python 后端基础设施。目前提供 FastAPI 应用工厂、类型化配置、严格本地 CORS、标准输出 JSON 日志、请求 ID、统一 API 错误格式、同步 SQLAlchemy SQLite 引擎、请求级会话管理、Alembic 迁移环境、存活与就绪健康检查，以及可选的 Vite 构建静态服务。

当前没有任何小说业务表、业务 Repository、Codex 调用、工作流或小说业务 API。健康检查成功仅表示基础后端、配置、数据库连接和按配置要求的前端构建可用，不表示小说数据已经可以保存，也不表示小说系统已经完成。

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
.\.venv\Scripts\python.exe -m aiwebnovel
```

另一个终端在 `frontend` 目录运行 `npm run dev`，浏览器只访问 `http://127.0.0.1:5173`。Vite 仅代理 `/api` 到本后端的 `127.0.0.1:8000`；后端仍默认只监听 `127.0.0.1`。

默认健康检查地址：

- `http://127.0.0.1:8000/api/v1/health/live`
- `http://127.0.0.1:8000/api/v1/health/ready`

就绪检查会真实执行数据库连接、`SELECT 1`、外键状态和文件型 SQLite WAL 状态检查。`checks.frontend` 在静态服务关闭、有效构建和无效构建时分别为 `not_required`、`ok` 和 `failed`。应用启动不会静默执行 Alembic 升级，也不会自动创建、删除或重建业务表。

## 生产集成模式

先在前端目录生成被 Git 忽略的本地构建，再显式启用静态服务：

```powershell
Set-Location frontend
npm run build
Set-Location ..
$env:AIWEBNOVEL_SERVE_FRONTEND = "true"
.\.venv\Scripts\python.exe -m aiwebnovel
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

## 阶段 0 数据库配置

默认开发数据库 URL 为：

```text
sqlite+pysqlite:///./.runtime/aiwebnovel-dev.sqlite3
```

该路径只用于阶段 0 本地开发，不是最终用户数据路径。正式用户数据目录将在后续 DEV-0.7 迁移为 `%LOCALAPPDATA%\AIWebNovel`；本任务不会访问或创建该正式目录。

应用支持以下环境变量：

- `AIWEBNOVEL_DATABASE_URL`
- `AIWEBNOVEL_DATABASE_ECHO`
- `AIWEBNOVEL_DATABASE_BUSY_TIMEOUT_MS`

测试或人工迁移时应始终指定临时数据库。例如在仓库根目录执行：

```powershell
$databasePath = (Join-Path $env:TEMP "aiwebnovel-migration-test.sqlite3").Replace('\', '/')
$env:AIWEBNOVEL_DATABASE_URL = "sqlite+pysqlite:///$databasePath"
```

## Alembic 迁移

数据库迁移必须由开发者明确执行，不会随应用启动自动运行：

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini downgrade base
Remove-Item Env:AIWEBNOVEL_DATABASE_URL
```

当前初始迁移仅建立 Alembic 基线。除 Alembic 自身的版本表外，不包含任何业务表或业务数据。迁移在用于未来正式数据前必须经过对应任务的审查和验证。

## 测试

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/backend -q
.\.venv\Scripts\python.exe -m pip check
```
