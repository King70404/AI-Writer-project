# 本地质量门禁

质量门禁用于在进入下一编号任务前，以可重复、可失败的检查证明当前工程基线仍然可靠。门禁只验证工程质量，不代表小说业务功能已经实现。

## 统一门禁

在仓库根目录执行默认门禁：

```powershell
.\scripts\quality_gate.ps1
```

脚本按以下顺序执行，任一步返回非零后立即停止，并保留该非零结果：

1. `git diff --check HEAD --`：检查当前差异中的空白错误；
2. 仓库卫生：只检查 Git 已跟踪文件中的本地产物、绝对用户路径和明显凭据；
3. 安全基线：只扫描 Git 已跟踪的生产代码和运行配置，拒绝危险静态模式并验证安全配置、中间件、CSRF、文档与 Uvicorn 策略接线；
4. Ruff 格式检查；
5. Ruff 静态规则；
6. mypy 严格类型检查；
7. 后端与架构测试，包括存储、安全、健康和依赖边界，并分别验证语句和分支覆盖率；
8. `pip check`：验证已安装 Python 依赖的一致性；
9. `npm run quality`：运行前端格式、lint、类型、覆盖率、测试和构建检查；
10. `npm ls --depth=0`：验证前端直接依赖树。

默认门禁不执行联网审计，网络不可用不应导致默认门禁失败。需要按任务要求审计生产依赖时，显式执行：

```powershell
.\scripts\quality_gate.ps1 -IncludeDependencyAudit
```

该模式在默认检查后增加 `npm audit --omit=dev`，可能访问 npm 网络服务。当前不引入 Python 联网漏洞扫描器。

脚本必须从仓库根目录运行，并要求根目录 `.venv`、前端 `node_modules`、64 位 Python 3.12 和 64 位 Node.js 24 已经可用。它不要求工作区干净，也不会格式化、暂存或提交文件。安全静态脚本按任务要求只读取 Git 已跟踪文件，因此完成前应先确认所有拟提交源码已处于暂存区；未跟踪的用户文件不会被读取。默认模式不会启动持久开发服务或浏览器，但后端测试会在各自的临时数据根中创建并清理测试目录和 SQLite，不得触碰正式 `%LOCALAPPDATA%\AIWebNovel`。

## 可选浏览器端到端验收

浏览器 E2E 需要本地 Chromium 缓存、真实服务进程和更长运行时间，因此默认门禁不执行。需要时显式运行：

```powershell
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
```

`-IncludeE2E` 在全部默认检查以及请求的依赖审计之后依次执行：

1. 检查本地 `@playwright/test` 对应的 Chromium 可执行文件；
2. 运行 `npm run e2e`，验收开发模式和生产集成模式；
3. 检查 E2E 专用端口已释放，场景自有数据根、数据库 sidecar、运行目录和成功产物均已清理。

门禁不会自动下载浏览器。浏览器缺失时明确失败，并提示在 `frontend` 目录运行 `npm run e2e:install`。E2E 失败或清理失败都会使统一门禁返回非零。运行方式、网络隔离和失败产物见 [浏览器端到端测试](E2E_TESTING.md)。

## 真实 Windows 冒烟验收

DEV-0.8 还必须从仓库根目录单独执行：

```powershell
.\scripts\check_windows_storage.ps1
```

该脚本不属于默认门禁。它在 LocalAppData 下创建名称唯一的 `AIWebNovel-DEV-0.8-*` 临时兄弟目录，通过 `AIWEBNOVEL_DATA_ROOT` 启动真实 FastAPI，验证 12 个标准目录、`checks.storage=ok`、`checks.database=ok` 和派生数据库位置，然后终止自有进程并精确清理数据库、sidecar 和整个临时根。脚本只检查正式默认根是否存在，不读取其内容，也不修改 ACL；输出只包含临时根叶名，不包含本机绝对路径或用户名。

DEV-0.8 的完整验收顺序是：

```powershell
.\scripts\quality_gate.ps1
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
.\scripts\check_windows_storage.ps1
```

DEV-0.9 另有真实运行安全冒烟脚本：

```powershell
.\scripts\check_security_runtime.ps1
```

它使用独立数据根与临时环回端口验证 Host、代理头、请求限制、内容类型、会话 Cookie、CSRF、响应头、生产文档关闭和日志脱敏。该脚本不属于默认门禁，不能替代三种规定门禁；安全边界见 [本地应用安全基线](SECURITY_BASELINE.md)。

DEV-0.9 的完整验收顺序是：

```powershell
.\scripts\quality_gate.ps1
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
.\scripts\check_security_runtime.ps1
```

## 只运行后端检查

以下命令均从仓库根目录执行。显式指定配置文件，避免根目录运行时依赖工具的配置发现细节：

```powershell
.\.venv\Scripts\python.exe -m ruff format --check `
  --config backend/pyproject.toml `
  backend/src tests/backend tests/architecture

.\.venv\Scripts\python.exe -m ruff check `
  --config backend/pyproject.toml `
  backend/src tests/backend tests/architecture

.\.venv\Scripts\python.exe -m mypy `
  --config-file backend/pyproject.toml `
  backend/src/aiwebnovel

$coverageReport = Join-Path $env:TEMP `
  "aiwebnovel-backend-coverage-$PID-$([guid]::NewGuid().ToString('N')).json"
try {
  .\.venv\Scripts\python.exe -m pytest `
    tests/backend tests/architecture `
    --cov=aiwebnovel `
    --cov-branch `
    --cov-config=backend/pyproject.toml `
    --cov-report=term-missing `
    --cov-report="json:$coverageReport" `
    --cov-fail-under=0
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

  .\.venv\Scripts\python.exe scripts/check_backend_coverage.py $coverageReport
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
  Remove-Item -LiteralPath $coverageReport -Force -ErrorAction SilentlyContinue
}

.\.venv\Scripts\python.exe -m pip check
```

覆盖率 JSON 只写入系统临时目录，并在 `finally` 中删除。Python 检查器直接使用 coverage.py JSON 的计数，独立计算：

- `covered_lines / num_statements >= 80%`；
- `covered_branches / num_branches >= 75%`。

`--cov-fail-under=0` 避免 coverage.py 把语句和分支合并成一个百分比后误代替上述两个独立门槛；测试失败仍会返回非零，两个覆盖率门槛由检查器强制执行。

## 只运行前端检查

在 `frontend` 目录执行：

```powershell
npm run format:check
npm run lint
npm run typecheck
npm run test:coverage
npm run build
npm ls --depth=0
```

也可以用 `npm run quality` 顺序运行本项目定义的全部前端质量检查。前端覆盖率门槛为：statements 80%、branches 75%、functions 80%、lines 80%。仅在任务明确要求联网审计时另外运行 `npm audit --omit=dev`。

## 显式格式化

格式化不是质量门禁的隐式步骤。需要改写格式时，在仓库根目录显式运行：

```powershell
.\scripts\format_code.ps1
```

该脚本只运行 Ruff 安全修复与格式化，以及前端 Prettier 格式化；它不会运行 `git add`、创建提交或修改锁文件。执行后必须人工审查 `git diff`，再重新运行统一门禁。

## 架构与仓库卫生

后端架构测试保护阶段 0 的依赖方向：`storage` 只向 `core` 依赖，`db` 只能读取公开的存储路径契约，`security` 不访问存储、数据库或 Web，会话管理器保持纯内存，`web` 只可使用公开安全 DTO/响应契约，低层不得导入 `main`，生产代码不得导入测试代码或在配置边界外重新解析 LocalAppData；`main` 是组合 `core`、`storage`、`db`、`security` 和 `web` 的唯一组合根。前端边界检查阻止 API、组件等低层代码反向依赖页面，并阻止生产源码导入测试代码。更高层业务模块边界仍以 [架构边界](ARCHITECTURE_BOUNDARIES.md) 为准。

仓库卫生脚本只使用 `git ls-files` 枚举并读取已跟踪文件，不读取未跟踪的用户文件。它发现疑似秘密时只输出仓库相对文件名和问题类型，不输出匹配值；不会自动删除文件，也不会改写 `.gitignore`。

安全静态脚本可单独从仓库根目录执行：

```powershell
.\scripts\check_security_baseline.ps1
```

它同样只通过 `git ls-files` 读取跟踪的生产代码和运行配置，不联网、不自动修复，也不打印匹配值。受控架构测试分别证明安全接线可通过、跟踪违规会非零失败、未跟踪文件不会被读取且 canary 不会进入输出。静态模式检查只是一层快速防回归，不能替代真实请求测试、E2E 或安全冒烟。

## 失败规则与当前边界

任何适用门禁失败，都不得声称当前任务完成，也不得开始下一编号任务。应先修复真实原因并完整重跑；不得降低阈值、跳过检查或把失败输出为成功。

DEV-0.9 已把安全基线静态检查、Security 架构边界和受控负向测试纳入默认门禁，并保持 Chromium 浏览器验收为显式可选项；真实 Windows 存储与安全冒烟仍需按各自任务单独执行。本阶段仍没有用户登录、业务写入 API、Project、写作、评审、Agent、Skill、Prompt、备份、导出或其他小说业务功能。
