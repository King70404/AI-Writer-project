# AIWebNovel 后端

本目录包含已冻结的阶段 0 Python 后端基础设施，以及DEV-1.1至DEV-1.6的Project领域、持久化、应用与HTTP适配层。目前提供四个Project业务接口、稳定Keyset列表读取、严格Pydantic DTO、ETag/If-Match并发协议、安全错误映射和显式组合根装配。

当前没有用户账号或登录、Project历史/删除接口、前端Project页面、搜索、筛选、Codex调用或工作流。Project POST与PUT要求Origin、本地Session和CSRF；详情与列表GET可匿名本地读取。应用不会自动迁移或建表，安全session只是本机浏览器CSRF基础，不代表身份认证。

## 领域基础

`src/aiwebnovel/domain/`只依赖Python标准库，提供标准ULID、进程内单调生成、受验证的前缀ULID类型工厂、aware UTC时间、`RevisionNumber`、`ConcurrencyVersion`和安全领域错误。`src/aiwebnovel/db/types.py`使用现有SQLAlchemy把这些值适配为TEXT、INTEGER或UTC时间；通用适配器本身不拥有Project业务规则。

Project模块已拥有`prj`和`prv`两种固定业务ID；Chapter及其他业务ID仍未定义。完整通用语义见[领域基础原语](../docs/DOMAIN_FOUNDATION.md)。

## Project持久化基础

`src/aiwebnovel/project/`的领域部分不依赖数据库，定义稳定Project、不可变ProjectRevision、独立ProjectHead、纯转换规则和框架无关Repository契约。`project/persistence/`保存三个显式ORM记录、双向mapper、固定查询与SQLAlchemy Repository实现；`db/model_registry.py`只在Alembic或明确测试需要时确定性注册模型，不连接数据库或执行迁移。

迁移`0002_create_project_foundation`建立`projects`、`project_revisions`和`project_heads`，使用复合外键防止跨Project Head指针，并以SQLite触发器拒绝Revision UPDATE和DELETE。内部Repository使用`BEGIN IMMEDIATE`、Project与Head双CAS以及每操作独立Session保证原子性；独立列表Reader以一条LEFT JOIN SELECT、不可变创建时间和Project ID降序执行Keyset分页。完整边界见[Project持久化基础](../docs/PROJECT_FOUNDATION.md)、[Project Repository事务边界](../docs/PROJECT_REPOSITORY.md)、[Project HTTP API](../docs/PROJECT_HTTP_API.md)和[Project列表读取](../docs/PROJECT_LISTING.md)。

## Project应用用例

`src/aiwebnovel/project/application/`保持纯Python；列表端口与写Repository分离。`project/web/`单独负责DTO、Snapshot/Page映射、ETag、严格cursor、错误和Router。具体SQLAlchemy Repository与列表Reader只在`main`中用既有Session工厂装配，Router不访问Session或ORM。完整输入顺序见[Project应用用例](../docs/PROJECT_APPLICATION.md)。

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

先在仓库根目录诊断环境，再通过统一前台脚本启动后端与 Vite：

```powershell
.\scripts\environment_doctor.ps1 -Mode Development
.\scripts\start_development.ps1
```

统一脚本默认使用 `%LOCALAPPDATA%\AIWebNovel-Development`，并拒绝正式 `%LOCALAPPDATA%\AIWebNovel` 及与其重叠的路径。测试、启动烟测和 E2E 使用各自唯一的临时根。诊断和启动都不会安装或修复依赖、运行 Alembic 迁移或自动打开浏览器。

浏览器只访问 `http://127.0.0.1:5173`。Vite 仅代理 `/api` 到本次指定的后端端口；后端仍只监听 `127.0.0.1`。脚本保持前台运行，按 `Ctrl+C` 会核验 PID 和启动时间并只清理本次拥有的进程树。

默认健康检查地址：

- `http://127.0.0.1:8000/api/v1/health/live`
- `http://127.0.0.1:8000/api/v1/health/ready`

应用生命周期按“加载配置、注册安全请求边界、解析 `StoragePaths`、初始化标准目录、执行访问探针、创建数据库引擎、进入就绪判断”的顺序启动。ready 真实报告 `checks.security`、`checks.storage` 和 `checks.database`；关键安全配置或中间件失败时 ready 返回 503 且 `checks.security=failed`，live 仍尽量返回 200。响应不包含 Host 原值、会话、令牌、数据根、数据库、探针路径或底层系统异常。`checks.frontend` 在静态服务关闭、有效构建和无效构建时分别为 `not_required`、`ok` 和 `failed`。应用启动不会静默执行 Alembic 升级，也不会自动创建、删除或重建业务表。

## 生产集成模式

从仓库根目录运行统一集成入口。它默认复用已有且有效的 `frontend/dist`，只启动 FastAPI：

```powershell
.\scripts\environment_doctor.ps1 -Mode Integrated
.\scripts\start_integrated.ps1
```

只有需要显式重建时才使用 `.\scripts\start_integrated.ps1 -BuildFrontend`；该选项只运行 `npm run build`，不会运行 `npm install`。集成入口固定为 production、启用静态服务、默认关闭 API 文档，并使用与正式数据根隔离的 `%LOCALAPPDATA%\AIWebNovel-Integrated-Development`。

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

当前策略精确允许`GET`、`POST`、`PUT`、`OPTIONS`；允许`Accept`、`Content-Type`、`If-Match`、`X-Request-ID`和配置的CSRF头，暴露`X-Request-ID`、`ETag`和`Location`。不允许PATCH、DELETE、通配符或跨域凭据；生产同源模式不依赖CORS。

## 本地安全配置

安全配置使用同一 `AIWEBNOVEL_` 前缀：

- `AIWEBNOVEL_TRUSTED_HOSTS`：默认 `127.0.0.1` 与 `localhost`，列表要使用 JSON；
- `AIWEBNOVEL_MAX_REQUEST_BODY_BYTES`：默认 1,048,576；
- `AIWEBNOVEL_SESSION_COOKIE_NAME`：默认 `aiwebnovel_session`；
- `AIWEBNOVEL_SESSION_TTL_SECONDS`：默认 28,800；
- `AIWEBNOVEL_SESSION_MAX_ENTRIES`：默认 16；
- `AIWEBNOVEL_CSRF_HEADER_NAME`：默认 `X-CSRF-Token`；
- `AIWEBNOVEL_EXPOSE_API_DOCS`：development/test 默认开启，production 默认关闭。

启动入口仅允许 `127.0.0.1` 或显式 IPv6 环回值，并向 Uvicorn 显式传入 `proxy_headers=False` 和 `server_header=False`。`GET /api/v1/security/session` 只创建进程内本地 CSRF 会话，设置 HttpOnly、SameSite=Strict、`Path=/api` Cookie；它不是用户登录。POST、PUT、PATCH、DELETE 默认要求合法 Origin、会话 Cookie 和 CSRF 头。完整威胁边界、响应头、CSP、脱敏与明确不做项见 [本地应用安全基线](../docs/SECURITY_BASELINE.md)。

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

当前Alembic head为`0002_create_project_foundation`，包含Project拥有的三张表但不包含任何业务数据。迁移必须由操作者对明确目标显式执行；应用和API不会自动升级Schema。

## 后端质量检查

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m ruff format --check --config backend/pyproject.toml backend/src tests/backend tests/architecture
.\.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml backend/src tests/backend tests/architecture
.\.venv\Scripts\python.exe -m mypy --config-file backend/pyproject.toml backend/src/aiwebnovel
.\.venv\Scripts\python.exe -m pytest tests/backend tests/architecture --cov=aiwebnovel --cov-branch --cov-config=backend/pyproject.toml
.\.venv\Scripts\python.exe -m pip check
```

完整本地门禁由 `.\scripts\quality_gate.ps1` 负责，并在 Python 检查前运行只扫描 Git 跟踪生产代码的安全静态基线。后端语句覆盖率不得低于 80%，分支覆盖率不得低于 75%。完整命令和失败规则见 [本地质量门禁](../docs/QUALITY_GATES.md)。
