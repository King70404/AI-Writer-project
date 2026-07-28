# AIWebNovel 前端

本目录包含 AIWebNovel 的 React、TypeScript 与 Vite 前端工程基础。

## 当前范围

当前包含阶段 0 工程基础页、全局错误边界、真实 `SystemStatus`、DEV-1.7 的 `/projects` 列表与创建页面、DEV-1.8 的 `/projects/:projectId` 当前详情、完整修订和显式并发冲突流程、DEV-1.9 的 `/projects/:projectId/history` 只读不可变修订历史页面，以及DEV-2.5的`/projects/:projectId/story-bible`纯文本创建、读取、完整修订和显式并发冲突流程。Project与Story Bible前端使用类型化 API客户端、精确运行时响应校验、共享的内存 Security Session和强ETag编辑基线；创建POST与修订PUT均只发送一次且不自动重试。

前端没有用户登录、安全设置页、Project或Story Bible历史回滚/恢复/Diff/编辑/删除、归档/自动保存、规划、写作、评审、Codex 或其他创作功能。Project历史摘要不含 description，正文只在显式选择单个 Revision 后按需读取；cursor 和正文不进入浏览器存储。Story Bible没有Revision历史入口。本地 session 不是身份认证；CSRF、ETag和编辑草稿只保存在当前 JavaScript/React 内存，不写入 `localStorage` 或 `sessionStorage`，页面不显示安全令牌。Project和Story Bible管理可用不代表小说创作功能已经实现。

## 环境要求

- 正式 64 位 Node.js `>=24.0.0 <25.0.0`；
- npm，使用随 Node.js 提供的版本。

## 开发模式

从仓库根目录运行统一开发入口：

```powershell
.\scripts\environment_doctor.ps1 -Mode Development
.\scripts\start_development.ps1
```

浏览器默认访问 `http://127.0.0.1:5173`。前端始终使用相对 `/api/v1`；Vite 仅代理 `/api` 到本次统一入口指定的本地后端端口（默认为 `http://127.0.0.1:8000`），不代理其他路径或 WebSocket。开发服务器只绑定 `127.0.0.1`。

统一入口会把 Vite 代理指向本次选择的后端端口，默认使用与正式用户数据隔离的 `%LOCALAPPDATA%\AIWebNovel-Development`。它不会运行 `npm install`、自动构建、执行迁移或自动打开浏览器；按 `Ctrl+C` 只清理本次脚本拥有的服务。

原生 `fetch` 默认不携带外部凭据；同源安全 session 可接收 HttpOnly Cookie。未来不安全请求必须先建立本地 session，再从模块内存加入 CSRF 头，不得将 Cookie 或令牌输出到控制台。

## 生产集成模式

从仓库根目录运行 `.\scripts\environment_doctor.ps1 -Mode Integrated` 和 `.\scripts\start_integrated.ps1`。入口默认要求已有有效 `dist/`，只启动 FastAPI；仅显式传入 `-BuildFrontend` 时才执行 `npm run build`。浏览器只访问后端端口，前端通过同源相对 API 工作；不需要 Vite 开发服务器。`dist/` 是本地构建产物并保持被 Git 忽略，production 默认关闭 API 文档，默认数据根为隔离的 `%LOCALAPPDATA%\AIWebNovel-Integrated-Development`。

## 浏览器端到端验收

浏览器验收使用项目本地的 Playwright Test，并且只安装和运行其管理的 Chromium。首次运行前执行 `npm run e2e:install`；该命令不会安装 Firefox、WebKit 或项目 npm 依赖。

```powershell
npm run e2e:dev
npm run e2e:integrated
npm run e2e
npm run e2e:headed
npm run e2e:report
```

`e2e:dev` 自动启动 E2E 专用的 FastAPI 与 Vite，`e2e:integrated` 先构建前端并只启动提供 API 和静态文件的 FastAPI，`e2e` 依次执行两种模式。默认测试无头运行；`e2e:headed` 仅用于人工调试，`e2e:report` 打开本地失败报告。测试服务只绑定专用的 `127.0.0.1` 端口，使用临时数据库，阻止外部网络，并在结束后清理本次测试拥有的进程和临时数据。

每个场景使用独立服务和数据库。可用 `npm run e2e:dev -- -Scenario E2E-DEV-001` 或 `npm run e2e:integrated -- -Scenario E2E-INT-003` 独立运行固定场景编号。

当前16个 E2E 场景验收阶段0基础、Project API、`E2E-INT-008`真实Project前端创建/持久刷新/21项加载更多、`E2E-INT-009`详情读取与显式412冲突恢复、`E2E-INT-010`不可变历史逐项读取与20+1分页、`E2E-INT-011` Story Bible HTTP链路，以及`E2E-INT-012` Story Bible前端创建、刷新、完整修订和显式412冲突恢复；同时验证生产安全头、CSP、本地Session Cookie、浏览器无CSRF/cursor/ETag/草稿/正文持久数据和专用数据根清理。它不覆盖小说正文创作功能。

## 本地命令

以下命令均从本目录执行：

```powershell
npm install
npm run dev
npm run format:check
npm run lint
npm run typecheck
npm run test:run
npm run test:coverage
npm run quality
npm run test
npm run build
npm run preview
npm ls --depth=0
```

`npm run test` 进入交互测试模式，`npm run test:run` 单次运行全部前端测试。`npm run test:coverage` 强制 statements 80%、branches 75%、functions 80% 和 lines 80% 的门槛。`npm run quality` 统一执行前端格式检查、lint、类型检查、覆盖率测试和生产构建；它不会自动改写源码。`npm run build` 先执行严格类型检查，再生成本地生产构建；`npm run preview` 仅用于本地查看该构建。完整的跨栈门禁和可选联网审计见 [本地质量门禁](../docs/QUALITY_GATES.md)。当前仍没有小说业务功能。
