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
3. Ruff 格式检查；
4. Ruff 静态规则；
5. mypy 严格类型检查；
6. 后端与架构测试，并分别验证语句和分支覆盖率；
7. `pip check`：验证已安装 Python 依赖的一致性；
8. `npm run quality`：运行前端格式、lint、类型、覆盖率、测试和构建检查；
9. `npm ls --depth=0`：验证前端直接依赖树。

默认门禁不执行联网审计，网络不可用不应导致默认门禁失败。需要按任务要求审计生产依赖时，显式执行：

```powershell
.\scripts\quality_gate.ps1 -IncludeDependencyAudit
```

该模式在默认检查后增加 `npm audit --omit=dev`，可能访问 npm 网络服务。当前不引入 Python 联网漏洞扫描器。

脚本必须从仓库根目录运行，并要求根目录 `.venv`、前端 `node_modules`、64 位 Python 3.12 和 64 位 Node.js 24 已经可用。它不要求工作区干净，也不会格式化、暂存或提交文件。默认模式不会启动服务器、数据库或浏览器。

## 可选浏览器端到端验收

浏览器 E2E 需要本地 Chromium 缓存、真实服务进程和更长运行时间，因此默认门禁不执行。需要时显式运行：

```powershell
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
```

`-IncludeE2E` 在全部默认检查以及请求的依赖审计之后依次执行：

1. 检查本地 `@playwright/test` 对应的 Chromium 可执行文件；
2. 运行 `npm run e2e`，验收开发模式和生产集成模式；
3. 检查 E2E 专用端口已释放且 `.runtime/e2e` 不含临时数据。

门禁不会自动下载浏览器。浏览器缺失时明确失败，并提示在 `frontend` 目录运行 `npm run e2e:install`。E2E 失败或清理失败都会使统一门禁返回非零。运行方式、网络隔离和失败产物见 [浏览器端到端测试](E2E_TESTING.md)。

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

后端架构测试保护阶段 0 的依赖方向：`core` 不依赖 `db` 或 `web`，`db` 不依赖 `web`，`web` 不直接依赖 `db`，生产代码不导入测试代码；`main` 是允许组合基础层的组合根。前端边界检查阻止 API、组件等低层代码反向依赖页面，并阻止生产源码导入测试代码。更高层业务模块边界仍以 [架构边界](ARCHITECTURE_BOUNDARIES.md) 为准。

仓库卫生脚本只使用 `git ls-files` 枚举并读取已跟踪文件，不读取未跟踪的用户文件。它发现疑似秘密时只输出仓库相对文件名和问题类型，不输出匹配值；不会自动删除文件，也不会改写 `.gitignore`。

## 失败规则与当前边界

任何适用门禁失败，都不得声称当前任务完成，也不得开始下一编号任务。应先修复真实原因并完整重跑；不得降低阈值、跳过检查或把失败输出为成功。

DEV-0.7 已建立可选的 Chromium 浏览器端到端验收，但不把它放入默认离线门禁。本阶段仍没有 Project、写作、评审、Agent、Skill、Prompt 或其他小说业务功能。
