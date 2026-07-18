# 本地开发脚本

本目录包含 AIWebNovel 阶段 0 的环境诊断、统一启动、本地质量治理、预验收与 E2E 编排脚本。脚本不会创建 Git 提交或执行 `git add`；默认质量门禁不会启动开发服务器或浏览器，只有显式启动、烟测、E2E 或 M0 预验收命令会启动受控的本地进程。

## 环境诊断

```powershell
.\scripts\environment_doctor.ps1 -Mode Development
.\scripts\environment_doctor.ps1 -Mode Integrated
.\scripts\environment_doctor.ps1 -Mode M0
.\scripts\environment_doctor.ps1 -Json
```

诊断按稳定顺序输出 `ENV-001` 至 `ENV-012`，不会联网、安装或修复依赖，也不会修改代码、Git 配置或正式数据。退出码 `0`、`1`、`2`、`3` 分别表示 `ready`、`ready_with_warnings`、`not_ready` 和调用参数错误。正式数据根只检查是否存在；读写与数据库探针只在 LocalAppData 下唯一临时诊断根中运行并清理。完整模式差异和脱敏规则见 [环境诊断](../docs/ENVIRONMENT_DIAGNOSTICS.md)。

## 统一本地启动

```powershell
.\scripts\start_development.ps1
.\scripts\start_integrated.ps1
```

开发入口启动 FastAPI 和 Vite，集成入口默认只启动 FastAPI 并提供已有 `frontend/dist`。二者只绑定环回地址，使用不同的隔离开发数据根，不运行迁移、不安装依赖且不自动打开浏览器。公共进程管理辅助能力记录 PID 和启动时间，停止前再次核对，只清理本次拥有的进程树；禁止按名称终止 Python 或 Node。脚本保持前台运行，按 `Ctrl+C` 停止。详细参数和失败行为见 [本地统一启动](../docs/LOCAL_STARTUP.md)。

## M0 预验收

```powershell
.\scripts\m0_preflight.ps1
```

预验收固定运行 M0 严格诊断、默认门禁、依赖审计与 E2E 门禁、两种启动烟测、存储与安全烟测以及清理和 Git 检查。任一步失败立即返回非零；成功证据写入被忽略的 `.runtime/m0-preflight/`。它只证明已准备等待正式阶段验收，不宣告 M0 正式通过，也不属于默认质量门禁。

## 统一质量门禁

```powershell
.\scripts\quality_gate.ps1
```

默认顺序检查 Git 差异、仓库卫生、只面向 Git 跟踪生产代码的安全基线、启动脚本静态安全基线、Ruff 格式与规则、mypy、包含 Diagnostics 的后端测试与覆盖率、Python 依赖完整性、前端质量脚本与 npm 依赖树。任一步失败都会立即返回非零退出码。默认模式不访问网络，也不运行完整 M0 预验收或启动长期服务。

需要额外审计 npm 生产依赖时：

```powershell
.\scripts\quality_gate.ps1 -IncludeDependencyAudit
```

需要在全部既有门禁之后运行真实 Chromium 验收时：

```powershell
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
```

浏览器必须事先通过 `frontend` 的 `npm run e2e:install` 安装；可选门禁不会自动下载。

## E2E 服务编排

`run_e2e.ps1` 由前端 package scripts 以开发、生产集成或全部模式调用，也可用固定 `-Scenario` 编号独立运行单项。它为每个场景在 `.runtime/e2e` 下创建独立运行目录和唯一数据根，由应用把 SQLite 派生到该数据根的 `data/`，在固定 loopback 专用端口启动服务，等待真实 URL，就地运行 Playwright，并在 `finally` 中只终止已保存 PID 与启动时间的自有进程树。删除运行目录或成功产物前会拒绝整个目标树中的重解析点。`run_e2e_service.ps1` 是前台子进程入口，只为该子进程设置数据根、静态服务或 Vite 代理环境，并向父脚本登记实际 Node/Python 进程；登记失败时会终止刚启动的自有进程树。`check_e2e_cleanup.ps1` 从仓库根目录复核端口、临时运行目录和成功运行产物均已释放；显式 `e2e:report` 命令通过 `show_e2e_report.ps1` 打开最近一次保留的失败报告。

完整命令、端口、网络隔离与诊断规则见 [浏览器端到端测试](../docs/E2E_TESTING.md)。

## Windows 本地存储烟测

```powershell
.\scripts\check_windows_storage.ps1
```

该脚本只在 Windows 上运行。它在当前用户的 `LOCALAPPDATA` 下选择带固定 DEV-0.8 标识的唯一临时根，通过 `AIWEBNOVEL_DATA_ROOT` 启动真实后端，验证标准目录、访问探针、派生数据库及 ready 状态，然后只终止已核验身份的自有进程并清理该临时根。脚本对正式默认根只检查是否存在，不枚举、读取、修改或删除其内容，也不修改 ACL 或请求提权。

## 安全基线与真实运行烟测

```powershell
.\scripts\check_security_baseline.ps1
.\scripts\check_security_runtime.ps1
```

`check_security_baseline.ps1` 只使用 `git ls-files` 枚举已跟踪的生产代码和运行配置，检查通配符 CORS、跨域凭据、代理头信任、非环回默认绑定、明文令牌、CSRF 持久存储、敏感日志、Host 验证关闭，以及配置、应用工厂中间件、生产文档、CSRF 和 Uvicorn 安全选项接线。它不读取未跟踪用户文件，不打印匹配值、不联网、不自动修复。架构测试使用受控正负夹具证明跟踪违规返回非零且 canary 不泄漏。

`check_security_runtime.ps1` 在唯一临时数据根和动态环回端口启动 production 集成服务，验证合法/非法 Host、代理头、ready 安全状态、响应头和 CSP、文档关闭、session Cookie、请求限制、内容类型与日志无秘密。它核验实际监听进程归属，结束后必须释放端口并清理数据库、sidecar、诊断与临时根。两个脚本都不是运行时测试的替代品。

## 显式格式化

```powershell
.\scripts\format_code.ps1
```

该脚本会修改 Ruff 和 Prettier 管理的源码与测试文件，但不会修改锁文件、构建物或数据库。运行后必须人工审查 Git 差异，再重新执行统一门禁。

## 仓库卫生

```powershell
.\scripts\check_repository_hygiene.ps1
```

卫生检查只使用 `git ls-files` 得到的跟踪文件，不读取未跟踪的用户文件。它检查不应跟踪的本地产物、用户目录绝对路径和明显凭据。如发现疑似秘密，只报告仓库相对文件名和问题类型，不输出匹配值。

## 后端覆盖率检查器

`check_backend_coverage.py` 由统一门禁调用，读取写入系统临时目录的 coverage.py JSON，并分别强制语句覆盖率不低于 80%、分支覆盖率不低于 75%。门禁会在 `finally` 中删除该临时报告；检查器不会读取项目数据库或用户数据。

完整门禁、单项命令和覆盖率阈值见 [质量门禁说明](../docs/QUALITY_GATES.md)。
