# AIWebNovel 前端

本目录包含 AIWebNovel 的 React、TypeScript 与 Vite 前端工程基础。

## 当前范围

当前只有阶段 0 工程基础页、最小路由、全局错误边界、类型化原生 `fetch` 客户端和真实 `SystemStatus`。状态区会依次请求后端 live 与 ready 接口，区分检查中、已就绪、后端未就绪和当前无法连接，并提供会取消旧请求的“重新检查”按钮；不会后台轮询。

前端没有小说项目、规划、写作、评审、Codex 或其他业务功能。状态显示正常只代表本地工程基础检查通过。

## 环境要求

- 正式 64 位 Node.js `>=24.0.0 <25.0.0`；
- npm，使用随 Node.js 提供的版本。

## 开发模式

先在仓库根目录启动 FastAPI：

```powershell
.\.venv\Scripts\python.exe -m aiwebnovel
```

再在本目录启动 Vite：

```powershell
npm run dev
```

浏览器只访问 `http://127.0.0.1:5173`。前端始终使用相对 `/api/v1`；Vite 仅代理 `/api` 到固定的本地开发后端 `http://127.0.0.1:8000`，不代理其他路径或 WebSocket。开发服务器只绑定 `127.0.0.1`。

## 生产集成模式

在本目录执行 `npm run build` 后，回到仓库根目录显式设置 `AIWEBNOVEL_SERVE_FRONTEND=true` 并启动 FastAPI。浏览器只访问后端端口，前端通过同源相对 API 工作；不需要 Vite 开发服务器。`dist/` 是本地构建产物并保持被 Git 忽略。

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

当前 E2E 只验收阶段 0 基础页、真实健康状态、客户端路由及 API/静态资源/SPA 隔离；仍没有小说业务 E2E。

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
