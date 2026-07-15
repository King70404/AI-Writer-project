# 本地开发脚本

本目录包含 AIWebNovel 阶段 0 的本地质量治理与 E2E 编排脚本。脚本不会创建 Git 提交或执行 `git add`；默认质量门禁不会启动开发服务器或浏览器，只有显式 E2E 命令会启动受控的本地测试进程。

## 统一质量门禁

```powershell
.\scripts\quality_gate.ps1
```

默认顺序检查 Git 差异、仓库卫生、Ruff 格式与规则、mypy、后端测试与覆盖率、Python 依赖完整性、前端质量脚本与 npm 依赖树。任一步失败都会立即返回非零退出码。默认模式不访问网络。

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

`run_e2e.ps1` 由前端 package scripts 以开发、生产集成或全部模式调用，也可用固定 `-Scenario` 编号独立运行单项。它为每个场景创建独立 `.runtime/e2e` 目录和 SQLite，在固定 loopback 专用端口启动服务，等待真实 URL，就地运行 Playwright，并在 `finally` 中只终止已保存 PID 与启动时间的自有进程树。`run_e2e_service.ps1` 是前台子进程入口，只为该子进程设置后端数据库、静态服务或 Vite 代理环境，并向父脚本登记实际 Node/Python 进程。`check_e2e_cleanup.ps1` 从仓库根目录复核端口、临时运行目录和成功运行产物均已释放；显式 `e2e:report` 命令通过 `show_e2e_report.ps1` 打开最近一次保留的失败报告。

完整命令、端口、网络隔离与诊断规则见 [浏览器端到端测试](../docs/E2E_TESTING.md)。

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
