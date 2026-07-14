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

## 本地命令

以下命令均从本目录执行：

```powershell
npm install
npm run dev
npm run typecheck
npm run test:run
npm run test
npm run build
npm run preview
```

`npm run test` 进入交互测试模式，`npm run test:run` 单次运行全部前端测试。`npm run build` 先执行严格类型检查，再生成本地生产构建；`npm run preview` 仅用于本地查看该构建。M0 仍未完成，后续还有质量门禁和本地数据目录任务。
