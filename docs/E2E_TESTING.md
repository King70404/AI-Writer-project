# 浏览器端到端测试

Playwright在独立本地数据根上验收开发与生产集成服务。`E2E-INT-006`覆盖单Project API链路，`E2E-INT-007`覆盖稳定Keyset列表API，`E2E-INT-008`完成Project创建与列表分页，`E2E-INT-009`覆盖当前详情、修订和显式412冲突恢复，`E2E-INT-010`覆盖不可变Revision历史查看与20+1分页，`E2E-INT-011`覆盖Story Bible创建、两种读取、完整替换、stale 412与写安全边界。六个业务场景只对自己的临时数据库显式迁移；应用启动本身仍不迁移。

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
- `e2e:integrated`先构建前端，再验证FastAPI静态服务、生产安全基线、`E2E-INT-006`单Project API链路、`E2E-INT-007`稳定列表分页、`E2E-INT-008`Project列表/创建、`E2E-INT-009`Project详情/修订、`E2E-INT-010`Project不可变历史、`E2E-INT-011`Story Bible HTTP链路，以及缺失构建的安全失败；
- `e2e` 按开发模式、生产集成模式的顺序运行全部浏览器验收，任一阶段失败即返回非零。

每个场景都重新启动所需服务并使用独立 `AIWEBNOVEL_DATA_ROOT`，不依赖其他场景的执行顺序。需要独立复现单项时，在对应模式后传入固定场景编号，例如：

```powershell
npm run e2e:dev -- -Scenario E2E-DEV-001
npm run e2e:integrated -- -Scenario E2E-INT-003
npm run e2e:integrated -- -Scenario E2E-INT-005
npm run e2e:integrated -- -Scenario E2E-INT-006
npm run e2e:integrated -- -Scenario E2E-INT-007
npm run e2e:integrated -- -Scenario E2E-INT-008
npm run e2e:integrated -- -Scenario E2E-INT-009
npm run e2e:integrated -- -Scenario E2E-INT-010
npm run e2e:integrated -- -Scenario E2E-INT-011
```

当前完整集共15个场景：3个开发模式、11个生产集成模式和1个缺失构建启动失败场景。

统一启动入口的最低浏览器验收由仓库根目录的受控脚本执行：

```powershell
.\scripts\check_startup_runtime.ps1 -Mode Development
.\scripts\check_startup_runtime.ps1 -Mode Integrated
```

Development与Integrated烟测使用专用临时端口和唯一隔离数据根；它们不会复制全部15个E2E场景。`E2E-INT-006`保留完整单Project API链路，`E2E-INT-007`保留稳定列表API，`E2E-INT-008`验证Project列表/创建，`E2E-INT-009`验证详情修订与冲突恢复。`E2E-INT-010`经UI形成Revision 1至3并逐项读取原始正文，再经独立API扩展到21，验证20+1降序Keyset分页、current标记、cursor不进入URL/存储/日志、历史GET不获取Session、production直接刷新、未知路由404、双不可变触发器、无外部网络及完整清理。`E2E-INT-011`通过真实production进程验证Story Bible的Project归属、双GET一致性、强ETag、完整替换、stale隐私、Session/CSRF边界和不存在前端入口。

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

每个独立场景创建带 E2E 标识和随机值的唯一临时数据根，并通过子进程环境变量传入。应用数据库只能位于该根的 `data/aiwebnovel.sqlite3`，应用运行目录只能位于该根的 `runtime/`；它不使用正式 `%LOCALAPPDATA%\AIWebNovel`，也不读取该目录。场景可以另用受控编排目录保存 PID 清单和短期诊断，但编排目录不是应用数据根。

运行结束会清理数据库及 WAL、SHM、journal、整个场景数据根、临时构建目录和服务诊断。清理只接受本场景记录、位于受控父目录内且名称带 E2E 标识的精确路径；不会按模糊名称删除，也不会影响其他测试进程。`run_e2e.ps1` 保存启动器及其实际 Node/Python 服务的 PID 与启动时间，只终止本次记录的进程树，不按进程名结束其他 Node 或 Python 进程；清理失败会使测试失败，`check_e2e_cleanup.ps1` 复核专用端口、编排目录和成功运行产物均已释放。

所有正常开发和生产集成场景的 ready 响应必须包含真实的 `storage=ok` 与 `database=ok`。缺失构建场景只允许 `frontend=failed`，不能以存储失败掩盖预期的前端故障。

DEV-0.9 起，正常场景的 ready 还必须包含 `security=ok`。生产集成验收同时证明：HTML 与 API 基础安全头存在、CSP 不阻止本地 React 构建、Uvicorn 不公开 Server 版本、生产 `/docs`、`/redoc` 与 `/openapi.json` 关闭、非法 Host 被拒绝、session 接口设置 HttpOnly/SameSite Cookie，且浏览器 `localStorage` 与 `sessionStorage` 中没有 CSRF 令牌。测试和诊断不得打印 Cookie 或 CSRF 原值。

## 安全隔离与诊断

每个浏览器上下文安装网络守卫，只允许当前模式的 `http://127.0.0.1:<端口>`，同时阻止外部 HTTP、WebSocket 和 `file://`。页面错误、非预期控制台错误和非预期请求失败会使测试失败。诊断只记录主机与路径摘要，不记录查询参数、Cookie、Authorization、CSRF 令牌或完整页面 HTML。伪造代理头不能改变 Host、scheme、客户端来源或同源判断；服务启动器显式保持代理头不受信任。

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
