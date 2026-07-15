# 浏览器端到端测试

DEV-0.7 使用 Playwright Test 在干净、无认证状态的 Chromium 上验收真实本地服务。浏览器测试覆盖开发模式下的 FastAPI、Vite 与 React 协作，以及生产集成模式下由 FastAPI 独立提供 API、静态资源和 SPA 回退。它只证明阶段 0 工程基础可用，当前仍没有小说业务测试。

## 安装

Playwright 是 `frontend` 的本地开发依赖，版本由 `package-lock.json` 固定。项目只安装 Playwright 管理的 Chromium，以控制下载量和测试矩阵；本阶段不安装 Firefox、WebKit，也不读取系统 Chrome、Edge 或用户浏览器配置。

首次运行或本地浏览器缓存缺失时，在 `frontend` 目录执行：

```powershell
npm run e2e:install
npx playwright install --list
```

Chromium 二进制由 Playwright 保存在当前用户的仓库外缓存中，不进入 Git。默认 E2E 命令不会自动下载浏览器；缺失时会失败并提示上述安装命令。

## 运行命令

在 `frontend` 目录执行：

```powershell
npm run e2e:dev
npm run e2e:integrated
npm run e2e
```

- `e2e:dev` 验证 Vite 页面、真实健康检查、手动重新检查和客户端路由；
- `e2e:integrated` 先构建前端，再验证 FastAPI 静态服务、API/资源/SPA 隔离以及缺失构建的安全失败；
- `e2e` 按开发模式、生产集成模式的顺序运行全部浏览器验收，任一阶段失败即返回非零。

每个场景都重新启动所需服务并使用独立 SQLite，不依赖其他场景的执行顺序。需要独立复现单项时，在对应模式后传入固定场景编号，例如：

```powershell
npm run e2e:dev -- -Scenario E2E-DEV-001
npm run e2e:integrated -- -Scenario E2E-INT-003
```

默认使用无头 Chromium、`retries=0` 和单 worker，不自动打开报告或浏览器窗口。人工调试时可执行 `npm run e2e:headed`；失败后执行 `npm run e2e:report` 查看本地 HTML 报告。截图和 trace 只在失败时保留，视频关闭；成功运行会删除无用的模式报告和结果目录。

## 本地服务与临时数据

E2E 使用固定专用 loopback 端口，启动前必须确认端口空闲，绝不复用开发者已经启动的服务：

| 模式 | 服务 | 端口 |
| --- | --- | ---: |
| 开发 | Vite | 14173 |
| 开发 | FastAPI | 18120 |
| 生产集成 | FastAPI | 18121 |
| 缺失构建失败验收 | FastAPI | 18122 |

开发模式只从 Vite 访问页面，Vite 的 `/api` 代理仅指向本次 E2E 后端，并为测试关闭 HMR WebSocket。生产集成模式不启动 Vite；正常构建验收结束并清理后，才以缺少 `index.html` 的受控目录启动独立失败验收进程。

每个独立场景在 `.runtime/e2e/` 下创建唯一运行目录和独立 SQLite 数据库，不使用默认开发数据库，也不创建正式用户数据目录。运行结束会清理数据库及 WAL、SHM、journal、临时构建目录和服务日志。`run_e2e.ps1` 保存启动器及其实际 Node/Python 服务的 PID 与启动时间，只终止本次记录的进程树，不按进程名结束其他 Node 或 Python 进程；`check_e2e_cleanup.ps1` 复核专用端口、运行目录和成功运行产物均已释放。

## 安全隔离与诊断

每个浏览器上下文安装网络守卫，只允许当前模式的 `http://127.0.0.1:<端口>`，同时阻止外部 HTTP、WebSocket 和 `file://`。页面错误、非预期控制台错误和非预期请求失败会使测试失败。诊断只记录主机与路径摘要，不记录查询参数、Cookie、Authorization 或完整页面 HTML。

失败产物只保存在被 Git 忽略的 `frontend/playwright-results/` 与 `frontend/playwright-report/`。服务启动错误只输出经过路径替换、行数和长度限制的日志尾部；无论成功、断言失败或受控启动中断，服务和临时数据库清理都在 `finally` 中执行。

## 统一质量门禁

浏览器 E2E 需要额外的 Chromium 缓存、真实服务进程和较长运行时间，因此不属于默认离线质量门禁。默认门禁仍执行：

```powershell
.\scripts\quality_gate.ps1
```

需要完整浏览器验收时显式执行：

```powershell
.\scripts\quality_gate.ps1 -IncludeE2E
.\scripts\quality_gate.ps1 -IncludeDependencyAudit -IncludeE2E
```

`-IncludeE2E` 只在既有门禁及可选审计通过后运行 E2E，并在成功后执行清理复核。它不会安装浏览器、修改源码、创建提交或访问外部网页。
